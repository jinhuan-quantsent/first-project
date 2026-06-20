"""
历史数据获取工具（方案B）- 使用AKShare申万行业指数
支持：
1. 申万一级行业指数历史数据（稳定、规范）
2. 行业列表动态获取
3. 模拟数据兜底
"""

import logging
from datetime import datetime, timedelta
from typing import List, Dict, Optional
import random

logger = logging.getLogger(__name__)

# 申万一级行业代码到名称的映射（常用行业）
SW_INDUSTRY_MAPPING = {
    "801010": "农林牧渔I",
    "801030": "基础化工I",
    "801040": "钢铁I",
    "801050": "有色金属I",
    "801080": "建筑材料I",
    "801110": "家用电器I",
    "801120": "食品饮料I",
    "801130": "纺织服饰I",
    "801140": "轻工制造I",
    "801150": "医药生物I",
    "801160": "公用事业I",
    "801170": "交通运输I",
    "801180": "房地产I",
    "801200": "商贸零售I",
    "801210": "社会服务I",
    "801220": "综合I",
    "801230": "建筑材料I",
    "801710": "建筑材料I",
    "801720": "建筑装饰I",
    "801730": "电力设备I",
    "801740": "国防军工I",
    "801750": "计算机I",
    "801760": "传媒I",
    "801770": "通信I",
    "801780": "银行I",
    "801790": "非银金融I",
    "801880": "汽车I",
    "801890": "机械设备I",
}


def fetch_index_hist(index_code: str, days: int = 60) -> List[Dict]:
    """
    获取指数历史数据（支持沪深300、上证指数等）
    使用AKShare指数历史数据接口
    
    Args:
        index_code: 指数代码，例如 "000300"（沪深300）、"000001"（上证指数）
        days: 获取最近N天的数据
    
    Returns:
        历史数据列表，每个元素包含 date, close, change_pct
    """
    try:
        import akshare as ak
        
        # 获取指数历史数据
        df = ak.index_hist_cg(symbol=index_code, period="day")
        
        if df is None or df.empty:
            logger.warning(f"AKShare获取指数 {index_code} 历史数据失败")
            return []
        
        # 转换为标准格式
        data = []
        for _, row in df.iterrows():
            data.append({
                "date": row["日期"].strftime("%Y-%m-%d"),
                "close": float(row["收盘"]),
                "change_pct": float(row["涨跌幅"]) if "涨跌幅" in row else 0.0
            })
        
        # 返回最近N天的数据
        return data[-days:]
    except Exception as e:
        logger.error(f"获取指数 {index_code} 历史数据失败: {e}")
        return []


def fetch_sw_industry_list() -> List[Dict]:
    """
    获取申万一级行业列表（动态从AKShare获取）
    """
    try:
        import akshare as ak
        
        # 获取申万一级行业实时行情
        df = ak.index_realtime_sw()
        
        if df is None or df.empty:
            logger.warning("AKShare获取申万行业列表失败，返回缓存")
            return _get_cached_industry_list()
        
        # 转换为标准格式
        industry_list = []
        for _, row in df.iterrows():
            industry_info = {
                "code": str(row["指数代码"]),
                "name": row["指数名称"],
                "current": float(row["最新价"]),
                "change_pct": _calculate_change_pct(row),
            }
            industry_list.append(industry_info)
        
        logger.info(f"✅ 获取申万一级行业列表成功，共 {len(industry_list)} 个")
        return industry_list
        
    except Exception as e:
        logger.error(f"❌ 获取申万行业列表失败: {e}")
        return _get_cached_industry_list()


def fetch_sw_industry_hist(symbol: str, days: int = 60) -> List[Dict]:
    """
    获取申万行业指数历史数据（AKShare真实数据）
    
    Args:
        symbol: 行业指数代码，例如 "801730"（电力设备）
        days: 获取最近N天的数据
    
    Returns:
        历史数据列表，每个元素包含 date, close, change_pct
    """
    try:
        import akshare as ak
        
        # 获取历史数据
        df = ak.index_hist_sw(symbol=symbol)
        
        if df is None or df.empty:
            logger.warning(f"AKShare获取 {symbol} 历史数据失败，返回模拟数据")
            return _generate_mock_industry_data(symbol, days)
        
        # 只保留最近N天
        df = df.tail(days)
        
        # 转换为标准格式
        hist_data = []
        for _, row in df.iterrows():
            hist_data.append({
                "date": str(row["日期"]),
                "close": float(row["收盘"]),
                "change_pct": float(row["涨跌幅"]) if "涨跌幅" in row else 0.0,
                "volume": float(row["成交量"]) if "成交量" in row else 0.0,
                "amount": float(row["成交额"]) if "成交额" in row else 0.0,
            })
        
        logger.info(f"✅ 获取 {symbol} 历史数据成功，共 {len(hist_data)} 条")
        return hist_data
        
    except Exception as e:
        logger.error(f"❌ 获取 {symbol} 历史数据失败: {e}")
        return _generate_mock_industry_data(symbol, days)


