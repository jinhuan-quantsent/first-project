/**
 * V5.0 板块情绪 + 机会雷达 类型定义
 *
 * 对应后端端点:
 *   GET /api/v5/sector/sentiment  — 板块情绪评分
 *   GET /api/v5/sector/radar       — 双轨制推荐雷达
 */
import type { SignalLevel } from './index';

// ============================================================
// 因子相关
// ============================================================

/** 单个因子的评分详情 */
export interface SectorFactorScore {
  sigmoid_score: number;
  weight: number;
  direction: 'fear' | 'greed';
  reverse: boolean;
}

/** 因子配置（summary 中返回） */
export interface SectorFactorConfig {
  weight: number;
  direction: 'fear' | 'greed';
  reverse: boolean;
}

// ============================================================
// 板块情绪评分
// ============================================================

/** 单个板块的情绪评分结果 */
export interface SectorSentimentItem {
  sector_code: string;
  sector_name: string;
  sector_group: string;
  sentiment_score: number;
  sentiment_label: string;
  signal_level: SignalLevel;
  confidence_stars: number;
  confidence_detail: Record<string, number>;
  track: 'trend_follow' | 'contrarian' | 'excluded';
  triggered_defenses: string[];
  momentum_5d: number;
  momentum_20d: number;
  strength_index: number;
  strength_rank: number;
  sector_return: number;
  factor_completeness: number;
  cold_start: boolean;
  factor_scores: Record<string, SectorFactorScore>;
  aggregation_detail: Record<string, unknown>;
  reason: {
    observation: string;
    analysis: string;
    action: string;
  };
}

/** 板块情绪 API 响应 data */
export interface SectorSentimentData {
  sectors: SectorSentimentItem[];
  summary: {
    total: number;
    avg_sentiment_score: number;
    track_distribution: {
      trend_follow: number;
      contrarian: number;
      excluded: number;
    };
    factor_config: Record<string, SectorFactorConfig>;
  };
  elapsed_seconds: number;
}

// ============================================================
// 机会雷达
// ============================================================

/** 单个推荐机会 */
export interface SectorOpportunity {
  sector_code: string;
  sector_name: string;
  sector_group: string;
  sentiment_score: number;
  sentiment_label: string;
  signal_level: SignalLevel;
  confidence_stars: number;
  track: 'trend_follow' | 'contrarian' | 'excluded';
  momentum_5d: number;
  momentum_20d: number;
  strength_index: number;
  strength_rank: number;
  opportunity_type: string;
  opportunity_reason: string;
  rank: number;
  reason: {
    observation: string;
    analysis: string;
    action: string;
  };
  factor_scores: Record<string, SectorFactorScore>;
  factor_completeness: number;
  cold_start: boolean;
  recommended_funds: string[];
}

/** 机会雷达 API 响应 data */
export interface SectorRadarData {
  contrarian_opportunities: SectorOpportunity[];
  trend_follow_opportunities: SectorOpportunity[];
  all_recommendations: SectorOpportunity[];
  strong_sectors: SectorOpportunity[];
  rebound_opportunities: SectorOpportunity[];
  steady_choices: SectorOpportunity[];
  top_picks: SectorOpportunity[];
  summary: string;
  total_count: number;
  contrarian_count: number;
  trend_follow_count: number;
  excluded_count: number;
  factor_config: Record<string, SectorFactorConfig>;
  elapsed_seconds: number;
}
