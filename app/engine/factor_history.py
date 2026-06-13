"""
因子历史数据存储与查询
V4.0 动态分位数映射的基础设施
"""
import sqlite3
import os
from datetime import date, timedelta
from typing import Optional
import numpy as np

# SQLite 路径：与现有数据库同目录
DB_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(__file__)))), "data")
DB_PATH = os.path.join(DB_DIR, "fund_sentiment.db")

# 反向因子：值越高越恐慌 → 得分 = 100 - percentile
REVERSE_FACTORS = {"波动率", "RSI"}

# 倒U型因子：适中最好 → 用偏差映射
INVERTED_U_FACTORS = {"换手率", "融资融券"}

DEFAULT_LOOKBACK = 750


def _normalize_code(code: str) -> str:
    """Convert between API format (SH000001) and tushare format (000001.SH)"""
    if code.startswith("SH") and "." not in code:
        return code[2:] + ".SH"
    if code.startswith("SZ") and "." not in code:
        return code[2:] + ".SZ"
    return code




class FactorHistoryStore:
    """因子历史数据存储与查询"""
    
    def __init__(self, db_path: str = None):
        self.db_path = db_path or DB_PATH
        self._ensure_table()
    
    def _ensure_table(self):
        """确保 factor_history 表存在"""
        os.makedirs(os.path.dirname(self.db_path), exist_ok=True)
        with sqlite3.connect(self.db_path) as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS factor_history (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    index_code TEXT NOT NULL,
                    factor_name TEXT NOT NULL,
                    trade_date TEXT NOT NULL,
                    raw_value REAL NOT NULL,
                    created_at TEXT DEFAULT (datetime('now')),
                    UNIQUE(index_code, factor_name, trade_date)
                )
            """)
            conn.execute("""
                CREATE INDEX IF NOT EXISTS idx_factor_history_lookup 
                ON factor_history(index_code, factor_name, trade_date)
            """)
            conn.commit()
    
    def insert(self, index_code: str, factor_name: str, trade_date: str, raw_value: float) -> bool:
        """插入单条历史记录，唯一约束防重复"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                conn.execute(
                    "INSERT OR IGNORE INTO factor_history (index_code, factor_name, trade_date, raw_value) VALUES (?, ?, ?, ?)",
                    (index_code, factor_name, trade_date, round(raw_value, 4))
                )
                conn.commit()
            return True
        except Exception as e:
            print(f"⚠️ factor_history insert error: {e}")
            return False
    
    def insert_batch(self, records: list) -> int:
        """批量插入 [(index_code, factor_name, trade_date, raw_value), ...]"""
        count = 0
        try:
            with sqlite3.connect(self.db_path) as conn:
                for record in records:
                    try:
                        conn.execute(
                            "INSERT OR IGNORE INTO factor_history (index_code, factor_name, trade_date, raw_value) VALUES (?, ?, ?, ?)",
                            (record[0], record[1], record[2], round(record[3], 4))
                        )
                        count += 1
                    except Exception:
                        pass
                conn.commit()
        except Exception as e:
            print(f"⚠️ factor_history batch insert error: {e}")
        return count
    
    def get_series(self, index_code: str, factor_name: str, lookback_days: int = DEFAULT_LOOKBACK) -> list:
        """获取历史序列，按日期升序"""
        try:
            cutoff = (date.today() - timedelta(days=lookback_days)).isoformat()
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "SELECT raw_value FROM factor_history WHERE index_code = ? AND factor_name = ? AND trade_date >= ? ORDER BY trade_date ASC",
                    (_normalize_code(index_code), factor_name, cutoff)
                )
                return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            print(f"⚠️ factor_history get_series error: {e}")
            return []
    
    def get_percentile(self, index_code: str, factor_name: str, raw_value: float, lookback_days: int = DEFAULT_LOOKBACK) -> Optional[float]:
        """
        计算分位数：当前值在历史序列中处于什么位置
        返回 0-100 的百分位，数据不足时返回 None
        """
        series = self.get_series(index_code, factor_name, lookback_days)
        if len(series) < 60:
            return None  # 数据不足，由调用方降级
        try:
            from scipy import stats
            return stats.percentileofscore(series, raw_value, kind='rank')
        except Exception as e:
            print(f"⚠️ percentileofscore error: {e}")
            return None
    
    def get_series_count(self, index_code: str, factor_name: str) -> int:
        """获取某因子某指数的历史数据天数"""
        try:
            with sqlite3.connect(self.db_path) as conn:
                cursor = conn.execute(
                    "SELECT COUNT(*) FROM factor_history WHERE index_code = ? AND factor_name = ?",
                    (_normalize_code(index_code), factor_name)
                )
                row = cursor.fetchone()
                return row[0] if row else 0
        except Exception:
            return 0
    
    def backfill_from_tushare(self, index_code: str, tushare_pro, lookback_days: int = DEFAULT_LOOKBACK):
        """
        从 Tushare 回填某指数的历史因子数据
        
        对每个交易日的 index_daily 数据计算：
        - 波动率（60日滚动标准差年化）
        - RSI（14日）
        - 新高占比（当前价 / 60日最高价）
        换手率直接从 index_dailybasic 获取
        """
        import pandas as pd
        
        end_date = date.today().isoformat().replace('-', '')
        start_date = (date.today() - timedelta(days=lookback_days + 100)).isoformat().replace('-', '')
        
        try:
            # 获取指数日线
            df = tushare_pro.index_daily(ts_code=index_code, start_date=start_date, end_date=end_date)
            if df is None or df.empty:
                print(f"⚠️ Tushare index_daily 返回空: {index_code}")
                return 0
            
            df = df.sort_values('trade_date').reset_index(drop=True)
            closes = df['close'].values
            trade_dates = df['trade_date'].values
            
            records = []
            for i in range(len(closes)):
                td = trade_dates[i]
                # 至少需要60天数据才能算波动率
                if i < 60:
                    continue
                
                window = closes[max(0, i-60):i+1]
                
                # 波动率（年化）：60日收益率标准差 * sqrt(252)
                returns = np.diff(window) / window[:-1]
                volatility = float(np.std(returns) * np.sqrt(252) * 100)  # 转为百分比
                
                # RSI 14日
                if i >= 14:
                    rsi_window = closes[i-14:i+1]
                    diffs = np.diff(rsi_window)
                    gains = np.sum(diffs[diffs > 0]) if np.any(diffs > 0) else 0
                    losses = abs(np.sum(diffs[diffs < 0])) if np.any(diffs < 0) else 0
                    rs = gains / losses if losses > 0 else 100
                    rsi = float(100 - 100 / (1 + rs))
                else:
                    rsi = 50.0
                
                # 新高占比：当前价在60日最高价的位置
                high_60 = float(np.max(window))
                current = float(closes[i])
                new_high_ratio = round((current / high_60) * 20, 1) if current >= high_60 * 0.95 else round((current / high_60) * 10, 1)
                
                records.append((index_code, "波动率", td, volatility))
                records.append((index_code, "RSI", td, rsi))
                records.append((index_code, "新高占比", td, new_high_ratio))
            
            count = self.insert_batch(records)
            print(f"✅ {index_code} 回填完成: {count} 条记录 (波动率/RSI/新高占比)")
            return count
            
        except Exception as e:
            print(f"⚠️ backfill_from_tushare error for {index_code}: {e}")
            return 0


# 全局单例
factor_history = FactorHistoryStore()
