-- ============================================================
-- 基金情绪分析系统 V3.5 - PostgreSQL DDL
-- 10 张核心表
-- ============================================================

-- 1. 基金基本信息表
CREATE TABLE IF NOT EXISTS fund_basic (
    id SERIAL PRIMARY KEY,
    fund_code VARCHAR(10) NOT NULL UNIQUE,
    fund_name VARCHAR(100) NOT NULL,
    fund_short_name VARCHAR(50) DEFAULT '',
    fund_type VARCHAR(20) DEFAULT '',
    manager VARCHAR(50) DEFAULT '',
    company VARCHAR(100) DEFAULT '',
    inception_date DATE,
    nav DOUBLE PRECISION DEFAULT 0.0,
    accumulated_nav DOUBLE PRECISION DEFAULT 0.0,
    fund_size DOUBLE PRECISION DEFAULT 0.0,
    benchmark VARCHAR(100) DEFAULT '',
    tracking_index VARCHAR(20) DEFAULT '',
    risk_level VARCHAR(10) DEFAULT 'R3',
    description TEXT DEFAULT '',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_fund_basic_code ON fund_basic(fund_code);
CREATE INDEX idx_fund_basic_type ON fund_basic(fund_type);

-- 2. 基金净值历史表
CREATE TABLE IF NOT EXISTS fund_nav (
    id SERIAL PRIMARY KEY,
    fund_code VARCHAR(10) NOT NULL,
    nav_date DATE NOT NULL,
    nav DOUBLE PRECISION DEFAULT 0.0,
    accumulated_nav DOUBLE PRECISION DEFAULT 0.0,
    daily_return DOUBLE PRECISION DEFAULT 0.0,
    week_return DOUBLE PRECISION DEFAULT 0.0,
    month_return DOUBLE PRECISION DEFAULT 0.0,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_fund_nav_code ON fund_nav(fund_code);
CREATE INDEX idx_fund_nav_date ON fund_nav(nav_date);
CREATE UNIQUE INDEX idx_fund_nav_code_date ON fund_nav(fund_code, nav_date);

-- 3. 市场情绪主表
CREATE TABLE IF NOT EXISTS market_sentiment (
    id SERIAL PRIMARY KEY,
    index_code VARCHAR(20) NOT NULL,
    index_name VARCHAR(50) DEFAULT '',
    trade_date DATE NOT NULL,
    record_time TIMESTAMP,
    -- 7大因子原始值
    volatility DOUBLE PRECISION DEFAULT 0.0,
    turnover_ratio DOUBLE PRECISION DEFAULT 0.0,
    adv_decline_ratio DOUBLE PRECISION DEFAULT 0.0,
    new_high_ratio DOUBLE PRECISION DEFAULT 0.0,
    margin_balance DOUBLE PRECISION DEFAULT 0.0,
    short_balance DOUBLE PRECISION DEFAULT 0.0,
    bond_spread DOUBLE PRECISION DEFAULT 0.0,
    rsi_value DOUBLE PRECISION DEFAULT 50.0,
    -- 7大因子评分
    score_volatility DOUBLE PRECISION DEFAULT 50.0,
    score_turnover DOUBLE PRECISION DEFAULT 50.0,
    score_adv_decline DOUBLE PRECISION DEFAULT 50.0,
    score_new_high DOUBLE PRECISION DEFAULT 50.0,
    score_margin DOUBLE PRECISION DEFAULT 50.0,
    score_bond_equity DOUBLE PRECISION DEFAULT 50.0,
    score_rsi DOUBLE PRECISION DEFAULT 50.0,
    -- 综合指标
    composite_score DOUBLE PRECISION DEFAULT 50.0,
    sentiment_label VARCHAR(10) DEFAULT 'neutral',
    divergence_index DOUBLE PRECISION DEFAULT 0.0,
    trend_direction VARCHAR(10) DEFAULT 'stable',
    trend_strength DOUBLE PRECISION DEFAULT 0.0,
    top3_factors VARCHAR(200) DEFAULT '',
    conclusion TEXT DEFAULT '',
    operation_advice TEXT DEFAULT '',
    is_extreme INTEGER DEFAULT 0,
    abnormal_signals VARCHAR(500) DEFAULT '',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_market_sentiment_code ON market_sentiment(index_code);
CREATE INDEX idx_market_sentiment_date ON market_sentiment(trade_date);
CREATE UNIQUE INDEX idx_market_sentiment_code_date ON market_sentiment(index_code, trade_date);

-- 4. 板块情绪表
CREATE TABLE IF NOT EXISTS sector_sentiment (
    id SERIAL PRIMARY KEY,
    sector_code VARCHAR(20) NOT NULL,
    sector_name VARCHAR(50) NOT NULL,
    trade_date DATE NOT NULL,
    sector_return DOUBLE PRECISION DEFAULT 0.0,
    turnover_ratio DOUBLE PRECISION DEFAULT 0.0,
    fund_flow DOUBLE PRECISION DEFAULT 0.0,
    strength_index DOUBLE PRECISION DEFAULT 50.0,
    sentiment_score DOUBLE PRECISION DEFAULT 50.0,
    sentiment_label VARCHAR(10) DEFAULT 'neutral',
    rank INTEGER DEFAULT 0,
    momentum_5d DOUBLE PRECISION DEFAULT 0.0,
    momentum_20d DOUBLE PRECISION DEFAULT 0.0,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_sector_sentiment_code ON sector_sentiment(sector_code);
CREATE INDEX idx_sector_sentiment_date ON sector_sentiment(trade_date);

-- 5. 融资融券数据表
CREATE TABLE IF NOT EXISTS market_margin (
    id SERIAL PRIMARY KEY,
    trade_date DATE NOT NULL,
    market VARCHAR(10) DEFAULT 'SH',
    margin_buy DOUBLE PRECISION DEFAULT 0.0,
    margin_balance DOUBLE PRECISION DEFAULT 0.0,
    margin_repay DOUBLE PRECISION DEFAULT 0.0,
    short_sell DOUBLE PRECISION DEFAULT 0.0,
    short_balance DOUBLE PRECISION DEFAULT 0.0,
    margin_ratio DOUBLE PRECISION DEFAULT 0.0,
    short_ratio DOUBLE PRECISION DEFAULT 0.0,
    net_margin_flow DOUBLE PRECISION DEFAULT 0.0,
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_market_margin_date ON market_margin(trade_date);

-- 6. 用户自选基金表
CREATE TABLE IF NOT EXISTS user_watchlist (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    fund_code VARCHAR(10) NOT NULL,
    fund_name VARCHAR(100) DEFAULT '',
    added_at TIMESTAMP DEFAULT NOW(),
    notes VARCHAR(500) DEFAULT '',
    alert_threshold DOUBLE PRECISION DEFAULT 0.0,
    sort_order INTEGER DEFAULT 0
);
CREATE INDEX idx_user_watchlist_user ON user_watchlist(user_id);
CREATE INDEX idx_user_watchlist_fund ON user_watchlist(fund_code);

-- 7. 用户持仓组合表
CREATE TABLE IF NOT EXISTS user_portfolio (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    fund_code VARCHAR(10) NOT NULL,
    fund_name VARCHAR(100) DEFAULT '',
    fund_type VARCHAR(20) DEFAULT '',
    holding_shares DOUBLE PRECISION DEFAULT 0.0,
    cost_nav DOUBLE PRECISION DEFAULT 0.0,
    current_nav DOUBLE PRECISION DEFAULT 0.0,
    market_value DOUBLE PRECISION DEFAULT 0.0,
    total_return DOUBLE PRECISION DEFAULT 0.0,
    return_rate DOUBLE PRECISION DEFAULT 0.0,
    daily_return DOUBLE PRECISION DEFAULT 0.0,
    buy_date DATE,
    updated_at TIMESTAMP DEFAULT NOW(),
    portfolio_tag VARCHAR(20) DEFAULT '',
    weight_pct DOUBLE PRECISION DEFAULT 0.0
);
CREATE INDEX idx_user_portfolio_user ON user_portfolio(user_id);
CREATE INDEX idx_user_portfolio_fund ON user_portfolio(fund_code);

-- 8. 板块映射表（大板块 28 个）
CREATE TABLE IF NOT EXISTS sector_mapping (
    id SERIAL PRIMARY KEY,
    sector_code VARCHAR(20) NOT NULL UNIQUE,
    sector_name VARCHAR(50) NOT NULL,
    sector_group VARCHAR(20) DEFAULT '',
    index_code VARCHAR(20) DEFAULT '',
    weight DOUBLE PRECISION DEFAULT 0.0,
    description VARCHAR(200) DEFAULT '',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_sector_mapping_code ON sector_mapping(sector_code);
CREATE INDEX idx_sector_mapping_group ON sector_mapping(sector_group);

-- 9. 小板块映射表（60 个细分板块）
CREATE TABLE IF NOT EXISTS small_sector_mapping (
    id SERIAL PRIMARY KEY,
    sector_code VARCHAR(20) NOT NULL UNIQUE,
    sector_name VARCHAR(50) NOT NULL,
    parent_code VARCHAR(20) NOT NULL,
    parent_name VARCHAR(50) DEFAULT '',
    sector_group VARCHAR(20) DEFAULT '',
    weight DOUBLE PRECISION DEFAULT 0.0,
    description VARCHAR(200) DEFAULT '',
    created_at TIMESTAMP NOT NULL DEFAULT NOW(),
    updated_at TIMESTAMP NOT NULL DEFAULT NOW()
);
CREATE INDEX idx_small_sector_code ON small_sector_mapping(sector_code);
CREATE INDEX idx_small_sector_parent ON small_sector_mapping(parent_code);

-- 10. 操作建议日志表
CREATE TABLE IF NOT EXISTS advice_log (
    id SERIAL PRIMARY KEY,
    user_id VARCHAR(50) NOT NULL,
    index_code VARCHAR(20) DEFAULT '',
    trade_date TIMESTAMP DEFAULT NOW(),
    sentiment_score DOUBLE PRECISION DEFAULT 50.0,
    sentiment_label VARCHAR(10) DEFAULT 'neutral',
    advice_type VARCHAR(20) DEFAULT '',
    advice_content TEXT DEFAULT '',
    suggested_position DOUBLE PRECISION DEFAULT 50.0,
    is_executed INTEGER DEFAULT 0,
    executed_at TIMESTAMP,
    execution_note VARCHAR(500) DEFAULT '',
    is_verified INTEGER DEFAULT 0,
    actual_result DOUBLE PRECISION DEFAULT 0.0,
    accuracy_score DOUBLE PRECISION DEFAULT 0.0
);
CREATE INDEX idx_advice_log_user ON advice_log(user_id);
CREATE INDEX idx_advice_log_date ON advice_log(trade_date);
