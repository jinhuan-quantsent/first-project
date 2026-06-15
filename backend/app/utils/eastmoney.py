"""
东方财富数据源模块 V5.0
提供基金搜索、实时估值、净值历史、持仓、板块行情、资金流向等数据

数据源优先级：东方财富(搜索+估值+板块) → Tushare(净值历史+基础信息) → Mock

可用接口：
1. 基金搜索: fundsuggest.eastmoney.com (关键词搜索，支持代码/名称/拼音)
2. 实时估值: fundgz.1234567.com.cn (盘中实时估值，交易时间内更新)
3. 基金详情: fund.eastmoney.com/pingzhongdata (持仓、费率、净值等)
4. 净值历史: Tushare fund_nav (精确历史净值)
5. 基础信息: Tushare fund_basic (基金类型、成立日、基准等)
6. 概念板块行情: 腾讯行情API + Tushare行业分类 (31个申万一级行业 + 热门概念板块)
7. 行业板块行情: 腾讯行情API (中证行业指数实时涨跌+成交量)
"""
import asyncio
import json
import logging
import re
from datetime import date, datetime, timedelta
from typing import Optional

import httpx

from app.core.config import settings
from app.core.redis_client import cache_get, cache_set

logger = logging.getLogger(__name__)

# ============================================================
# 东方财富 FUNDTYPE → 前端 fund_type 映射
# ============================================================
EM_FUNDTYPE_MAP: dict[str, str] = {
    "001": "股票型",
    "002": "混合型",
    "003": "债券型",
    "004": "指数型",
    "005": "货币型",
    "006": "QDII",
    "007": "FOF",
    "008": "商品型",
}

# 东方财富 FTYPE 字段(带子类型) → 大类映射
EM_FTYPE_MAP: dict[str, str] = {
    "股票型": "股票型",
    "混合型-偏股": "混合型",
    "混合型-灵活": "混合型",
    "混合型-偏债": "混合型",
    "混合型-绝对收益": "混合型",
    "债券型-长债": "债券型",
    "债券型-中短债": "债券型",
    "债券型-混合一级": "债券型",
    "债券型-混合二级": "债券型",
    "债券型-增强": "债券型",
    "指数型-股票": "指数型",
    "指数型-债券": "指数型",
    "指数型-海外股票": "指数型",
    "指数型-固收": "指数型",
    "指数型-其他": "指数型",
    "货币型-普通货币": "货币型",
    "货币型-理财货币": "货币型",
    "QDII-普通股票": "QDII",
    "QDII-混合偏股": "QDII",
    "QDII-指数": "QDII",
    "QDII-纯债": "QDII",
    "QDII-混合债": "QDII",
    "FOF-股票型": "FOF",
    "FOF-混合型": "FOF",
    "FOF-债券型": "FOF",
    "商品型": "商品型",
}


def _parse_ftype(ftype: str) -> str:
    """将东方财富FTYPE字段映射为前端fund_type大类"""
    return EM_FTYPE_MAP.get(ftype, ftype.split("-")[0] if "-" in ftype else "其他")


def _cache_key(prefix: str, *args: str) -> str:
    """构建缓存key"""
    raw = f"eastmoney:{prefix}:{':'.join(args)}"
    return raw


