/**
 * SectorWarnings - 风险警示板块组件
 * 标题始终渲染，空态显示灰色"暂无风险警示"
 * 有数据时渲染警示列表 + max-h 防撑开
 * 放置在 SectorCards 和 OpportunityRadarPanel 之间
 */
import { AlertTriangle, ShieldAlert } from 'lucide-react';
import { clsx } from 'clsx';

interface SectorWarningItem {
  sector_name: string;
  sentiment_score: number;
  momentum_5d: number;
  reason: string;
  /** 警示类型：overheated=过热警告, weak=疲软警告 */
  warning_type: 'overheated' | 'weak';
}

interface SectorWarningsProps {
  items?: SectorWarningItem[];
  loading?: boolean;
}

/** 警示类型配置 */
const WARNING_CFG = {
  overheated: {
    icon: AlertTriangle,
    label: '过热',
    bg: 'bg-red-50',
    border: 'border-red-200',
    text: 'text-red-700',
    accent: 'border-l-red-400',
    dotColor: 'bg-red-400',
  },
  weak: {
    icon: ShieldAlert,
    label: '疲软',
    bg: 'bg-amber-50',
    border: 'border-amber-200',
    text: 'text-amber-700',
    accent: 'border-l-amber-400',
    dotColor: 'bg-amber-400',
  },
} as const;

export default function SectorWarnings({ items, loading }: SectorWarningsProps) {
  const hasWarnings = items && items.length > 0;

  return (
    <div className="card p-4 bg-gray-50 transition-all duration-300">
      {/* 标题始终渲染 */}
      <div className="flex items-center gap-2 mb-3">
        <AlertTriangle className="w-4 h-4 text-amber-500" />
        <h3 className="text-sm font-bold text-gray-700">风险警示</h3>
        {hasWarnings && (
          <span className="text-[10px] px-1.5 py-0.5 rounded-full bg-amber-100 text-amber-600 font-medium">
            {items!.length}
          </span>
        )}
      </div>

      {loading ? (
        <div className="space-y-2 animate-pulse">
          {Array.from({ length: 3 }, (_, i) => (
            <div key={i} className="h-10 bg-gray-100 rounded" />
          ))}
        </div>
      ) : hasWarnings ? (
        <div className="space-y-2 max-h-[240px] overflow-y-auto">
          {items!.map((item) => {
            const cfg = WARNING_CFG[item.warning_type] || WARNING_CFG.weak;
            const Icon = cfg.icon;
            return (
              <div
                key={item.sector_name}
                className={clsx(
                  'flex items-center gap-3 px-3 py-2 rounded-lg border-l-3',
                  cfg.bg, cfg.accent,
                )}
              >
                <Icon className={clsx('w-3.5 h-3.5 shrink-0', cfg.text)} />
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-1.5">
                    <span className={clsx('text-xs font-medium', cfg.text)}>
                      {item.sector_name}
                    </span>
                    <span className={clsx('text-[10px] px-1 py-0.5 rounded', cfg.bg, cfg.text)}>
                      {cfg.label}
                    </span>
                  </div>
                  <p className="text-[10px] text-gray-400 truncate mt-0.5">
                    情绪 {item.sentiment_score} · 5日动量 {item.momentum_5d > 0 ? '+' : ''}{item.momentum_5d.toFixed(1)}%
                  </p>
                </div>
                <p className="text-[10px] text-gray-400 max-w-[140px] truncate shrink-0">
                  {item.reason}
                </p>
              </div>
            );
          })}
        </div>
      ) : (
        /* 空态：灰色弱化文案 */
        <p className="text-xs text-gray-400 py-2">暂无风险警示</p>
      )}
    </div>
  );
}