def fetch_sector_historical_data(sector_code: str, days: int = 60) -> List[Dict]:
    """
    获取板块指数历史数据（兼容旧接口）
    
    注意：这个函数现在使用申万行业指数数据
    如果需要概念板块数据，请使用 fetch_sw_industry_hist()
    """
    logger.info(f"获取板块 {sector_code} 的历史数据（{days}天）")
    
    # 优先使用申万行业指数
    if sector_code.startswith("801"):
        # 申万行业指数代码（801xxx）
        return fetch_sw_industry_hist(sector_code, days)
    else:
        # 其他代码，尝试作为申万行业代码
        logger.warning(f"不支持的板块代码格式: {sector_code}，尝试作为申万行业代码")
        return fetch_sw_industry_hist(sector_code, days)


def calculate_sector_filter(sector_code: str) -> Dict:
    """
    计算板块过滤器信号（方案B）
    
    Args:
        sector_code: 板块代码
    
    Returns:
        包含 up_days_ratio, relative_strength, trend_position, build_signal 的字典
    """
    try:
        # 获取历史数据
        hist_data = fetch_sector_historical_data(sector_code, days=60)
        
        if not hist_data or len(hist_data) < 20:
            logger.warning(f"板块 {sector_code} 历史数据不足，返回默认值")
            return _default_filter_result()
        
        # 计算上涨天数占比
        up_days = sum(1 for d in hist_data[-20:] if d.get("change_pct", 0) > 0)
        up_days_ratio = up_days / 20
        
        # 计算相对强度（板块涨跌幅 - 市场平均涨跌幅）
        sector_change = sum(d.get("change_pct", 0) for d in hist_data[-20:]) / 20
        market_change = 0.0  # 简化：假设市场平均涨跌幅为0
        relative_strength = (sector_change - market_change) / 100  # 转换为小数
        
        # 判断趋势位置
        trend_position = _determine_trend_position(hist_data)
        
        # 生成建仓信号
        build_signal = _generate_build_signal(up_days_ratio, relative_strength, trend_position)
        
        return {
            "up_days_ratio": round(up_days_ratio, 3),
            "relative_strength": round(relative_strength, 3),
            "trend_position": trend_position,
            "build_signal": build_signal,
        }
        
    except Exception as e:
        logger.error(f"计算板块过滤器信号失败: {e}")
        return _default_filter_result()


def fetch_fund_nav_history(fund_code: str, days: int = 60) -> List[Dict]:
    """
    获取基金净值历史数据（方案B）
    优先级：A（Tushare） → D（模拟数据）
    
    Args:
        fund_code: 基金代码，例如 "110022"
        days: 获取最近N天的数据
    
    Returns:
        净值历史数据列表，每个元素包含 date, nav, change_pct
    """
    logger.info(f"获取基金 {fund_code} 的净值历史数据（{days}天）")
    
    # 优先级A - Tushare获取真实净值数据
    try:
        import tushare as ts
        import os
        from dotenv import load_dotenv
        
        # 加载环境变量
        load_dotenv()
        token = os.getenv("TUSHARE_TOKEN")
        
        if token:
            ts.set_token(token)
            pro = ts.pro_api()
            
            # 转换基金代码格式（110022 → 110022.OF）
            if not fund_code.endswith(".OF"):
                ts_code = f"{fund_code}.OF"
            else:
                ts_code = fund_code
            
            # 计算起始日期
            from datetime import datetime, timedelta
            end_date = datetime.now().strftime("%Y%m%d")
            start_date = (datetime.now() - timedelta(days=days*2)).strftime("%Y%m%d")  # 多拉一些数据
            
            # 调用 Tushare API
            df = pro.fund_nav(ts_code=ts_code, start_date=start_date, end_date=end_date)
            
            if df is not None and len(df) > 0:
                # 转换为标准格式
                data = []
                prev_nav = None
                for _, row in df.iterrows():
                    unit_nav = float(row["unit_nav"])
                    nav_date = str(row["nav_date"])
                    
                    # 计算涨跌幅
                    change_pct = 0.0
                    if prev_nav is not None and prev_nav > 0:
                        change_pct = (unit_nav - prev_nav) / prev_nav * 100
                    prev_nav = unit_nav
                    
                    data.append({
                        "date": nav_date,
                        "nav": unit_nav,
                        "change_pct": round(change_pct, 2)
                    })
                
                # 返回最近N天的数据
                logger.info(f"✅ Tushare获取 {fund_code} 净值数据成功，共 {len(data)} 条")
                return data[-days:]
            else:
                logger.warning(f"Tushare获取 {fund_code} 数据为空，降级到模拟数据")
        else:
            logger.warning("未配置 TUSHARE_TOKEN，降级到模拟数据")
    except ImportError:
        logger.warning("未安装 tushare 包，降级到模拟数据")
    except Exception as e:
        logger.error(f"Tushare获取 {fund_code} 失败：{e}，降级到模拟数据")
    
    # 优先级D：返回模拟数据
    logger.info(f"返回模拟数据：{fund_code}")
    return _generate_mock_nav_data(fund_code, days)


