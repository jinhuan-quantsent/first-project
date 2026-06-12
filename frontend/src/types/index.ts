/* ============================================================
   全局类型定义
   基金情绪分析系统 V3.5
   ============================================================ */

// --- 情绪标签 ---
export type SentimentLabel =
  | 'extreme_fear'
  | 'fear'
  | 'neutral'
  | 'greed'
  | 'extreme_greed';

// --- 趋势方向 ---
export type TrendDirection = 'up' | 'down' | 'stable';

// --- 操作类型 ---
export type ActionType = 'increase' | 'hold' | 'reduce' | 'heavy_reduce';

// --- 风险等级 ---
export type RiskLevel = 'low' | 'medium' | 'high' | 'extreme';

// --- 因子评分 ---
export interface FactorScoreData {
  factor_name: string;
  raw_value: number;
  score: number;
  label: SentimentLabel;
  is_extreme: boolean;
  extreme_type: string;
}

// --- 指数摘要（快照条） ---
export interface IndexSnapshot {
  index_code: string;
  index_name: string;
  close: number;
  change_pct: number;
  composite_score: number;
  sentiment_label: SentimentLabel;
}

// --- 指数详情 ---
export interface IndexDetail {
  index_code: string;
  index_name: string;
  close: number;
  change_pct: number;
  composite_score: number;
  sentiment_label: SentimentLabel;
  factor_scores: Record<string, FactorScoreData>;
  top3_factors: FactorScoreData[];
  conclusion: string;
  operation_advice: string;
  trend_direction: TrendDirection;
  trend_strength: number;
  is_extreme: boolean;
  abnormal_signals: string[];
  position_advice: PositionAdviceData;
  history: SentimentHistoryPoint[];
}

// --- 多指数数据 ---
export interface MultiIndexData {
  index_code: string;
  index_name: string;
  close: number;
  change_pct: number;
  composite_score: number;
  sentiment_label: SentimentLabel;
  top3_factors: FactorScoreData[];
  trend_direction: TrendDirection;
  trend_strength: number;
  is_extreme: boolean;
  conclusion: string;
}

// --- 综合情绪 ---
export interface CompositeSentiment {
  composite_score: number;
  sentiment_label: SentimentLabel;
  divergence_index: number;
  conclusion: string;
  operation_advice: string;
}

// --- 情绪历史点 ---
export interface SentimentHistoryPoint {
  date: string;
  composite_score: number;
  sentiment_label: SentimentLabel;
}

// --- 仓位建议 ---
export interface PositionAdviceData {
  suggested_position: number;
  cash_reserve: number;
  action: ActionType;
  reason: string;
  risk_level: RiskLevel;
}

// --- 板块数据 ---
export interface SectorData {
  sector_code: string;
  sector_name: string;
  sector_group: string;
  sentiment_score: number;
  sentiment_label: SentimentLabel;
  sector_return: number;
  momentum_5d: number;
  momentum_20d: number;
  strength_index: number;
  turnover_ratio: number;
  fund_flow: number;
}

// --- 板块热力图 ---
export interface SectorHeatmapItem {
  sector_code: string;
  sector_name: string;
  sector_group: string;
  sentiment_score: number;
  sentiment_label: SentimentLabel;
  sector_return: number;
  momentum_5d: number;
  strength_index: number;
}

export interface GroupSummary {
  group_name: string;
  avg_score: number;
  sector_count: number;
}

// --- 机会推荐 ---
export interface OpportunityItem {
  sector_code: string;
  sector_name: string;
  sector_group: string;
  sentiment_score: number;
  sentiment_label: SentimentLabel;
  momentum_5d: number;
  momentum_20d: number;
  strength_index: number;
  opportunity_type: 'strong' | 'rebound' | 'steady';
  opportunity_reason: string;
  recommended_funds: string[];
}

export interface RecommendationData {
  strong_sectors: OpportunityItem[];
  rebound_opportunities: OpportunityItem[];
  steady_choices: OpportunityItem[];
  top_picks: OpportunityItem[];
  summary: string;
}