# ============================================================
# 1. 基金搜索 (东方财富 fundsuggest)
# ============================================================
async def search_funds_em(
    keyword: str,
    page: int = 1,
    page_size: int = 20,
    fund_type: Optional[str] = None,
) -> dict:
    """
    东方财富基金搜索

    接口: http://fundsuggest.eastmoney.com/FundSearch/api/FundSearchAPI.ashx
    支持按代码、名称、拼音首字母搜索

    Returns:
        {
            "items": [...],
            "total": int,
            "page": int,
            "page_size": int,
        }
    """
    # 检查缓存
    cache_k = _cache_key("search", keyword, str(page), str(page_size), str(fund_type))
    cached = await cache_get(cache_k)
    if cached is not None:
        return cached

    url = "http://fundsuggest.eastmoney.com/FundSearch/api/FundSearchAPI.ashx"
    params = {
        "callback": "",
        "m": "1",
        "key": keyword,
        "pageIndex": page - 1,  # 东方财富从0开始
        "pageSize": page_size,
    }

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url, params=params)
            resp.raise_for_status()
            data = resp.json()

        if data.get("ErrCode") != 0:
            logger.warning("东方财富搜索返回错误: %s", data.get("ErrMsg"))
            return {"items": [], "total": 0, "page": page, "page_size": page_size}

        datas = data.get("Datas", [])
        total_count = data.get("TotalCount", len(datas))

        items = []
        for d in datas:
            info = d.get("FundBaseInfo") or {}
            if not info:
                # 非基金条目（如指数条目 FundBaseInfo=null），跳过
                continue
            ftype_raw = info.get("FTYPE", "")
            ftype_mapped = _parse_ftype(ftype_raw)

            # 按类型过滤
            if fund_type and ftype_mapped != fund_type:
                continue

            items.append({
                "fund_code": info.get("FCODE", d.get("CODE", "")),
                "fund_name": info.get("SHORTNAME", d.get("NAME", "")),
                "fund_short_name": info.get("SHORTNAME", ""),
                "fund_type": ftype_mapped,
                "fund_type_raw": ftype_raw,
                "nav": float(info.get("DWJZ", 0) or 0),
                "manager": info.get("JJJL", ""),
                "company": info.get("JJGS", ""),
                "nav_date": info.get("FSRQ", ""),
                "risk_level": "",  # 东方财富搜索不返回风险等级
                "is_buy": info.get("ISBUY") == "1",
            })

        result = {
            "items": items,
            "total": total_count if not fund_type else len(items),  # 类型过滤后total不准，用len
            "page": page,
            "page_size": page_size,
        }

        # 缓存5分钟
        await cache_set(cache_k, result, ttl=300)
        return result

    except Exception as e:
        logger.warning("东方财富基金搜索失败: %s", e)
        return {"items": [], "total": 0, "page": page, "page_size": page_size}


# ============================================================
# 2. 实时估值 (东方财富 fundgz)
# ============================================================
async def get_fund_realtime(code: str) -> Optional[dict]:
    """
    获取基金实时估值（仅交易时间有效）

    接口: http://fundgz.1234567.com.cn/js/{code}.js
    返回JSONP格式: jsonpgz({...})

    Returns:
        {
            "fund_code": str,
            "fund_name": str,
            "nav_date": str,       # 净值日期
            "nav": float,          # 最近净值
            "estimated_nav": float, # 估算净值
            "estimated_change": float, # 估算涨跌幅(%)
            "estimate_time": str,  # 估算时间
        }
    """
    cache_k = _cache_key("realtime", code)
    cached = await cache_get(cache_k)
    if cached is not None:
        return cached

    url = f"http://fundgz.1234567.com.cn/js/{code}.js"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            text = resp.text

        # 解析JSONP: jsonpgz({...});
        match = re.search(r'jsonpgz\((.+?)\);?', text, re.DOTALL)
        if not match:
            return None

        data = json.loads(match.group(1))
        result = {
            "fund_code": data.get("fundcode", code),
            "fund_name": data.get("name", ""),
            "nav_date": data.get("jzrq", ""),
            "nav": float(data.get("dwjz", 0) or 0),
            "estimated_nav": float(data.get("gsz", 0) or 0),
            "estimated_change": float(data.get("gszzl", 0) or 0),
            "estimate_time": data.get("gztime", ""),
        }

        # 缓存60秒（盘中估值变化快）
        await cache_set(cache_k, result, ttl=60)
        return result

    except Exception as e:
        logger.warning("东方财富实时估值获取失败(%s): %s", code, e)
        return None


