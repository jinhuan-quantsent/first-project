-- ============================================================
-- RLS 策略：Row Level Security
-- 启用于 user_watchlist、user_portfolio、advice_log
-- 注意：此文件需在 Supabase Dashboard SQL Editor 中执行
-- ============================================================

-- 启用 RLS
ALTER TABLE user_watchlist ENABLE ROW LEVEL SECURITY;
ALTER TABLE user_portfolio ENABLE ROW LEVEL SECURITY;
ALTER TABLE advice_log ENABLE ROW LEVEL SECURITY;

-- ============================================================
-- user_watchlist 策略
-- ============================================================
CREATE POLICY "Users can read own watchlist" ON user_watchlist
    FOR SELECT USING (auth.uid() = user_id::text);

CREATE POLICY "Users can insert own watchlist" ON user_watchlist
    FOR INSERT WITH CHECK (auth.uid() = user_id::text);

CREATE POLICY "Users can delete own watchlist" ON user_watchlist
    FOR DELETE USING (auth.uid() = user_id::text);

-- ============================================================
-- user_portfolio 策略
-- ============================================================
CREATE POLICY "Users can read own portfolio" ON user_portfolio
    FOR SELECT USING (auth.uid() = user_id::text);

CREATE POLICY "Users can manage own portfolio" ON user_portfolio
    FOR ALL USING (auth.uid() = user_id::text);

-- ============================================================
-- advice_log 策略
-- ============================================================
CREATE POLICY "Users can read own advice_log" ON advice_log
    FOR SELECT USING (auth.uid() = user_id::text);