// --- 异常检测 ---
export interface AbnormalItem {
  index_code: string;
  index_name: string;
  extremes: {
    factor_name: string;
    score: number;
    extreme_type: string;
  }[];
}

// --- 趋势摘要 ---
export interface TrendSummary {
  trends: Record<string, { date: string; score: number; label: SentimentLabel }[]>;
}

// --- 基金搜索 ---
export interface FundSearchItem {
  fund_code: string;
  fund_name: string;
  fund_short_name: string;
  fund_type: string;
  nav: number;
  daily_return: number;
  week_return: number;
  month_return: number;
  year_return: number;
  fund_size: number;
  risk_level: string;
}

export interface FundSearchResult {
  items: FundSearchItem[];
  total: number;
  page: number;
  page_size: number;
}

// --- 基金详情 ---
export interface FundDetail extends FundSearchItem {
  manager: string;
  company: string;
  inception_date: string;
  accumulated_nav: number;
  benchmark: string;
  tracking_index: string;
  description: string;
  nav_history: {
    date: string;
    nav: number;
    daily_return: number;
  }[];
}

// --- 持仓 ---
export interface PortfolioItem {
  id: number;
  fund_code: string;
  fund_name: string;
  fund_type: string;
  holding_shares: number;
  cost_nav: number;
  current_nav: number;
  market_value: number;
  total_return: number;
  return_rate: number;
  daily_return: number;
  buy_date: string;
  portfolio_tag: string;
  weight_pct: number;
}

export interface PortfolioSummary {
  total_value: number;
  total_return: number;
  total_return_rate: number;
  daily_return: number;
  fund_count: number;
  core_ratio: number;
  satellite_ratio: number;
}

export interface PortfolioOverlap {
  overall_overlap_score: number;
  overlap_level: 'low' | 'medium' | 'high';
  details: {
    pair: string[];
    overlap_score: number;
    overlap_sectors: string[];
    suggestion: string;
  }[];
  suggestion: string;
}

// --- 自选 ---
export interface WatchlistItem {
  id: number;
  fund_code: string;
  fund_name: string;
  added_at: string;
  notes: string;
  alert_threshold: number;
  sort_order: number;
  current_nav: number;
  daily_return: number;
  week_return: number;
  month_return: number;
}

// --- 回测 ---
export interface BacktestParams {
  index_code: string;
  start_date: string;
  end_date: string;
  initial_capital: number;
  sentiment_threshold_buy: number;
  sentiment_threshold_sell: number;
}

export interface BacktestResult {
  total_return: number;
  annual_return: number;
  max_drawdown: number;
  win_rate: number;
  sharpe_ratio: number;
  benchmark_return: number;
  excess_return: number;
  total_trades: number;
  profit_trades: number;
}

export interface BacktestTrade {
  date: string;
  type: 'buy' | 'sell';
  price: number;
  amount: number;
  reason: string;
}

export interface EquityCurvePoint {
  date: string;
  value: number;
}

// --- 信号表现 ---
export interface SignalPerformance {
  index_code: string;
  total_signals: number;
  correct_signals: number;
  accuracy: number;
  buy_signals: number;
  sell_signals: number;
  hold_signals: number;
  signals: {
    date: string;
    composite_score: number;
    signal_type: 'buy' | 'sell' | 'hold';
    actual_return: number;
    is_correct: boolean;
  }[];
}

// --- 配置版本 ---
export interface ConfigVersion {
  version: string;
  released_at: string;
  changes: string[];
  weights: Record<string, number>;
}

// --- API 通用响应 ---
export interface ApiResponse<T = unknown> {
  code: number;
  data: T;
  message: string;
}

// --- 市场快照 ---
export interface MarketSnapshot {
  indexes: IndexSnapshot[];
  global_sentiment: SentimentLabel;
  global_score: number;
  divergence_index: number;
  conclusion: string;
  updated_at: string;
}
