"""
方案B A/B测试回测脚本（使用真实信号）

功能：
1. 回测对照组（A组：原始V5.0）和实验组（B组：方案B）
2. 使用真实历史净值数据计算情绪信号（非随机）
3. 计算收益率、回撤、夏普比率、胜率
4. 生成对比报告
"""

import json
import os
import sys
from datetime import datetime, timedelta
from typing import List, Dict, Tuple

# 设置输出编码为 UTF-8（解决 Windows 控制台编码问题）
sys.stdout.reconfigure(encoding='utf-8')
sys.stderr.reconfigure(encoding='utf-8')

# ============================================================
# 配置
# ============================================================

# 测试标的（只使用有真实数据的基金）
FUND_POOL = [
    {"code": "110022", "name": "易方达消费行业", "category": "sector"},
    {"code": "001630", "name": "天弘中证食品饮料", "category": "sector"},
    {"code": "002560", "name": "诺安和鑫行业", "category": "sector"},  # 半导体
    {"code": "320007", "name": "诺安成长", "category": "sector"},  # 半导体
    {"code": "003096", "name": "天弘中证证券保险", "category": "sector"},
]

# 回测参数
INITIAL_CASH = 100000  # 初始资金
MAX_POSITION_VALUE = 20000  # 单次建仓上限（20%）
MAX_HOLDING_COUNT = 5  # 最大持仓数
TRADE_COST = 0.0015  # 交易成本（单边0.15%）
BACKTEST_START = "2025-01-02"
BACKTEST_END = "2026-06-18"
HISTORICAL_DATA_DIR = "historical_data"  # 真实历史数据目录


# ============================================================
# 真实历史数据加载器
# ============================================================

