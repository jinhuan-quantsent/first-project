/**
 * SectorFundCard — 板块基金卡片组件
 *
 * 可复用于:
 *  - 板块详情页基金列表
 *  - 持仓页空仓/轻仓标的
 *  - 自选页基金推荐
 *
 * 浅色极简风格, greedColor 体系
 */
import { clsx } from 'clsx';
import { Plus, ExternalLink, Star } from 'lucide-react';
import { POSITION_RATING_CONFIG } from '../../types/positionRating';
import type { SectorFund, PositionRating } from '../../types/positionRating';
import { toast } from '../common/Toast';

interface SectorFundCardProps {
  fund: SectorFund;
  onAddWatchlist?: (fundCode: string) => void;
  onViewDetail?: (fundCode: string) => void;
  compact?: boolean;
}

export default function SectorFundCard({
  fund,
  onAddWatchlist,
  onViewDetail,
  compact = false,
}: SectorFundCardProps) {
  const rating = (fund.rating || 'watch') as PositionRating;
  const cfg = POSITION_RATING_CONFIG[rating];

  const handleAddWatchlist = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (onAddWatchlist) {
      onAddWatchlist(fund.fund_code);
    } else {
      toast.success(`已添加 ${fund.fund_name} 到自选`);
    }
  };

  const handleViewDetail = (e: React.MouseEvent) => {
    e.stopPropagation();
    if (onViewDetail) {
      onViewDetail(fund.fund_code);
    }
  };

  return (
    <div
      className={clsx(
        'rounded-xl border transition-all hover:shadow-md',
        cfg.border,
        compact ? 'p-2.5' : 'p-3',
      )}
      style={{ background: '#fff' }}
    >
      {/* 头部: 基金名称 + 评级标签 */}
      <div className="flex items-start justify-between gap-2 mb-2">
        <div className="flex-1 min-w-0">
          <p className={clsx('font-bold text-gray-800 truncate', compact ? 'text-xs' : 'text-sm')}>
            {fund.fund_name}
          </p>
          <div className="flex items-center gap-1.5 mt-0.5">
            <span className="text-[10px] text-gray-400 font-mono">{fund.fund_code}</span>
            <span className="text-[9px] text-gray-300">|</span>
            <span className="text-[10px] text-gray-400">
              {fund.fund_level === 1 ? '一级' : '二级'}
            </span>
            {fund.status === 'reserved' && (
              <>
                <span className="text-[9px] text-gray-300">|</span>
                <span className="text-[10px] text-gray-400">储备</span>
              </>
            )}
          </div>
        </div>
        {/* 建仓评级标签 */}
        <span
          className={clsx(
            'shrink-0 text-[10px] font-bold px-2 py-0.5 rounded-full border',
            cfg.bg,
            cfg.text,
            cfg.border,
          )}
        >
          {cfg.label}
        </span>
      </div>

      {/* 细分赛道标签 (二级基金) + 跟踪指数 */}
      {fund.fund_level === 2 && fund.sub_sector && (
        <div className="mb-1.5">
          <span className="inline-block text-[10px] font-medium px-1.5 py-0.5 rounded bg-blue-50 text-blue-600 border border-blue-100">
            {fund.sub_sector}
          </span>
        </div>
      )}
      {!compact && (
        <p className="text-[10px] text-gray-400 mb-2 truncate">
          跟踪: {fund.track_index}
          {fund.track_index_code && (
            <span className="text-gray-300 font-mono ml-1">({fund.track_index_code})</span>
          )}
        </p>
      )}

      {/* 评级原因 */}
      {fund.rating_reason && (
        <div className={clsx('rounded-lg p-1.5 mb-2', cfg.bg)}>
          <p className={clsx('text-[10px] leading-relaxed', cfg.text)}>
            {fund.rating_reason}
          </p>
        </div>
      )}

      {/* 拟合度 */}
      <div className="flex items-center gap-3 mb-2">
        <div className="flex-1">
          <p className="text-[9px] text-gray-400">拟合度</p>
          <p className="text-xs font-bold font-mono text-gray-600 flex items-center gap-0.5">
            <Star className="w-3 h-3 text-yellow-400" />
            {fund.fit_degree.toFixed(2)}
          </p>
        </div>
        <div className="flex-1">
          <p className="text-[9px] text-gray-400">级别</p>
          <p className="text-xs font-bold text-gray-600">
            {fund.fund_level === 1 ? '一级行业' : '二级细分'}
          </p>
          {fund.fund_level === 2 && fund.sub_sector && (
            <p className="text-[9px] text-blue-500 truncate">{fund.sub_sector}</p>
          )}
        </div>
        <div className="flex-1">
          <p className="text-[9px] text-gray-400">状态</p>
          <p className={clsx(
            'text-xs font-bold',
            fund.status === 'active' ? 'text-green-600' : 'text-gray-400',
          )}>
            {fund.status === 'active' ? '可用' : '储备'}
          </p>
        </div>
      </div>

      {/* 操作按钮 */}
      <div className="flex items-center gap-2 pt-1 border-t border-gray-50">
        <button
          onClick={handleAddWatchlist}
          className="flex items-center gap-1 text-[10px] text-brand-500 hover:text-brand-600 transition-colors"
        >
          <Plus className="w-3 h-3" />
          加自选
        </button>
        <button
          onClick={handleViewDetail}
          className="flex items-center gap-1 text-[10px] text-gray-400 hover:text-gray-600 transition-colors ml-auto"
        >
          查看详情
          <ExternalLink className="w-3 h-3" />
        </button>
      </div>
    </div>
  );
}