# ============================================================
# 3. 基金持仓信息 (东方财富 pingzhongdata)
# ============================================================
async def get_fund_holdings(code: str) -> Optional[list[dict]]:
    """
    获取基金持仓股票信息

    接口: http://fund.eastmoney.com/pingzhongdata/{code}.js
    解析 stockCodes 变量

    Returns:
        [{"stock_code": str, "exchange": str}, ...]
    """
    cache_k = _cache_key("holdings", code)
    cached = await cache_get(cache_k)
    if cached is not None:
        return cached

    url = f"http://fund.eastmoney.com/pingzhongdata/{code}.js"
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            text = resp.text

        # 解析 stockCodes
        match = re.search(r'var stockCodes=\[(.+?)\]', text)
        if not match:
            return []

        raw_codes = match.group(1).strip('"').split('","')
        holdings = []
        for sc in raw_codes:
            sc = sc.strip('"').strip()
            if not sc:
                continue
            # 格式: 6005191 (最后一位是市场标识: 1=沪, 0/2=深)
            if len(sc) >= 7:
                stock_code = sc[:6]
                market_flag = sc[6]
                exchange = "SH" if market_flag == "1" else "SZ"
                holdings.append({"stock_code": stock_code, "exchange": exchange})

        # 缓存1小时
        await cache_set(cache_k, holdings, ttl=3600)
        return holdings

    except Exception as e:
        logger.warning("东方财富持仓获取失败(%s): %s", code, e)
        return None


# ============================================================
# 4. Tushare 基金基础信息
# ============================================================
async def get_fund_basic_tushare(ts_code: str) -> Optional[dict]:
    """
    通过Tushare获取单只基金基础信息

    Args:
        ts_code: Tushare格式的基金代码，如 "110011.OF" 或 "510300.SH"

    Returns:
        基金基础信息字典，或 None
    """
    cache_k = _cache_key("fund_basic", ts_code)
    cached = await cache_get(cache_k)
    if cached is not None:
        return cached

    try:
        from app.utils.data_source import data_source
        if not data_source._tushare_pro:
            return None

        # 尝试当前后缀，如果失败则尝试其他后缀
        suffixes_to_try = [ts_code.split(".")[-1]] if "." in ts_code else ["OF"]
        if suffixes_to_try[0] == "OF":
            suffixes_to_try.extend(["SH", "SZ"])  # 场外找不到时试场内
        elif suffixes_to_try[0] in ("SH", "SZ"):
            suffixes_to_try.append("OF")  # 场内找不到时试场外

        base_code = ts_code.split(".")[0]
        for suffix in suffixes_to_try:
            try:
                try_code = f"{base_code}.{suffix}"
                df = data_source._tushare_pro.fund_basic(ts_code=try_code)
                if df is not None and not df.empty:
                    row = df.iloc[0]
                    result = {
                        "ts_code": row.get("ts_code", ""),
                        "fund_name": row.get("name", ""),
                        "fund_type": row.get("fund_type", ""),
                        "management": row.get("management", ""),
                        "custodian": row.get("custodian", ""),
                        "found_date": str(row.get("found_date", "")),
                        "benchmark": row.get("benchmark", ""),
                        "status": row.get("status", ""),
                        "invest_type": row.get("invest_type", ""),
                        "m_fee": float(row.get("m_fee", 0) or 0),
                        "c_fee": float(row.get("c_fee", 0) or 0),
                        "market": row.get("market", ""),
                    }
                    # 缓存24小时（基础信息很少变化）
                    await cache_set(cache_k, result, ttl=86400)
                    return result
            except Exception as e:
                # Tushare可能返回每分钟限流错误，跳过尝试下一个后缀
                logger.debug("fund_basic %s 尝试失败: %s", try_code, e)
                continue

        return None

    except Exception as e:
        logger.warning("Tushare fund_basic获取失败(%s): %s", ts_code, e)
        return None


