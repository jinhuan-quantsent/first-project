/**
 * V5.0 建仓评级 + 板块基金 类型定义
 *
 * 对应后端端点:
 *   GET /api/v5/sector/position-rating              — 全部板块建仓评级
 *   GET /api/v5/sector/position-rating/{code}       — 单板块评级详情
 *   GET /api/v5/sector/position-rating/{code}/funds — 板块关联基金
 */

/** 建仓评级4档 */
export type PositionRating = 'strong' | 'cautious' | 'watch' | 'forbidden';

/** 建仓评级配置 */
export const POSITION_RATING_CONFIG: Record<
  PositionRating,
  { label: string; shortLabel: string; color: string; bg: string; text: string; border: string; dot: string }
> = {
  strong: {
    label: '强烈建仓',
    shortLabel: '强烈',
    color: '#16a34a',
    bg: 'bg-green-50',
    text: 'text-green-700',
    border: 'border-green-200',
    dot: 'bg-green-500',
  },
  cautious: {
    label: '谨慎建仓',
    shortLabel: '谨慎',
    color: '#eab308',
    bg: 'bg-yellow-50',
    text: 'text-yellow-700',
    border: 'border-yellow-200',
    dot: 'bg-yellow-500',
  },
  watch: {
    label: '观望',
    shortLabel: '观望',
    color: '#6b7280',
    bg: 'bg-gray-50',
    text: 'text-gray-600',
    border: 'border-gray-200',
    dot: 'bg-gray-400',
  },
  forbidden: {
    label: '禁止建仓',
    shortLabel: '禁止',
    color: '#dc2626',
    bg: 'bg-red-50',
    text: 'text-red-700',
    border: 'border-red-200',
    dot: 'bg-red-500',
  },
};

/** 轨道类型 */
export type TrackType = 'trend_follow' | 'contrarian';

/** 旧版建仓类型（向后兼容，SectorRadarPanel 等使用） */
export type PositionType = 'trend' | 'contrarian' | 'forbidden';

/** 板块关联基金（API返回结构） */
export interface SectorFund {
  fund_code: string;
  fund_name: string;
  track_index: string;
  track_index_code?: string; // 二级赛道主题指数代码
  fit_degree: number;
  fund_level: number; // 1=一级, 2=二级
  status: string; // active/reserved
  sub_sector?: string; // 二级细分赛道名称
  parent_sector?: string; // 父级板块代码
  rating?: PositionRating;
  rating_reason?: string;
}

/** 二级赛道摘要 (level2_sectors 数组项) */
export interface Level2Sector {
  fund_code: string;
  fund_name: string;
  track_index: string;
  track_index_code: string;
  sub_sector: string;
  fit_degree: number;
  build_rating: PositionRating;
}

/** 建仓评级结果（单个板块，对应 _format_position_rating_item） */
export interface PositionRatingItem {
  sector_code: string;
  sector_name: string;
  rating: PositionRating;
  rating_label: string;
  rating_color: string;
  reason: string;
  signal_level: string;
  trend_track: TrackType;
  track: TrackType;
  position_suggestion: number;
  confidence_stars: number;
  composite_score: number;
  turn_percentile: number | null;
  bottom_divergence: boolean | null;
  funds: SectorFund[];
  level2_sectors?: Level2Sector[]; // 二级赛道列表
  level2_hint?: string; // 二级赛道提示文案
}

/** 板块详情数据（= PositionRatingItem 别名，向后兼容） */
export type SectorDetailData = PositionRatingItem;
