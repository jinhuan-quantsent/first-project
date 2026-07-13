"""
IMA 知识库文件上传模块
封装腾讯 IMA 知识库 OpenAPI 的三步上传流程：
  1. create_media  — 获取 COS 上传凭证
  2. COS 上传      — 使用临时凭证上传文件到腾讯云 COS
  3. add_knowledge — 关联文件到知识库

依赖: pip install cos-python-sdk-v5 requests
"""

import os
import time
import logging
import requests
from qcloud_cos import CosConfig, CosS3Client

logger = logging.getLogger(__name__)

# ── IMA OpenAPI 配置 ──────────────────────────────────────────
IMA_API_BASE = "https://ima.qq.com/openapi/wiki/v1"

# 凭证优先从环境变量读取，回退到默认值
IMA_CLIENT_ID = os.environ.get(
    "IMA_CLIENT_ID",
    "ad23aaf1b01a5efb85257d0deb263157",
)
IMA_API_KEY = os.environ.get(
    "IMA_API_KEY",
    "aIOId/wORTIGUbhsa4Df8ZNZDUbuIRdKOZJvLiCMAxR96j3BTd9+sENU+Nt2ZfcfcWLMy76NaA==",
)

# ── 文件类型 → IMA media_type 映射 ────────────────────────────
# (media_type, content_type)
MEDIA_TYPE_MAP = {
    ".csv":  (5,  "text/csv"),
    ".xlsx": (5,  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ".xls":  (5,  "application/vnd.ms-excel"),
    ".pdf":  (1,  "application/pdf"),
    ".doc":  (3,  "application/msword"),
    ".docx": (3,  "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    ".md":   (7,  "text/markdown"),
    ".txt":  (13, "text/plain"),
    ".png":  (9,  "image/png"),
    ".jpg":  (9,  "image/jpeg"),
    ".jpeg": (9,  "image/jpeg"),
    ".webp": (9,  "image/webp"),
}

# 文件大小上限（字节）
SIZE_LIMITS = {
    5:  10 * 1024 * 1024,   # Excel/CSV/TXT/Xmind/Markdown → 10 MB
    7:  10 * 1024 * 1024,
    13: 10 * 1024 * 1024,
    14: 10 * 1024 * 1024,
    9:  30 * 1024 * 1024,   # 图片 → 30 MB
    1:  200 * 1024 * 1024,  # PDF/Word/PPT → 200 MB
    3:  200 * 1024 * 1024,
    4:  200 * 1024 * 1024,
}


def _ima_api(endpoint: str, payload: dict, retries: int = 3) -> dict:
    """调用 IMA OpenAPI，带重试"""
    url = f"{IMA_API_BASE}/{endpoint}"
    headers = {
        "Content-Type": "application/json",
        "ima-openapi-clientid": IMA_CLIENT_ID,
        "ima-openapi-apikey": IMA_API_KEY,
    }
    last_err = None
    for attempt in range(1, retries + 1):
        try:
            resp = requests.post(url, json=payload, headers=headers, timeout=30)
            data = resp.json()
            # API 返回 {code, msg, data, request_id}（非 retcode/errmsg）
            if data.get("code") == 0:
                return data.get("data", {})
            # 频控可重试
            if data.get("code") == 110021 and attempt < retries:
                logger.warning(f"IMA API 频控，{attempt}s 后重试...")
                time.sleep(attempt)
                continue
            raise RuntimeError(
                f"IMA API {endpoint} 失败: code={data.get('code')}, "
                f"msg={data.get('msg')}"
            )
        except requests.RequestException as e:
            last_err = e
            if attempt < retries:
                logger.warning(f"网络错误第 {attempt} 次: {e}，重试中...")
                time.sleep(attempt * 2)
            else:
                raise
    raise RuntimeError(f"IMA API {endpoint} 重试 {retries} 次后仍失败: {last_err}")


def _cos_upload(cos_cred: dict, file_path: str, content_type: str):
    """使用 IMA 返回的临时凭证上传文件到腾讯云 COS"""
    config = CosConfig(
        Region=cos_cred["region"],
        SecretId=cos_cred["secret_id"],
        SecretKey=cos_cred["secret_key"],
        Token=cos_cred["token"],
        Scheme="https",
    )
    client = CosS3Client(config)

    with open(file_path, "rb") as fp:
        client.put_object(
            Bucket=cos_cred["bucket_name"],
            Body=fp,
            Key=cos_cred["cos_key"],
            ContentType=content_type,
        )


def upload_to_kb(
    file_path: str,
    kb_id: str,
    folder_id: str | None = None,
    rename: str | None = None,
) -> str:
    """
    上传文件到 IMA 知识库（三步流程）

    Args:
        file_path:  本地文件路径
        kb_id:      知识库 ID
        folder_id:  目标文件夹 ID（可选，默认根目录）
        rename:     上传后的文件名（可选，默认用原文件名）

    Returns:
        media_id: 知识库中的媒体 ID

    Raises:
        FileNotFoundError: 文件不存在
        ValueError:         不支持的文件类型 / 超过大小限制
        RuntimeError:       API 调用或上传失败
    """
    if not os.path.exists(file_path):
        raise FileNotFoundError(f"文件不存在: {file_path}")

    file_name = rename or os.path.basename(file_path)
    file_ext = os.path.splitext(file_name)[1].lower()
    file_size = os.path.getsize(file_path)

    if file_ext not in MEDIA_TYPE_MAP:
        raise ValueError(f"不支持的文件类型: {file_ext}")

    media_type, content_type = MEDIA_TYPE_MAP[file_ext]

    # 大小检查
    limit = SIZE_LIMITS.get(media_type, 10 * 1024 * 1024)
    if file_size > limit:
        raise ValueError(
            f"文件大小 {file_size} 超过限制 {limit}（{file_ext} 类型上限 {limit // 1024 // 1024}MB）"
        )

    logger.info(
        f"上传到 IMA KB: {file_name} ({file_size:,} bytes) "
        f"→ kb={kb_id[:12]}..., folder={folder_id}"
    )

    # ── Step 1: 创建媒体，获取 COS 凭证 ──
    create_data = _ima_api("create_media", {
        "file_name": file_name,
        "file_size": file_size,
        "content_type": content_type,
        "knowledge_base_id": kb_id,
        "file_ext": file_ext.lstrip("."),
    })
    media_id = create_data["media_id"]
    cos_cred = create_data["cos_credential"]
    logger.info(f"  [1/3] create_media OK  media_id={media_id}")

    # ── Step 2: 上传文件到 COS ──
    _cos_upload(cos_cred, file_path, content_type)
    logger.info(
        f"  [2/3] COS 上传 OK  "
        f"bucket={cos_cred['bucket_name']}, key={cos_cred['cos_key'][:40]}..."
    )

    # ── Step 3: 添加知识 ──
    add_payload = {
        "media_type": media_type,
        "media_id": media_id,
        "title": file_name,
        "knowledge_base_id": kb_id,
        "file_info": {
            "cos_key": cos_cred["cos_key"],
            "file_size": file_size,
            "last_modify_time": int(time.time()),
            "file_name": file_name,
        },
    }
    if folder_id:
        add_payload["folder_id"] = folder_id

    add_data = _ima_api("add_knowledge", add_payload)
    result_id = add_data.get("media_id", media_id)
    logger.info(f"  [3/3] add_knowledge OK  media_id={result_id}")

    return result_id
