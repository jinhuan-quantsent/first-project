"""
下载历史数据脚本（方案B回测用）
使用 Tushare 拉取2025-2026年的基金净值数据
"""
import os
import json
import logging
from datetime import datetime, timedelta
from typing import List, Dict

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def download_fund_nav_data(fund_code: str, start_date: str = "20250101", end_date: str = "20260620") -> List[Dict]:
    """
    下载单个基金的净值历史数据
    
    Args:
        fund_code: 基金代码，例如 "110022"
        start_date: 起始日期，格式 "YYYYMMDD"
        end_date: 结束日期，格式 "YYYYMMDD"
    
    Returns:
        净值历史数据列表
    """
    try:
        import tushare as ts
        
        # 加载 token
        token = os.getenv("TUSHARE_TOKEN")
        if not token:
            logger.error("未配置 TUSHARE_TOKEN")
            return []
        
        ts.set_token(token)
        pro = ts.pro_api()
        
        # 转换基金代码格式
        if not fund_code.endswith(".OF"):
            ts_code = f"{fund_code}.OF"
        else:
            ts_code = fund_code
        
        logger.info(f"正在下载 {fund_code} 的净值数据（{start_date} 至 {end_date}）...")
        
        # 调用 Tushare API
        df = pro.fund_nav(ts_code=ts_code, start_date=start_date, end_date=end_date)
        
        if df is None or len(df) == 0:
            logger.warning(f"基金 {fund_code} 无数据")
            return []
        
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
        
        logger.info(f"✅ 下载 {fund_code} 成功，共 {len(data)} 条数据")
        return data
        
    except Exception as e:
        logger.error(f"❌ 下载 {fund_code} 失败：{e}")
        return []

def download_multiple_funds(fund_codes: List[str], output_dir: str = "historical_data"):
    """
    下载多个基金的历史数据
    
    Args:
        fund_codes: 基金代码列表
        output_dir: 输出目录
    """
    # 创建输出目录
    os.makedirs(output_dir, exist_ok=True)
    
    # 加载 .env 文件
    from dotenv import load_dotenv
    load_dotenv()
    
    # 下载每个基金的数据
    for fund_code in fund_codes:
        data = download_fund_nav_data(fund_code)
        
        if data:
            # 保存到 JSON 文件
            output_file = os.path.join(output_dir, f"{fund_code}.json")
            with open(output_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            logger.info(f"数据已保存到 {output_file}")
        else:
            logger.warning(f"基金 {fund_code} 无数据，跳过保存")

def main():
    """主函数"""
    # 从 fund_category_map.json 读取基金列表
    fund_map_file = "backend/app/data/fund_category_map.json"
    
    if os.path.exists(fund_map_file):
        with open(fund_map_file, "r", encoding="utf-8") as f:
            fund_map = json.load(f)
        # 从 fund_mapping 数组中读取基金代码
        fund_codes = [item["code"] for item in fund_map.get("fund_mapping", [])]
        logger.info(f"从 {fund_map_file} 读取到 {len(fund_codes)} 个基金代码")
    else:
        # 默认基金列表
        fund_codes = [
            "110022",  # 易方达消费行业
            "510300",  # 沪深300ETF
            "510500",  # 中证500ETF
            "159915",  # 创业板ETF
            "512690",  # 酒ETF
            "512480",  # 半导体ETF
            "515790",  # 光伏ETF
            "512660",  # 军工ETF
            "510880",  # 红利ETF
        ]
        logger.info(f"使用默认基金列表，共 {len(fund_codes)} 个基金")
    
    # 下载数据
    output_dir = "historical_data"
    download_multiple_funds(fund_codes, output_dir)
    
    logger.info(f"\n✅ 所有数据已下载到 {output_dir}/ 目录")

if __name__ == "__main__":
    main()
