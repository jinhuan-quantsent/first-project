"""
JWT 认证中间件
V4.0 云服务启用：Supabase Auth 作为身份源 + 后端自签 JWT 验证
"""
import uuid
from datetime import datetime, timezone, timedelta
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.core.config import settings

security = HTTPBearer(auto_error=False)


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def create_access_token(
    user_id: str,
    email: str,
    role: str = "authenticated",
) -> str:
    """签发 JWT access token"""
    now = _now_utc()
    payload = {
        "sub": user_id,
        "email": email,
        "role": role,
        "iat": now,
        "exp": now + timedelta(seconds=settings.JWT_EXPIRE_SECONDS),
        "jti": str(uuid.uuid4()),
    }
    return jwt.encode(payload, settings.SUPABASE_JWT_SECRET, algorithm=settings.JWT_ALGORITHM)


def decode_access_token(token: str) -> dict:
    """验证并解码 JWT token，返回 payload"""
    try:
        payload = jwt.decode(
            token,
            settings.SUPABASE_JWT_SECRET,
            algorithms=[settings.JWT_ALGORITHM],
            leeway=timedelta(seconds=30),  # 允许 30s clock skew
        )
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": 40102,
                "data": None,
                "message": "Token 已过期",
            },
        )
    except jwt.InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": 40103,
                "data": None,
                "message": "Token 无效",
            },
        )


async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> str:
    """
    FastAPI 依赖：从 Authorization header 提取 user_id

    - AUTH_DISABLED 模式：返回 "demo_user"
    - 正常模式：验证 JWT，返回 payload["sub"]
    - 无 token：40101
    """
    # 降级模式
    if settings.AUTH_DISABLED:
        return "demo_user"

    if credentials is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": 40101,
                "data": None,
                "message": "未提供认证凭据",
            },
        )

    payload = decode_access_token(credentials.credentials)
    user_id: str = payload.get("sub", "")
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={
                "code": 40103,
                "data": None,
                "message": "Token 中无有效用户标识",
            },
        )
    return user_id


async def get_current_user_optional(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> Optional[str]:
    """可选认证：有 token 就解析，无 token 返回 None（用于兼容公开端点）"""
    if settings.AUTH_DISABLED:
        return "demo_user"

    if credentials is None:
        return None

    try:
        payload = decode_access_token(credentials.credentials)
        return payload.get("sub", "")
    except HTTPException:
        return None