# ============================================================
# 5. Tushare 基金净值历史
# ============================================================
async def get_fund_nav_history(
    ts_code: str,
    days: int = 30,
) -> Optional[list[dict]]:
    """
    通过Tushare获取基金净值历史

    Args:
        ts_code: Tushare格式基金代码，如 "110011.OF" 或 "510300.SH"
        days: 获取最近N天数据

    Returns:
        [{"date": str, "nav": float, "accumulated_nav": float, "daily_return": float}, ...]
    """
    cache_k = _cache_key("nav_history", ts_code, str(days))
    cached = await cache_get(cache_k)
    if cached is not None:
        return cached

    try:
        from app.utils.data_source import data_source
        if not data_source._tushare_pro:
            return None

        end_date = date.today().strftime("%Y%m%d")
        start_date = (date.today() - timedelta(days=days + 10)).strftime("%Y%m%d")

        # 尝试不同后缀（和 fund_basic 同理）
        base_code = ts_code.split(".")[0] if "." in ts_code else ts_code
        suffix = ts_code.split(".")[-1] if "." in ts_code else "OF"
        suffixes = [suffix]
        if suffix == "OF":
            suffixes.extend(["SH", "SZ"])
        elif suffix in ("SH", "SZ"):
            suffixes.append("OF")

        for suf in suffixes:
            try_code = f"{base_code}.{suf}"
            df = data_source._tushare_pro.fund_nav(
                ts_code=try_code,
                start_date=start_date,
                end_date=end_date,
            )
            if df is None or df.empty:
                continue

            df = df.sort_values("nav_date", ascending=True)

            result = []
            for _, row in df.iterrows():
                unit_nav = float(row.get("unit_nav", 0) or 0)
                accum_nav = float(row.get("accum_nav", 0) or 0)
                adj_nav = float(row.get("adj_nav", 0) or 0)

                daily_ret = 0.0
                if len(result) > 0 and adj_nav > 0 and result[-1].get("adj_nav", 0) > 0:
                    prev_adj = result[-1]["adj_nav"]
                    daily_ret = round((adj_nav / prev_adj - 1) * 100, 2)

                result.append({
                    "date": str(row.get("nav_date", "")),
                    "nav": unit_nav,
                    "accumulated_nav": accum_nav,
                    "adj_nav": adj_nav,
                    "daily_return": daily_ret,
                })

            result = result[-days:]
            await cache_set(cache_k, result, ttl=300)
            return result

        return None

    except Exception as e:
        logger.warning("Tushare fund_nav获取失败(%s): %s", ts_code, e)
        return None


# ============================================================
# 6. 基金代码格式转换工具
# ============================================================
def code_to_tushare(code: str) -> str:
    """
    6位基金代码 → Tushare格式

    规则：
    - 5/6开头 → 场内ETF/LOF，根据代码判断交易所:
      - 51xxxx, 52xxxx, 56xxxx, 58xxxx → .SH (上交所)
      - 15xxxx, 16xxxx, 18xxxx → .SZ (深交所)
    - 其他 → 场外基金 → .OF

    示例:
      110011 → 110011.OF
      510300 → 510300.SH
      159919 → 159919.SZ
      012414 → 012414.OF (场外LOF)
    """
    code = code.strip()
    if "." in code:
        return code

    # 场内基金判断
    if code.startswith(("51", "52", "56", "58", "50")):
        return f"{code}.SH"
    if code.startswith(("15", "16", "18")):
        return f"{code}.SZ"

    # 默认场外
    return f"{code}.OF"


def tushare_to_code(ts_code: str) -> str:
    """
    Tushare格式 → 6位基金代码
    110011.OF → 110011
    """
    return ts_code.split(".")[0] if "." in ts_code else ts_code


