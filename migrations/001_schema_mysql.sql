-- ============================================================
-- 基金情绪分析系统 V3.5 - MySQL DDL（备用）
-- ============================================================

-- 1. 基金基本信息表
CREATE TABLE IF NOT EXISTS fund_basic (
    id INT AUTO_INCREMENT PRIMARY KEY,
    fund_code VARCHAR(10) NOT NULL UNIQUE,
    fund_name VARCHAR(100) NOT NULL,
    fund_short_name VARCHAR(50) DEFAULT '',
    fund_type VARCHAR(20) DEFAULT '',
    manager VARCHAR(50) DEFAULT '',
    company VARCHAR(100) DEFAULT '',
    inception_date DATE,
    nav DOUBLE DEFAULT 0.0,
    accumulated_nav DOUBLE DEFAULT 0.0,
    fund_size DOUBLE DEFAULT 0.0,
    benchmark VARCHAR(100) DEFAULT '',
    tracking_index VARCHAR(20) DEFAULT '',
    risk_level VARCHAR(10) DEFAULT 'R3',
    description TEXT,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_fund_basic_code (fund_code),
    INDEX idx_fund_basic_type (fund_type)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 2. 基金净值历史表
CREATE TABLE IF NOT EXISTS fund_nav (
    id INT AUTO_INCREMENT PRIMARY KEY,
    fund_code VARCHAR(10) NOT NULL,
    nav_date DATE NOT NULL,
    nav DOUBLE DEFAULT 0.0,
    accumulated_nav DOUBLE DEFAULT 0.0,
    daily_return DOUBLE DEFAULT 0.0,
    week_return DOUBLE DEFAULT 0.0,
    month_return DOUBLE DEFAULT 0.0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_fund_nav_code (fund_code),
    INDEX idx_fund_nav_date (nav_date),
    UNIQUE INDEX idx_fund_nav_code_date (fund_code, nav_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 3. 市场情绪主表
CREATE TABLE IF NOT EXISTS market_sentiment (
    id INT AUTO_INCREMENT PRIMARY KEY,
    index_code VARCHAR(20) NOT NULL,
    index_name VARCHAR(50) DEFAULT '',
    trade_date DATE NOT NULL,
    record_time TIMESTAMP NULL,
    volatility DOUBLE DEFAULT 0.0,
    turnover_ratio DOUBLE DEFAULT 0.0,
    adv_decline_ratio DOUBLE DEFAULT 0.0,
    new_high_ratio DOUBLE DEFAULT 0.0,
    margin_balance DOUBLE DEFAULT 0.0,
    short_balance DOUBLE DEFAULT 0.0,
    bond_spread DOUBLE DEFAULT 0.0,
    rsi_value DOUBLE DEFAULT 50.0,
    score_volatility DOUBLE DEFAULT 50.0,
    score_turnover DOUBLE DEFAULT 50.0,
    score_adv_decline DOUBLE DEFAULT 50.0,
    score_new_high DOUBLE DEFAULT 50.0,
    score_margin DOUBLE DEFAULT 50.0,
    score_bond_equity DOUBLE DEFAULT 50.0,
    score_rsi DOUBLE DEFAULT 50.0,
    composite_score DOUBLE DEFAULT 50.0,
    sentiment_label VARCHAR(10) DEFAULT 'neutral',
    divergence_index DOUBLE DEFAULT 0.0,
    trend_direction VARCHAR(10) DEFAULT 'stable',
    trend_strength DOUBLE DEFAULT 0.0,
    top3_factors VARCHAR(200) DEFAULT '',
    conclusion TEXT,
    operation_advice TEXT,
    is_extreme INT DEFAULT 0,
    abnormal_signals VARCHAR(500) DEFAULT '',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_market_sentiment_code (index_code),
    INDEX idx_market_sentiment_date (trade_date),
    UNIQUE INDEX idx_market_sentiment_code_date (index_code, trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 4. 板块情绪表
CREATE TABLE IF NOT EXISTS sector_sentiment (
    id INT AUTO_INCREMENT PRIMARY KEY,
    sector_code VARCHAR(20) NOT NULL,
    sector_name VARCHAR(50) NOT NULL,
    trade_date DATE NOT NULL,
    sector_return DOUBLE DEFAULT 0.0,
    turnover_ratio DOUBLE DEFAULT 0.0,
    fund_flow DOUBLE DEFAULT 0.0,
    strength_index DOUBLE DEFAULT 50.0,
    sentiment_score DOUBLE DEFAULT 50.0,
    sentiment_label VARCHAR(10) DEFAULT 'neutral',
    rank INT DEFAULT 0,
    momentum_5d DOUBLE DEFAULT 0.0,
    momentum_20d DOUBLE DEFAULT 0.0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_sector_sentiment_code (sector_code),
    INDEX idx_sector_sentiment_date (trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 5. 融资融券数据表
CREATE TABLE IF NOT EXISTS market_margin (
    id INT AUTO_INCREMENT PRIMARY KEY,
    trade_date DATE NOT NULL,
    market VARCHAR(10) DEFAULT 'SH',
    margin_buy DOUBLE DEFAULT 0.0,
    margin_balance DOUBLE DEFAULT 0.0,
    margin_repay DOUBLE DEFAULT 0.0,
    short_sell DOUBLE DEFAULT 0.0,
    short_balance DOUBLE DEFAULT 0.0,
    margin_ratio DOUBLE DEFAULT 0.0,
    short_ratio DOUBLE DEFAULT 0.0,
    net_margin_flow DOUBLE DEFAULT 0.0,
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_market_margin_date (trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 6. 用户自选基金表
CREATE TABLE IF NOT EXISTS user_watchlist (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    fund_code VARCHAR(10) NOT NULL,
    fund_name VARCHAR(100) DEFAULT '',
    added_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    notes VARCHAR(500) DEFAULT '',
    alert_threshold DOUBLE DEFAULT 0.0,
    sort_order INT DEFAULT 0,
    INDEX idx_user_watchlist_user (user_id),
    INDEX idx_user_watchlist_fund (fund_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 7. 用户持仓组合表
CREATE TABLE IF NOT EXISTS user_portfolio (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    fund_code VARCHAR(10) NOT NULL,
    fund_name VARCHAR(100) DEFAULT '',
    fund_type VARCHAR(20) DEFAULT '',
    holding_shares DOUBLE DEFAULT 0.0,
    cost_nav DOUBLE DEFAULT 0.0,
    current_nav DOUBLE DEFAULT 0.0,
    market_value DOUBLE DEFAULT 0.0,
    total_return DOUBLE DEFAULT 0.0,
    return_rate DOUBLE DEFAULT 0.0,
    daily_return DOUBLE DEFAULT 0.0,
    buy_date DATE,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    portfolio_tag VARCHAR(20) DEFAULT '',
    weight_pct DOUBLE DEFAULT 0.0,
    INDEX idx_user_portfolio_user (user_id),
    INDEX idx_user_portfolio_fund (fund_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 8. 板块映射表
CREATE TABLE IF NOT EXISTS sector_mapping (
    id INT AUTO_INCREMENT PRIMARY KEY,
    sector_code VARCHAR(20) NOT NULL UNIQUE,
    sector_name VARCHAR(50) NOT NULL,
    sector_group VARCHAR(20) DEFAULT '',
    index_code VARCHAR(20) DEFAULT '',
    weight DOUBLE DEFAULT 0.0,
    description VARCHAR(200) DEFAULT '',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_sector_mapping_code (sector_code),
    INDEX idx_sector_mapping_group (sector_group)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 9. 小板块映射表
CREATE TABLE IF NOT EXISTS small_sector_mapping (
    id INT AUTO_INCREMENT PRIMARY KEY,
    sector_code VARCHAR(20) NOT NULL UNIQUE,
    sector_name VARCHAR(50) NOT NULL,
    parent_code VARCHAR(20) NOT NULL,
    parent_name VARCHAR(50) DEFAULT '',
    sector_group VARCHAR(20) DEFAULT '',
    weight DOUBLE DEFAULT 0.0,
    description VARCHAR(200) DEFAULT '',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
    INDEX idx_small_sector_code (sector_code),
    INDEX idx_small_sector_parent (parent_code)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;

-- 10. 操作建议日志表
CREATE TABLE IF NOT EXISTS advice_log (
    id INT AUTO_INCREMENT PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    index_code VARCHAR(20) DEFAULT '',
    trade_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    sentiment_score DOUBLE DEFAULT 50.0,
    sentiment_label VARCHAR(10) DEFAULT 'neutral',
    advice_type VARCHAR(20) DEFAULT '',
    advice_content TEXT,
    suggested_position DOUBLE DEFAULT 50.0,
    is_executed INT DEFAULT 0,
    executed_at TIMESTAMP NULL,
    execution_note VARCHAR(500) DEFAULT '',
    is_verified INT DEFAULT 0,
    actual_result DOUBLE DEFAULT 0.0,
    accuracy_score DOUBLE DEFAULT 0.0,
    INDEX idx_advice_log_user (user_id),
    INDEX idx_advice_log_date (trade_date)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
