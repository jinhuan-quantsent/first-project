-- T5: 申万一级行业指数日线数据表
-- 用于存储板块价格数据，支持回测和底背离计算

CREATE TABLE IF NOT EXISTS sector_price (
    id BIGINT AUTO_INCREMENT PRIMARY KEY,
    sector_code VARCHAR(10) NOT NULL COMMENT '申万一级行业代码(如801050)',
    sector_name VARCHAR(20) NOT NULL COMMENT '行业名称',
    trade_date DATE NOT NULL COMMENT '交易日期',
    open DECIMAL(10,4) COMMENT '开盘价',
    high DECIMAL(10,4) COMMENT '最高价',
    low DECIMAL(10,4) COMMENT '最低价',
    close DECIMAL(10,4) COMMENT '收盘价',
    volume BIGINT COMMENT '成交量(手)',
    amount DECIMAL(18,2) COMMENT '成交额(千元)',
    pct_change DECIMAL(8,4) COMMENT '涨跌幅(%)',
    UNIQUE KEY uk_sector_date (sector_code, trade_date),
    KEY idx_sector_code (sector_code),
    KEY idx_trade_date (trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COMMENT='申万一级行业指数日线数据';