# ============================================================
# 7. 组合搜索：东方财富搜索 + Tushare补全
# ============================================================
async def search_funds_combined(
    keyword: str,
    page: int = 1,
    page_size: int = 20,
    fund_type: Optional[str] = None,
) -> dict:
    """
    组合搜索策略：
    1. 优先东方财富搜索API（支持关键词模糊匹配）
    2. 对搜索结果中的每只基金，尝试从Tushare补全基础信息（规模、成立日等）
    3. 如果东方财富失败，降级到Tushare fund_basic（仅支持代码精确搜索）
    4. 最终降级到Mock数据
    """
    # 第一级：东方财富搜索
    em_result = await search_funds_em(keyword, page, page_size, fund_type)
    if em_result["items"]:
        # 尝试用Tushare补全额外信息（异步不阻塞）
        for item in em_result["items"]:
            ts_code = code_to_tushare(item["fund_code"])
            basic = await get_fund_basic_tushare(ts_code)
            if basic:
                # 补全东方财富搜索没有的字段
                if not item.get("company") and basic.get("management"):
                    item["company"] = basic["management"]
                if basic.get("found_date") and basic["found_date"] != "None":
                    item["inception_date"] = basic["found_date"]
                if basic.get("benchmark"):
                    item["benchmark"] = basic["benchmark"]
                # Tushare的fund_type更权威
                if basic.get("fund_type"):
                    item["fund_type_tushare"] = basic["fund_type"]
                # 根据投资类型推断风险等级
                invest_type = basic.get("invest_type", "")
                if invest_type in ("股票型",):
                    item["risk_level"] = "R4"
                elif invest_type in ("混合型",):
                    item["risk_level"] = "R3"
                elif invest_type in ("债券型",):
                    item["risk_level"] = "R2"
                elif invest_type in ("货币型",):
                    item["risk_level"] = "R1"
                elif invest_type in ("指数型",):
                    item["risk_level"] = "R3"
        return em_result

    # 第二级：Tushare fund_basic（仅支持代码精确搜索或类型过滤）
    try:
        from app.utils.data_source import data_source
        if data_source._tushare_pro:
            # 如果keyword是6位数字，尝试精确查询
            if keyword and len(keyword) == 6 and keyword.isdigit():
                ts_code = code_to_tushare(keyword)
                basic = await get_fund_basic_tushare(ts_code)
                if basic:
                    item = {
                        "fund_code": tushare_to_code(basic["ts_code"]),
                        "fund_name": basic["fund_name"],
                        "fund_short_name": basic["fund_name"][:8],
                        "fund_type": basic["fund_type"],
                        "manager": basic.get("management", ""),
                        "company": basic.get("management", ""),
                        "nav": 0.0,
                        "risk_level": "R3",
                        "inception_date": basic.get("found_date", ""),
                        "benchmark": basic.get("benchmark", ""),
                    }
                    return {"items": [item], "total": 1, "page": 1, "page_size": page_size}
    except Exception as e:
        logger.warning("Tushare降级搜索失败: %s", e)

    # 第三级：返回空结果（不再用Mock）
    return {"items": [], "total": 0, "page": page, "page_size": page_size}