def load_historical_nav(fund_code: str) -> Dict[str, float]:
    """
    从 historical_data/ 目录加载真实净值数据
    
    如果本地文件不存在，自动从 Tushare 拉取并保存
    
    Returns:
        日期到净值的映射字典，例如 {"2025-01-02": 3.358, "2025-01-03": 3.325}
    """
    data_file = os.path.join(HISTORICAL_DATA_DIR, f"{fund_code}.json")
    
    # 如果本地文件不存在，自动拉取
    if not os.path.exists(data_file):
        print(f"⚠️ 基金 {fund_code} 的本地数据不存在，自动从 Tushare 拉取...")
        _auto_download_fund_nav(fund_code)
    
    if not os.path.exists(data_file):
        print(f"❌ 基金 {fund_code} 数据拉取失败")
        return {}
    
    try:
        with open(data_file, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        # 转换为日期到净值的映射（统一格式为 YYYY-MM-DD）
        nav_map = {}
        for item in data:
            # 确保日期格式是 YYYY-MM-DD
            date_str = item["date"]
            if len(date_str) == 8 and "-" not in date_str:
                # YYYYMMDD 格式，转换为 YYYY-MM-DD
                date_str = f"{date_str[:4]}-{date_str[4:6]}-{date_str[6:8]}"
            
            nav_map[date_str] = item["nav"]
        
        return nav_map
        
    except Exception as e:
        print(f"❌ 加载 {fund_code} 历史数据失败：{e}")
        return {}


def _auto_download_fund_nav(fund_code: str, start_date: str = "20250101", end_date: str = "20260620"):
    """
    自动从 Tushare 下载基金净值数据并保存
    
    Args:
        fund_code: 基金代码，例如 "110022"
        start_date: 起始日期，格式 "YYYYMMDD"
        end_date: 结束日期，格式 "YYYYMMDD"
    """
    try:
        from dotenv import load_dotenv
        load_dotenv()
        import os
        import tushare as ts
        
        token = os.getenv("TUSHARE_TOKEN")
        if not token:
            print("❌ 未配置 TUSHARE_TOKEN")
            return
        
        ts.set_token(token)
        pro = ts.pro_api()
        
        # 转换基金代码格式
        if not fund_code.endswith(".OF"):
            ts_code = f"{fund_code}.OF"
        else:
            ts_code = fund_code
        
        print(f"📥 正在从 Tushare 下载 {fund_code} 的净值数据...")
        df = pro.fund_nav(ts_code=ts_code, start_date=start_date, end_date=end_date)
        
        if df is not None and len(df) > 0:
            # 转换为标准格式
            data = []
            prev_nav = None
            for _, row in df.iterrows():
                unit_nav = float(row["unit_nav"])
                nav_date = str(row["nav_date"])
                
                # 确保日期格式是 YYYY-MM-DD
                if len(nav_date) == 8 and "-" not in nav_date:
                    nav_date = f"{nav_date[:4]}-{nav_date[4:6]}-{nav_date[6:8]}"
                
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
            
            # 保存到文件
            data_file = os.path.join(HISTORICAL_DATA_DIR, f"{fund_code}.json")
            os.makedirs(os.path.dirname(data_file), exist_ok=True)
            
            with open(data_file, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            
            print(f"✅ 自动下载 {fund_code} 成功，共 {len(data)} 条数据")
        else:
            print(f"⚠️ Tushare 返回空数据：{fund_code}")
    
    except ImportError:
        print("❌ 未安装 tushare 包")
    except Exception as e:
        print(f"❌ 自动下载 {fund_code} 失败：{e}")


# ============================================================
# 技术指标计算函数
# ============================================================

def calculate_ma(nav_list: List[float], window: int) -> float:
    """计算移动平均线"""
    if len(nav_list) < window:
        return nav_list[-1] if nav_list else 0.0
    return sum(nav_list[-window:]) / window


def calculate_rsi(nav_list: List[float], period: int = 14) -> float:
    """计算RSI相对强弱指数"""
    if len(nav_list) < period + 1:
        return 50.0  # 数据不足，返回中性值
    
    gains = []
    losses = []
    
    for i in range(1, len(nav_list)):
        change = nav_list[i] - nav_list[i-1]
        if change > 0:
            gains.append(change)
        else:
            losses.append(abs(change))
    
    avg_gain = sum(gains[-period:]) / period if len(gains) >= period else 0
    avg_loss = sum(losses[-period:]) / period if len(losses) >= period else 0
    
    if avg_loss == 0:
        return 100.0
    
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    
    return rsi


def calculate_macd(nav_list: List[float]) -> Tuple[float, float, str]:
    """
    计算MACD指标
    
    Returns:
        (macd_line, signal_line, signal_str)
    """
    if len(nav_list) < 26:
        return 0.0, 0.0, "中性"
    
    # 计算EMA
    ema12 = calculate_ema(nav_list, 12)
    ema26 = calculate_ema(nav_list, 26)
    
    macd_line = ema12 - ema26
    
    # 简化：signal_line = macd_line的9日EMA
    signal_line = macd_line * 0.9  # 简化计算
    
    if macd_line > signal_line:
        signal_str = "金叉"
    elif macd_line < signal_line:
        signal_str = "死叉"
    else:
        signal_str = "中性"
    
    return macd_line, signal_line, signal_str


def calculate_ema(nav_list: List[float], period: int) -> float:
    """计算指数移动平均线（简化版）"""
    if len(nav_list) < period:
        return nav_list[-1] if nav_list else 0.0
    
    # 简化：使用简单平均代替EMA
    return sum(nav_list[-period:]) / period


def calculate_volatility(nav_list: List[float], window: int = 20) -> float:
    """计算波动率（年化）"""
    if len(nav_list) < window + 1:
        return 0.0
    
    returns = [(nav_list[i] - nav_list[i-1]) / nav_list[i-1] for i in range(1, len(nav_list))]
    
    # 20日波动率（年化）
    avg_return = sum(returns[-window:]) / window
    variance = sum((r - avg_return) ** 2 for r in returns[-window:]) / window
    volatility = (variance ** 0.5) * (252 ** 0.5)  # 年化
    
    return volatility


# ============================================================
# 真实信号生成器（基于历史净值数据）
# ============================================================

def generate_real_sentiment(fund_code: str, date: str) -> Dict:
    """
    生成真实情绪信号（基于历史净值数据）
    
    计算4个因子：
    1. 趋势因子（MA20）：当前净值 vs MA20
    2. 动量因子（RSI）：相对强弱指数
    3. 波动率因子：20日波动率
    4. MACD因子：MACD金叉/死叉
    
    Returns:
        {"signal": "S+/S/A/B/C/D/E", "score": int, "suggested_position": float, "details": dict}
    """
    # 加载历史净值数据
    nav_map = load_historical_nav(fund_code)
    
    if not nav_map:
        return {"signal": "C", "score": 50, "suggested_position": 0.10, "details": {}}
    
    # 获取历史净值序列
    dates = sorted([d for d in nav_map.keys() if d <= date])
    
    if len(dates) < 30:
        return {"signal": "C", "score": 50, "suggested_position": 0.10, "details": {}}
    
    nav_list = [nav_map[d] for d in dates]
    
    # 1. 趋势因子（MA20）
    ma20 = calculate_ma(nav_list, 20)
    current_nav = nav_list[-1]
    trend_score = (current_nav - ma20) / ma20 * 100  # 转为百分比
    
    # 2. 动量因子（RSI）
    rsi = calculate_rsi(nav_list, 14)
    rsi_score = (rsi - 50) * 2  # 转为 -100 到 +100
    
    # 3. 波动率因子
    volatility = calculate_volatility(nav_list, 20)
    volatility_score = -volatility * 10  # 波动率越高，分数越低
    
    # 4. MACD因子
    macd_line, signal_line, macd_signal = calculate_macd(nav_list)
    macd_score = 20 if macd_signal == "金叉" else -20
    
    # 综合评分（-100 到 +100）
    score = 0
    score += trend_score * 2  # 趋势因子权重 2
    score += rsi_score * 1.5  # RSI因子权重 1.5
    score += volatility_score  # 波动率因子权重 1
    score += macd_score  # MACD因子权重 1
    
    # 限制在 [-100, +100]
    score = max(-100, min(100, score))
    
    # 映射到信号等级
    if score >= 80:
        signal = "S+"
        suggested_position = 0.30
    elif score >= 60:
        signal = "S"
        suggested_position = 0.25
    elif score >= 40:
        signal = "A"
        suggested_position = 0.20
    elif score >= 20:
        signal = "B"
        suggested_position = 0.15
    elif score >= 0:
        signal = "C"
        suggested_position = 0.10
    elif score >= -40:
        signal = "D"
        suggested_position = 0.05
    else:
        signal = "E"
        suggested_position = 0.0
    
    return {
        "signal": signal,
        "score": int(score),
        "suggested_position": suggested_position,
        "details": {
            "trend_score": round(trend_score, 2),
            "rsi": round(rsi, 2),
            "volatility": round(volatility, 4),
            "macd_signal": macd_signal,
            "ma20": round(ma20, 4),
            "current_nav": round(current_nav, 4)
        }
    }


def generate_real_sector_filter(fund_code: str, date: str) -> Dict:
    """
    生成真实板块过滤器结果（基于历史净值数据）
    
    使用净值数据判断：
    1. 振幅：20日净值振幅
    2. 交叉次数：MA5和MA20交叉次数
    3. 斜率：MA20的斜率
    
    Returns:
        {"build_signal": "适合建仓/不建议建仓", "trend_position": "上升/下降/震荡", 
         "up_days_ratio": float, "details": dict}
    """
    # 加载历史净值数据
    nav_map = load_historical_nav(fund_code)
    
    if not nav_map:
        return {"build_signal": "适合建仓", "trend_position": "震荡", "up_days_ratio": 0.5, "details": {}}
    
    # 获取历史净值序列
    dates = sorted([d for d in nav_map.keys() if d <= date])
    if len(dates) < 20:
        return {"build_signal": "适合建仓", "trend_position": "震荡", "up_days_ratio": 0.5, "details": {}}
    
    nav_list = [nav_map[d] for d in dates]
    
    # 1. 振幅
    amplitude = (max(nav_list[-20:]) - min(nav_list[-20:])) / min(nav_list[-20:])
    
    # 2. 交叉次数（MA5和MA20）
    cross_count = 0
    for i in range(20, len(nav_list)):
        ma5_prev = calculate_ma(nav_list[i-20:i-1], 5)
        ma20_prev = calculate_ma(nav_list[i-20:i-1], 20)
        ma5_curr = calculate_ma(nav_list[i-19:i], 5)
        ma20_curr = calculate_ma(nav_list[i-19:i], 20)
        
        # 判断交叉
        if (ma5_prev <= ma20_prev and ma5_curr > ma20_curr) or \
           (ma5_prev >= ma20_prev and ma5_curr < ma20_curr):
            cross_count += 1
    
    # 3. 斜率（MA20）
    if len(nav_list) >= 40:
        ma20_start = calculate_ma(nav_list[-40:-20], 20)
        ma20_end = calculate_ma(nav_list[-20:], 20)
        slope = (ma20_end - ma20_start) / ma20_start
    else:
        slope = 0.0
    
    # 判断是否为震荡市
    is_oscillating = (amplitude <= 0.05) and (cross_count >= 3) and (abs(slope) <= 0.003)
    
    # 趋势位置
    ma20 = calculate_ma(nav_list, 20)
    current_nav = nav_list[-1]
    if current_nav > ma20 * 1.02:
        trend_position = "上升"
    elif current_nav < ma20 * 0.98:
        trend_position = "下降"
    else:
        trend_position = "震荡"
    
    # 上涨天数比例
    up_days = sum(1 for i in range(1, len(nav_list)) if nav_list[i] > nav_list[i-1])
    up_days_ratio = up_days / (len(nav_list) - 1) if len(nav_list) > 1 else 0.5
    
    # 建仓信号
    if is_oscillating:
        build_signal = "不建议建仓"  # 震荡市，暂不建仓
    elif trend_position == "下降":
        build_signal = "不建议建仓"  # 下降趋势，暂不建仓
    else:
        build_signal = "适合建仓"
    
    return {
        "build_signal": build_signal,
        "trend_position": trend_position,
        "up_days_ratio": round(up_days_ratio, 2),
        "details": {
            "amplitude": round(amplitude, 4),
            "cross_count": cross_count,
            "slope": round(slope, 4),
            "is_oscillating": is_oscillating
        }
    }


def get_trend_guard_signal(fund_code: str, date: str) -> Dict:
    """
    获取趋势卫士信号（基于历史净值数据）
    
    Returns:
        {"trend": "上升/下降/震荡", "macd": "金叉/死叉/中性", "should_clear": True/False, "details": dict}
    """
    # 加载历史净值数据
    nav_map = load_historical_nav(fund_code)
    
    if not nav_map:
        return {"trend": "未知", "macd": "中性", "should_clear": False, "details": {}}
    
    # 获取历史净值序列
    dates = sorted([d for d in nav_map.keys() if d <= date])
    if len(dates) < 30:
        return {"trend": "未知", "macd": "中性", "should_clear": False, "details": {}}
    
    nav_list = [nav_map[d] for d in dates]
    
    # 计算MA20
    ma20 = calculate_ma(nav_list, 20)
    current_nav = nav_list[-1]
    
    # 判断趋势
    if current_nav > ma20 * 1.02:
        trend = "上升"
    elif current_nav < ma20 * 0.98:
        trend = "下降"
    else:
        trend = "震荡"
    
    # 计算MACD
    macd_line, signal_line, macd_signal = calculate_macd(nav_list)
    
    # 判断是否需要清仓
    should_clear = False
    if trend == "下降" and macd_signal == "死叉":
        should_clear = True
    
    return {
        "trend": trend,
        "macd": macd_signal,
        "should_clear": should_clear,
        "details": {
            "ma20": round(ma20, 4),
            "current_nav": round(current_nav, 4),
            "macd_line": round(macd_line, 6),
            "signal_line": round(signal_line, 6)
        }
    }


# ============================================================
# 回测引擎
# ============================================================

class BacktestEngine:
    """回测引擎"""
    
    def __init__(self, strategy: str):
        """
        strategy: "A" = 对照组, "B" = 实验组
        """
        self.strategy = strategy
        self.cash = INITIAL_CASH
        self.positions = []  # [{fund_code, buy_date, buy_nav, quantity, cost}]
        self.trades = []  # [{date, fund_code, type, price, quantity, cost, pnl}]
        self.nav_curve = []  # [{date, total_value}]
        
    def run(self):
        """运行回测"""
        print(f"\n🚀 开始回测（策略{self.strategy}组）...")
        
        # 生成所有交易日
        trading_days = self._generate_trading_days(BACKTEST_START, BACKTEST_END)
        
        for date in trading_days:
            # 1. 更新持仓市值
            self._update_positions(date)
            
            # 2. 生成交易信号
            signals = self._generate_signals(date)
            
            # 3. 执行交易
            for signal in signals:
                self._execute_trade(signal, date)
            
            # 4. 记录净值
            total_value = self.cash + sum(p["market_value"] for p in self.positions)
            self.nav_curve.append({"date": date, "total_value": total_value})
        
        print(f"✅ 回测完成（策略{self.strategy}组）")
        
        return self._calculate_metrics()
    
    def _generate_trading_days(self, start: str, end: str) -> List[str]:
        """生成交易日列表"""
        start_date = datetime.strptime(start, "%Y-%m-%d")
        end_date = datetime.strptime(end, "%Y-%m-%d")
        
        trading_days = []
        current = start_date
        
        while current <= end_date:
            if current.weekday() < 5:  # 跳过周末
                trading_days.append(current.strftime("%Y-%m-%d"))
            current += timedelta(days=1)
        
        return trading_days
    
    def _update_positions(self, date: str):
        """更新持仓市值"""
        # 加载所有持仓基金的真实净值数据
        for pos in self.positions:
            fund_code = pos["fund_code"]
            
            # 从真实数据文件加载
            nav_map = load_historical_nav(fund_code)
            
            if not nav_map:
                continue
            
            if date in nav_map:
                current_nav = nav_map[date]
                pos["market_value"] = pos["quantity"] * current_nav
            else:
                # 如果当天无数据（周末/节假日），使用最近一天的净值
                available_dates = sorted([d for d in nav_map.keys() if d <= date], reverse=True)
                if available_dates:
                    pos["market_value"] = pos["quantity"] * nav_map[available_dates[0]]
                else:
                    pos["market_value"] = pos["quantity"] * pos["buy_nav"]  # 兜底
    
    def _generate_signals(self, date: str) -> List[Dict]:
        """生成交易信号（包含趋势卫士）"""
        signals = []
        
        # 检查持仓是否需要清仓
        for pos in self.positions[:]:  # 使用副本
            fund_code = pos["fund_code"]
            
            # 对照组（A组）：仅根据情绪信号清仓
            sentiment = generate_real_sentiment(fund_code, date)
            should_clear = False
            
            if sentiment["signal"] in ["D", "E"]:
                should_clear = True
            
            # 实验组（B组）：额外检查趋势卫士
            if self.strategy == "B":
                trend_guard = get_trend_guard_signal(fund_code, date)
                
                # 趋势卫士建议清仓
                if trend_guard["should_clear"]:
                    should_clear = True
                    print(f"  📉 趋势卫士建议清仓 {fund_code}：趋势={trend_guard['trend']}, MACD={trend_guard['macd']}")
            
            if should_clear:
                signals.append({
                    "type": "sell",
                    "fund_code": fund_code,
                    "date": date
                })
        
        # 检查是否需要建仓
        if len(self.positions) < MAX_HOLDING_COUNT:
            for fund in FUND_POOL:
                if any(p["fund_code"] == fund["code"] for p in self.positions):
                    continue  # 已持有
                
                # 对照组（A组）：仅根据情绪信号建仓
                sentiment = generate_real_sentiment(fund["code"], date)
                should_buy = sentiment["signal"] in ["S+", "S", "A", "B", "C"]
                
                # 实验组（B组）：额外检查板块过滤器
                if self.strategy == "B" and should_buy:
                    sector_filter = generate_real_sector_filter(fund["code"], date)
                    if sector_filter["build_signal"] == "不建议建仓":
                        should_buy = False
                        print(f"  🚫 板块过滤器拦截 {fund['code']}：{sector_filter['build_signal']}, 趋势={sector_filter['trend_position']}")
                
                if should_buy:
                    signals.append({
                        "type": "buy",
                        "fund_code": fund["code"],
                        "date": date,
                        "suggested_position": sentiment["suggested_position"]
                    })
                
                if len(self.positions) + len([s for s in signals if s["type"] == "buy"]) >= MAX_HOLDING_COUNT:
                    break
        
        return signals
    
    def _execute_trade(self, signal: Dict, date: str):
        """执行交易"""
        if signal["type"] == "buy":
            # 买入
            fund_code = signal["fund_code"]
            suggested_position = signal.get("suggested_position", 0.1)
            
            # 计算买入金额
            buy_amount = min(
                INITIAL_CASH * suggested_position,
                MAX_POSITION_VALUE,
                self.cash * 0.95  # 保留5%现金
            )
            
            if buy_amount < 1000:  # 最小买入金额
                return
            
            # 获取当日净值（从真实数据）
            nav_map = load_historical_nav(fund_code)
            if not nav_map:
                return
            
            if date not in nav_map:
                # 如果当天无数据，使用最近一天的净值
                available_dates = sorted([d for d in nav_map.keys() if d <= date], reverse=True)
                if not available_dates:
                    return
                buy_nav = nav_map[available_dates[0]]
            else:
                buy_nav = nav_map[date]
            
            quantity = int(buy_amount / buy_nav / 100) * 100  # 按100份取整
            
            if quantity <= 0:
                return
            
            # 扣除交易成本
            total_cost = quantity * buy_nav * (1 + TRADE_COST)
            
            if total_cost > self.cash:
                return
            
            self.cash -= total_cost
            
            # 添加持仓
            self.positions.append({
                "fund_code": fund_code,
                "buy_date": date,
                "buy_nav": buy_nav,
                "quantity": quantity,
                "cost": total_cost,
                "market_value": quantity * buy_nav
            })
            
            # 记录交易
            self.trades.append({
                "date": date,
                "fund_code": fund_code,
                "type": "buy",
                "price": buy_nav,
                "quantity": quantity,
                "cost": total_cost,
                "pnl": 0
            })
        
        elif signal["type"] == "sell":
            # 卖出
            fund_code = signal["fund_code"]
            
            # 找到持仓
            pos = next((p for p in self.positions if p["fund_code"] == fund_code), None)
            if not pos:
                return
            
            # 获取当日净值（从真实数据）
            nav_map = load_historical_nav(fund_code)
            if not nav_map:
                return
            
            if date not in nav_map:
                # 如果当天无数据，使用最近一天的净值
                available_dates = sorted([d for d in nav_map.keys() if d <= date], reverse=True)
                if not available_dates:
                    return
                sell_nav = nav_map[available_dates[0]]
            else:
                sell_nav = nav_map[date]
            
            # 计算盈亏
            sell_amount = pos["quantity"] * sell_nav * (1 - TRADE_COST)
            pnl = sell_amount - pos["cost"]
            
            # 更新现金
            self.cash += sell_amount
            
            # 记录交易
            self.trades.append({
                "date": date,
                "fund_code": fund_code,
                "type": "sell",
                "price": sell_nav,
                "quantity": pos["quantity"],
                "cost": pos["cost"],
                "pnl": pnl
            })
            
            # 移除持仓
            self.positions = [p for p in self.positions if p["fund_code"] != fund_code]
    
    def _calculate_metrics(self) -> Dict:
        """计算评估指标"""
        if not self.nav_curve:
            return {}
        
        # 提取净值序列
        values = [v["total_value"] for v in self.nav_curve]
        
        # 累计收益率
        total_return = (values[-1] - INITIAL_CASH) / INITIAL_CASH
        
        # 最大回撤
        max_drawdown = 0
        peak = values[0]
        for v in values:
            if v > peak:
                peak = v
            drawdown = (peak - v) / peak
            if drawdown > max_drawdown:
                max_drawdown = drawdown
        
        # 胜率
        win_count = sum(1 for t in self.trades if t["type"] == "sell" and t["pnl"] > 0)
        total_sell = sum(1 for t in self.trades if t["type"] == "sell")
        win_rate = win_count / total_sell if total_sell > 0 else 0
        
        # 交易频率
        trade_frequency = len(self.trades) / len(self.nav_curve)
        
        # 夏普比率（简化计算）
        daily_returns = []
        for i in range(1, len(values)):
            ret = (values[i] - values[i-1]) / values[i-1]
            daily_returns.append(ret)
        
        if daily_returns:
            avg_return = sum(daily_returns) / len(daily_returns)
            std_return = (sum((r - avg_return) ** 2 for r in daily_returns) / len(daily_returns)) ** 0.5
            sharpe = (avg_return / std_return) * (252 ** 0.5) if std_return > 0 else 0
        else:
            sharpe = 0
        
        return {
            "strategy": self.strategy,
            "initial_cash": INITIAL_CASH,
            "final_value": values[-1],
            "total_return": total_return,
            "annualized_return": (1 + total_return) ** (252 / len(values)) - 1,
            "max_drawdown": max_drawdown,
            "sharpe_ratio": sharpe,
            "win_rate": win_rate,
            "total_trades": len(self.trades),
            "trade_frequency": trade_frequency,
            "win_count": win_count,
            "total_sell": total_sell
        }


# ============================================================
# 主函数
# ============================================================

def main():
    """运行A/B测试"""
    print("=" * 80)
    print("📊 方案B A/B测试回测（使用真实信号）")
    print("=" * 80)
    
    # 运行对照组（A组）
    engine_a = BacktestEngine(strategy="A")
    metrics_a = engine_a.run()
    
    # 运行实验组（B组）
    engine_b = BacktestEngine(strategy="B")
    metrics_b = engine_b.run()
    
    # 生成对比报告
    print("\n" + "=" * 80)
    print("📊 A/B测试结果对比")
    print("=" * 80)
    
    print(f"\n{'指标':<20} {'A组（对照组）':<20} {'B组（实验组）':<20} {'差异':<15}")
    print("-" * 80)
    
    # 累计收益率
    ret_a = metrics_a["total_return"]
    ret_b = metrics_b["total_return"]
    print(f"{'累计收益率':<20} {ret_a:>18.2%}   {ret_b:>18.2%}   {ret_b-ret_a:>+13.2%}")
    
    # 年化收益率
    ann_a = metrics_a["annualized_return"]
    ann_b = metrics_b["annualized_return"]
    print(f"{'年化收益率':<20} {ann_a:>18.2%}   {ann_b:>18.2%}   {ann_b-ann_a:>+13.2%}")
    
    # 最大回撤
    dd_a = metrics_a["max_drawdown"]
    dd_b = metrics_b["max_drawdown"]
    print(f"{'最大回撤':<20} {dd_a:>18.2%}   {dd_b:>18.2%}   {dd_b-dd_a:>+13.2%}")
    
    # 夏普比率
    sharpe_a = metrics_a["sharpe_ratio"]
    sharpe_b = metrics_b["sharpe_ratio"]
    print(f"{'夏普比率':<20} {sharpe_a:>18.2f}   {sharpe_b:>18.2f}   {sharpe_b-sharpe_a:>+13.2f}")
    
    # 胜率
    wr_a = metrics_a["win_rate"]
    wr_b = metrics_b["win_rate"]
    print(f"{'胜率':<20} {wr_a:>18.2%}   {wr_b:>18.2%}   {wr_b-wr_a:>+13.2%}")
    
    # 交易次数
    trades_a = metrics_a["total_trades"]
    trades_b = metrics_b["total_trades"]
    print(f"{'交易次数':<20} {trades_a:>18d}   {trades_b:>18d}   {trades_b-trades_a:>+13d}")
    
    # 交易频率
    freq_a = metrics_a["trade_frequency"]
    freq_b = metrics_b["trade_frequency"]
    print(f"{'交易频率（次/日）':<20} {freq_a:>18.4f}   {freq_b:>18.4f}   {freq_b-freq_a:>+13.4f}")
    
    print("\n" + "=" * 80)
    
    # 判断方案B是否有效
    print("\n🎯 方案B有效性判断：")
    
    is_effective = True
    
    if ret_b <= ret_a:
        print(f"  ❌ 累计收益率未提升（A组: {ret_a:.2%}, B组: {ret_b:.2%}）")
        is_effective = False
    else:
        print(f"  ✅ 累计收益率提升（A组: {ret_a:.2%}, B组: {ret_b:.2%}, +{ret_b-ret_a:.2%}）")
    
    if dd_b >= dd_a:
        print(f"  ❌ 最大回撤未降低（A组: {dd_a:.2%}, B组: {dd_b:.2%}）")
        is_effective = False
    else:
        print(f"  ✅ 最大回撤降低（A组: {dd_a:.2%}, B组: {dd_b:.2%}, {dd_b-dd_a:.2%}）")
    
    if sharpe_b <= sharpe_a:
        print(f"  ❌ 夏普比率未提升（A组: {sharpe_a:.2f}, B组: {sharpe_b:.2f}）")
        is_effective = False
    else:
        print(f"  ✅ 夏普比率提升（A组: {sharpe_a:.2f}, B组: {sharpe_b:.2f}, +{sharpe_b-sharpe_a:.2f}）")
    
    if trades_b >= trades_a:
        print(f"  ⚠️ 交易次数未减少（A组: {trades_a}, B组: {trades_b}）")
    else:
        print(f"  ✅ 交易次数减少（A组: {trades_a}, B组: {trades_b}, -{trades_a-trades_b}）")
    
    print("\n" + "=" * 80)
    
    if is_effective:
        print("\n✅ 方案B判定：有效！建议正式启用方案B。")
    else:
        print("\n⚠️ 方案B判定：无效或效果不明显，建议进一步优化。")
    
    print("=" * 80)
    
    # 保存结果
    result = {
        "metrics_a": metrics_a,
        "metrics_b": metrics_b,
        "is_effective": is_effective
    }
    
    with open("ab_test_result.json", "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    print("\n📁 结果已保存：ab_test_result.json")
    print("=" * 80)


if __name__ == "__main__":
    main()