def _calculate_change_pct(row) -> float:
    """计算涨跌幅"""
    try:
        current = float(row["最新价"])
        yesterday = float(row["昨收盘"])
        if yesterday > 0:
            return round((current - yesterday) / yesterday * 100, 2)
        return 0.0
    except:
        return 0.0


def _determine_trend_position(hist_data: List[Dict]) -> str:
    """判断趋势位置"""
    if len(hist_data) < 20:
        return "未知"
    
    # 计算短期（5日）和长期（20日）均线
    recent_5 = [d.get("close", 0) for d in hist_data[-5:]]
    recent_20 = [d.get("close", 0) for d in hist_data[-20:]]
    
    ma5 = sum(recent_5) / len(recent_5)
    ma20 = sum(recent_20) / len(recent_20)
    
    current_price = hist_data[-1].get("close", 0)
    
    # 判断趋势
    if current_price > ma5 > ma20:
        return "上升趋势"
    elif current_price < ma5 < ma20:
        return "下降趋势"
    elif abs(ma5 - ma20) / ma20 < 0.02:
        return "震荡"
    else:
        return "趋势不明"


def _generate_build_signal(up_days_ratio: float, relative_strength: float, trend_position: str) -> str:
    """生成建仓信号"""
    # 适合建仓：上涨天数占比高、相对强度强、趋势向上
    if up_days_ratio >= 0.6 and relative_strength >= 0 and trend_position in ["上升趋势", "震荡"]:
        return "适合建仓"
    
    # 谨慎建仓：条件中等
    if up_days_ratio >= 0.5 and relative_strength >= -0.02:
        return "谨慎建仓"
    
    # 暂不建仓：条件差
    return "暂不建仓"


def _default_filter_result() -> Dict:
    """返回默认的过滤器结果"""
    return {
        "up_days_ratio": 0.0,
        "relative_strength": 0.0,
        "trend_position": "未知",
        "build_signal": "暂不建仓",
    }


def _get_cached_industry_list() -> List[Dict]:
    """获取缓存的行业列表（模拟数据）"""
    cached = []
    for code, name in SW_INDUSTRY_MAPPING.items():
        cached.append({
            "code": code,
            "name": name,
            "current": 1000.0,
            "change_pct": 0.0,
        })
    return cached


def _generate_mock_industry_data(sector_code: str, days: int) -> List[Dict]:
    """生成模拟行业历史数据"""
    data = []
    base_price = 1000.0
    
    for i in range(days, 0, -1):
        date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        price_change = random.uniform(-0.05, 0.05)
        base_price *= (1 + price_change)
        
        data.append({
            "date": date,
            "close": round(base_price, 2),
            "change_pct": round(price_change * 100, 2),
            "volume": random.uniform(50, 200),
            "amount": random.uniform(1000, 5000),
        })
    
    return data


def _generate_mock_nav_data(fund_code: str, days: int) -> List[Dict]:
    """生成模拟基金净值历史数据"""
    data = []
    base_nav = 1.0
    
    for i in range(days, 0, -1):
        date = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        nav_change = random.uniform(-0.03, 0.03)
        base_nav *= (1 + nav_change)
        
        data.append({
            "date": date,
            "nav": round(base_nav, 4),
            "change_pct": round(nav_change * 100, 2)
        })
    
    return data


if __name__ == "__main__":
    # 测试代码
    logging.basicConfig(level=logging.INFO)
    
    # 测试获取行业列表
    print("=" * 50)
    print("测试1：获取申万一级行业列表")
    industry_list = fetch_sw_industry_list()
    print(f"获取到 {len(industry_list)} 个行业")
    if industry_list:
        print("前3个行业：")
        for item in industry_list[:3]:
            print(item)
    
    # 测试获取行业历史数据
    print("\n" + "=" * 50)
    print("测试2：获取电力设备行业历史数据（801730）")
    hist_data = fetch_sw_industry_hist("801730", days=30)
    print(f"获取到 {len(hist_data)} 条数据")
    if hist_data:
        print("前3条数据：")
        for item in hist_data[:3]:
            print(item)
    
    # 测试计算板块过滤器
    print("\n" + "=" * 50)
    print("测试3：计算板块过滤器信号（801730）")
    filter_result = calculate_sector_filter("801730")
    print(f"过滤器结果：{filter_result}")