# ============================================================
# 8. 组合详情：东方财富估值 + Tushare净值历史
# ============================================================
async def get_fund_detail_combined(code: str) -> Optional[dict]:
    """
    组合基金详情数据：

    1. 东方财富实时估值（盘中估算净值）
    2. Tushare fund_basic（基金基础信息）
    3. Tushare fund_nav（净值历史30天）
    4. 东方财富持仓信息（重仓股代码）

    Returns:
        完整的基金详情字典
    """
    ts_code = code_to_tushare(code)

    # 并行获取
    realtime_task = get_fund_realtime(code)
    basic_task = get_fund_basic_tushare(ts_code)
    nav_task = get_fund_nav_history(ts_code, days=30)
    holdings_task = get_fund_holdings(code)

    realtime, basic, nav_history, holdings = await asyncio.gather(
        realtime_task, basic_task, nav_task, holdings_task,
        return_exceptions=True,
    )

    # 处理异常
    if isinstance(realtime, Exception):
        logger.warning("实时估值获取异常: %s", realtime)
        realtime = None
    if isinstance(basic, Exception):
        logger.warning("基础信息获取异常: %s", basic)
        basic = None
    if isinstance(nav_history, Exception):
        logger.warning("净值历史获取异常: %s", nav_history)
        nav_history = None
    if isinstance(holdings, Exception):
        logger.warning("持仓信息获取异常: %s", holdings)
        holdings = None

    # 组装详情
    result = {
        "fund_code": code,
        "fund_name": "",
        "fund_short_name": "",
        "fund_type": "",
        "manager": "",
        "company": "",
        "inception_date": "",
        "nav": 0.0,
        "accumulated_nav": 0.0,
        "fund_size": 0.0,
        "benchmark": "",
        "tracking_index": "",
        "risk_level": "R3",
        "description": "",
        "daily_return": 0.0,
        "week_return": 0.0,
        "month_return": 0.0,
        "year_return": 0.0,
        # 实时估值
        "realtime": None,
        # 净值历史
        "nav_history": nav_history or [],
        # 持仓
        "top_holdings": holdings or [],
        # 数据来源标记
        "_data_source": "real",
    }

    # 合并实时估值数据
    if realtime:
        result["fund_name"] = result["fund_name"] or realtime.get("fund_name", "")
        result["nav"] = realtime.get("nav", 0.0) or result["nav"]
        result["realtime"] = {
            "estimated_nav": realtime.get("estimated_nav", 0),
            "estimated_change": realtime.get("estimated_change", 0),
            "estimate_time": realtime.get("estimate_time", ""),
        }
        result["daily_return"] = realtime.get("estimated_change", 0.0)

    # 合并基础信息
    if basic:
        result["fund_name"] = result["fund_name"] or basic.get("fund_name", "")
        result["fund_type"] = basic.get("fund_type", "")
        result["manager"] = basic.get("management", "")
        result["company"] = basic.get("management", "")
        result["inception_date"] = basic.get("found_date", "")
        result["benchmark"] = basic.get("benchmark", "")
        result["fund_size"] = 0.0  # Tushare fund_basic不直接返回规模

        # 根据投资类型推断风险等级
        invest_type = basic.get("invest_type", "")
        risk_map = {
            "股票型": "R4", "混合型": "R3", "债券型": "R2",
            "货币型": "R1", "指数型": "R3", "QDII": "R4",
            "FOF": "R3", "商品型": "R4",
        }
        result["risk_level"] = risk_map.get(invest_type, "R3")

    # 从净值历史计算周/月收益
    if nav_history and len(nav_history) >= 2:
        latest = nav_history[-1]
        result["nav"] = result["nav"] or latest.get("nav", 0.0)
        result["accumulated_nav"] = latest.get("accumulated_nav", 0.0)

        # 周收益: 5个交易日前
        if len(nav_history) >= 6:
            week_ago = nav_history[-6]
            if week_ago.get("adj_nav", 0) > 0 and latest.get("adj_nav", 0) > 0:
                result["week_return"] = round(
                    (latest["adj_nav"] / week_ago["adj_nav"] - 1) * 100, 2
                )

        # 月收益: 20个交易日前
        if len(nav_history) >= 21:
            month_ago = nav_history[-21]
            if month_ago.get("adj_nav", 0) > 0 and latest.get("adj_nav", 0) > 0:
                result["month_return"] = round(
                    (latest["adj_nav"] / month_ago["adj_nav"] - 1) * 100, 2
                )

    return result


# ============================================================
# 9. 板块行情：Tushare行业分类 + 腾讯实时行情
# ============================================================
# 申万一级行业 → 中证行业指数代码映射（腾讯可查）
_SW_INDUSTRY_TO_CSI = {
    "801010.SI": ("sz399814", "农林牧渔"),
    "801030.SI": ("sz399813", "基础化工"),
    "801040.SI": ("sh000932", "钢铁"),
    "801050.SI": ("sh000819", "有色金属"),
    "801080.SI": ("sz399811", "电子"),
    "801880.SI": ("sz399932", "汽车"),
    "801110.SI": ("sz399989", "家用电器"),
    "801120.SI": ("sz399971", "食品饮料"),  # 用中证传媒近似
    "801130.SI": ("sz399970", "纺织服饰"),
    "801140.SI": ("sz399816", "轻工制造"),
    "801150.SI": ("sz399975", "医药生物"),
    "801160.SI": ("sh000935", "公用事业"),
    "801170.SI": ("sz399817", "交通运输"),
    "801180.SI": ("sz399986", "银行"),
    "801200.SI": ("sh000934", "房地产"),
    "801210.SI": ("sz399950", "非银金融"),
    "801230.SI": ("sz399971", "综合"),
    "801710.SI": ("sz399812", "建筑材料"),
    "801720.SI": ("sz399809", "建筑装饰"),
    "801730.SI": ("sz399810", "通信"),
    "801740.SI": ("sh000933", "计算机"),
    "801750.SI": ("sz399989", "传媒"),  # 用中证传媒
    "801760.SI": ("sh000937", "国防军工"),
    "801770.SI": ("sz399815", "电力设备"),
    "801780.SI": ("sz399818", "环保"),
    "801790.SI": ("sz399819", "机械设备"),
    "801890.SI": ("sh000929", "煤炭"),
    "801950.SI": ("sh000930", "石油石化"),
    "801960.SI": ("sz399810", "商贸零售"),
    "801970.SI": ("sz399813", "社会服务"),
    "801980.SI": ("sz399970", "美容护理"),
}

# 热门概念板块 → 腾讯可查指数代码
_CONCEPT_SECTORS = {
    "白酒": "sz399997",
    "新能源车": "sz399976",
    "锂电池": "sz399928",
    "半导体": "sz399959",
    "人工智能": "sh000938",
    "光伏": "sz399808",
    "军工": "sz399967",
    "医药": "sz399975",
    "消费": "sz399932",
    "芯片": "sz399959",
    "5G": "sz399941",
    "碳中和": "sh000960",
    "稀土": "sz399810",
    "医美": "sz399970",
    "机器人": "sz399997",
    "数字经济": "sh000938",
    "元宇宙": "sz399971",
    "储能": "sz399808",
    "氢能源": "sz399808",
    "CRO": "sz399975",
}


def _safe_float(val) -> Optional[float]:
    """安全转换为float"""
    if val is None or val == "-":
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None


def _parse_tencent_quote(raw: str) -> Optional[dict]:
    """
    解析腾讯行情数据
    格式: v_code="1~名称~代码~当前价~昨收~今开~成交量~..."
    字段用~分隔，第4=当前价, 第5=昨收, 第32=涨跌额, 第33=涨跌幅, 第34=最高, 第35=最低
    """
    if not raw or '="' not in raw:
        return None

    # 去掉变量名部分
    parts = raw.split('="', 1)
    if len(parts) < 2:
        return None
    content = parts[1].rstrip('";')

    if content in ("", "0", "1"):
        return None

    fields = content.split("~")
    if len(fields) < 40:
        return None

    try:
        name = fields[1]
        code = fields[2]
        current = _safe_float(fields[3])
        prev_close = _safe_float(fields[4])
        open_price = _safe_float(fields[5])
        volume = _safe_float(fields[6])  # 手
        amount = _safe_float(fields[37]) if len(fields) > 37 else None  # 万元
        change_amt = _safe_float(fields[31])
        change_pct = _safe_float(fields[32])
        high = _safe_float(fields[33])
        low = _safe_float(fields[34])
        turnover = _safe_float(fields[38]) if len(fields) > 38 else None  # 换手率%

        return {
            "name": name,
            "code": code,
            "price": current,
            "prev_close": prev_close,
            "open": open_price,
            "high": high,
            "low": low,
            "change_amt": change_amt,
            "change_pct": change_pct,
            "volume": volume,
            "amount": amount,
            "turnover": turnover,
        }
    except (IndexError, ValueError) as e:
        logger.debug("腾讯行情解析失败: %s", e)
        return None


async def get_sector_list(
    sector_type: str = "industry",
    page: int = 1,
    page_size: int = 20,
    sort_by: str = "change_pct",
    sort_order: str = "desc",
) -> dict:
    """
    获取板块行情列表

    数据源：Tushare行业分类 + 腾讯实时行情
    - industry: 31个申万一级行业
    - concept: 热门概念板块

    Args:
        sector_type: "industry" 或 "concept"
        page: 页码(1-based)
        page_size: 每页条数
        sort_by: 排序字段 change_pct
        sort_order: asc/desc
    """
    cache_k = _cache_key("sector_list", sector_type, str(page), str(page_size), sort_by, sort_order)
    cached = await cache_get(cache_k)
    if cached is not None:
        return cached

    # 选择数据源
    if sector_type == "industry":
        sector_map = _SW_INDUSTRY_TO_CSI
    else:
        sector_map = {f"CONC_{k}": (v, k) for k, v in _CONCEPT_SECTORS.items()}

    # 批量获取腾讯实时行情（每次最多30个）
    tencent_codes = []
    name_map = {}
    for sw_code, (tencent_code, name) in sector_map.items():
        tencent_codes.append(tencent_code)
        name_map[tencent_code] = {"name": name, "sw_code": sw_code}

    items = []
    # 分批查询
    batch_size = 30
    for i in range(0, len(tencent_codes), batch_size):
        batch = tencent_codes[i:i + batch_size]
        query = ",".join(batch)
        try:
            async with httpx.AsyncClient(timeout=10, headers={"User-Agent": "Mozilla/5.0"}) as client:
                resp = await client.get(f"http://qt.gtimg.cn/q={query}")
                text = resp.text

            for line in text.strip().split(";"):
                line = line.strip()
                if not line:
                    continue
                parsed = _parse_tencent_quote(line)
                if parsed:
                    tencent_code = parsed["code"]
                    meta = name_map.get(tencent_code, {})
                    items.append({
                        "code": meta.get("sw_code", tencent_code),
                        "name": meta.get("name", parsed["name"]),
                        "price": parsed["price"],
                        "change_pct": parsed["change_pct"],
                        "change_amt": parsed["change_amt"],
                        "volume": parsed["volume"],
                        "amount": parsed["amount"],
                        "turnover": parsed["turnover"],
                        "high": parsed["high"],
                        "low": parsed["low"],
                    })
        except Exception as e:
            logger.warning("腾讯行情批量获取失败: %s", e)

    # 排序
    reverse = sort_order == "desc"
    if sort_by == "change_pct":
        items.sort(key=lambda x: x.get("change_pct") or 0, reverse=reverse)
    elif sort_by == "amount":
        items.sort(key=lambda x: x.get("amount") or 0, reverse=reverse)

    # 分页
    total = len(items)
    start = (page - 1) * page_size
    end = start + page_size
    paged = items[start:end]

    result = {
        "items": paged,
        "total": total,
        "page": page,
        "page_size": page_size,
        "sector_type": sector_type,
    }

    # 缓存60秒（盘中频繁刷新）
    await cache_set(cache_k, result, ttl=60)
    return result


async def get_sector_detail(code: str) -> Optional[dict]:
    """
    获取单个板块的实时行情详情

    Args:
        code: 行业指数代码(如 sz399986) 或板块代码(如 801180.SI)

    Returns:
        {"code": str, "name": str, "price": float, ...}
    """
    cache_k = _cache_key("sector_detail", code)
    cached = await cache_get(cache_k)
    if cached is not None:
        return cached

    # 查找腾讯代码
    tencent_code = code
    name = ""

    # 如果是申万代码，映射到腾讯代码
    if code in _SW_INDUSTRY_TO_CSI:
        tencent_code, name = _SW_INDUSTRY_TO_CSI[code]
    elif code.startswith("CONC_"):
        concept_name = code[5:]
        if concept_name in _CONCEPT_SECTORS:
            tencent_code = _CONCEPT_SECTORS[concept_name]
            name = concept_name

    try:
        async with httpx.AsyncClient(timeout=10, headers={"User-Agent": "Mozilla/5.0"}) as client:
            resp = await client.get(f"http://qt.gtimg.cn/q={tencent_code}")
            parsed = _parse_tencent_quote(resp.text)

        if not parsed:
            return None

        result = {
            "code": code,
            "tencent_code": tencent_code,
            "name": name or parsed["name"],
            "price": parsed["price"],
            "prev_close": parsed["prev_close"],
            "open": parsed["open"],
            "high": parsed["high"],
            "low": parsed["low"],
            "change_amt": parsed["change_amt"],
            "change_pct": parsed["change_pct"],
            "volume": parsed["volume"],
            "amount": parsed["amount"],
            "turnover": parsed["turnover"],
        }

        # 缓存5分钟
        await cache_set(cache_k, result, ttl=300)
        return result

    except Exception as e:
        logger.warning("板块详情获取失败(%s): %s", code, e)
        return None
