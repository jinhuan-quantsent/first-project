/**
 * FundDetailPanel - 右侧详情面板
 * 包含: 基本信息 + 情绪信号 + 今日评估 + 趋势判断
 */
import type { FundSearchItem, FundDetail, SignalLevel } from '../../types';
import { SIGNAL_LABELS } from '../../types';
import { X } from 'lucide-react';
import { clsx } from 'clsx';

/** 安全取数，防止 undefined/null 调用 .toFixed() 崩溃 */
const safeNum = (v: number | undefined | null, fallback = 0): number => v ?? fallback;

/** 信号徽章背景色映射 */
const SIGNAL_BG: Record<SignalLevel, string> = {
  'S+': 'bg-emerald-600 text-white',
  'S':  'bg-emerald-500 text-white',
  'A':  'bg-teal-400 text-white',
  'B':  'bg-amber-400 text-white',
  'C':  'bg-amber-500 text-white',
  'D':  'bg-rose-500 text-white',
  'E':  'bg-rose-600 text-white',
};

/** 信号文字颜色 */
const SIGNAL_TEXT: Record<SignalLevel, string> = {
  'S+': 'text-emerald-600',
  'S':  'text-emerald-500',
  'A':  'text-teal-500',
  'B':  'text-amber-500',
  'C':  'text-amber-600',
  'D':  'text-rose-500',
  'E':  'text-rose-600',
};

/** 趋势方向文案 */
const TREND_LABEL: Record<SignalLevel, { text: string; color: string }> = {
  'S+': { text: '看多', color: 'text-emerald-600' },
  'S':  { text: '看多', color: 'text-emerald-500' },
  'A':  { text: '偏多', color: 'text-teal-500' },
  'B':  { text: '中性', color: 'text-gray-500' },
  'C':  { text: '偏空', color: 'text-amber-500' },
  'D':  { text: '看空', color: 'text-rose-500' },
  'E':  { text: '看空', color: 'text-rose-600' },
};

/** 趋势理由默认文案 */
const TREND_REASONS: Record<string, string> = {
  'shortTerm': '板块触底+恐慌极致值',
  'midTerm': '行业周期支撑',
  'longTerm': '长期成长趋势',
};

interface FundDetailPanelProps {
  fund: FundSearchItem;
  detail: FundDetail | null;
  sentiment: {
    score: number;
    signalLevel: SignalLevel;
    confidenceStars: number;
    shortTerm: SignalLevel;
    midTerm: SignalLevel;
    longTerm: SignalLevel;
    reason?: string;
  } | null;
  loading: boolean;
  onClose: () => void;
}

export default function FundDetailPanel({
  fund,
  detail,
  sentiment,
  loading,
  onClose,
}: FundDetailPanelProps) {
  if (loading) {
    return (
      <div className="p-6 space-y-4 animate-pulse">
        <div className="h-8 w-48 bg-gray-200 rounded" />
        <div className="h-20 w-full bg-gray-100 rounded-xl" />
        <div className="h-24 w-full bg-gray-100 rounded-xl" />
        <div className="h-24 w-full bg-gray-100 rounded-xl" />
      </div>
    );
  }

  const level = sentiment?.signalLevel;
  const label = level ? SIGNAL_LABELS[level] : '';
  const score = sentiment?.score;

  return (
    <div className="h-full flex flex-col">
      {/* 标题栏：基金名 + 代码 + 关闭按钮 */}
      <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100 shrink-0">
        <div className="min-w-0">
          <h3 className="text-lg font-bold text-gray-900 truncate">
            {fund.fund_short_name || fund.fund_name}
          </h3>
          <p className="text-sm text-gray-400 font-mono mt-0.5">
            {fund.fund_code}
          </p>
        </div>
        <button
          onClick={onClose}
          className="p-2 rounded-lg hover:bg-gray-100 transition-colors shrink-0"
          aria-label="关闭面板"
        >
          <X className="w-5 h-5 text-gray-400" />
        </button>
      </div>

      {/* 内容区：可滚动 */}
      <div className="flex-1 overflow-y-auto px-6 py-5 space-y-5">
        {/* ===== 基本信息 ===== */}
        <section>
          <h4 className="text-xs font-medium text-gray-400 mb-2">基本信息</h4>
          <div className="space-y-2.5">
            <InfoRow label="基金类型" value={fund.fund_type || '-'} />
            <InfoRow
              label="基金规模"
              value={
                fund.fund_size
                  ? `${safeNum(fund.fund_size).toFixed(1)}亿`
                  : '-'
              }
            />
            <InfoRow label="基金经理" value={detail?.manager || '-'} />
            <InfoRow label="成立日期" value={detail?.inception_date || '-'} />
          </div>
        </section>

        {/* ===== 情绪信号 ===== */}
        {sentiment && level && (
          <section>
            <h4 className="text-xs font-medium text-gray-400 mb-2">情绪信号</h4>
            <div className="flex items-center gap-3 mb-3">
              <span
                className={clsx(
                  'px-3 py-1.5 rounded-lg text-sm font-bold whitespace-nowrap',
                  SIGNAL_BG[level],
                )}
              >
                {level}·{label}
              </span>
              <span className={clsx('text-2xl font-bold', SIGNAL_TEXT[level])}>
                {safeNum(score).toFixed(0)}分
              </span>
            </div>
            {sentiment.reason && (
              <div className="bg-gray-50 rounded-lg p-3">
                <p className="text-xs text-gray-600 leading-relaxed">
                  {sentiment.reason}
                </p>
              </div>
            )}
          </section>
        )}

        {/* ===== 今日评估 ===== */}
        <section>
          <h4 className="text-xs font-medium text-gray-400 mb-2">今日评估</h4>
          <div className="flex items-start gap-2">
            <span
              className={clsx(
                'w-2 h-2 rounded-full mt-1.5 shrink-0',
                safeNum(fund.daily_return) >= 0
                  ? 'bg-emerald-500'
                  : 'bg-rose-500',
              )}
            />
            <p className="text-sm text-gray-700 leading-relaxed">
              净值估算
              {safeNum(fund.daily_return) >= 0 ? '上涨' : '下跌'}
              {Math.abs(safeNum(fund.daily_return)).toFixed(2)}%
              {safeNum(fund.daily_return) >= 0
                ? '，板块回暖'
                : '，板块调整'}
            </p>
          </div>
        </section>

        {/* ===== 趋势判断 ===== */}
        {sentiment && (
          <section>
            <h4 className="text-xs font-medium text-gray-400 mb-2">趋势判断</h4>
            <div className="grid grid-cols-3 gap-2">
              <TrendCard
                title="短期"
                level={sentiment.shortTerm}
                reason={TREND_REASONS['shortTerm']}
              />
              <TrendCard
                title="中期"
                level={sentiment.midTerm}
                reason={TREND_REASONS['midTerm']}
              />
              <TrendCard
                title="长期"
                level={sentiment.longTerm}
                reason={TREND_REASONS['longTerm']}
              />
            </div>
          </section>
        )}
      </div>
    </div>
  );
}

/** 信息行组件 */
function InfoRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between">
      <span className="text-sm text-gray-400">{label}</span>
      <span className="text-sm font-medium text-gray-900">{value}</span>
    </div>
  );
}

/** 趋势卡片组件 */
function TrendCard({
  title,
  level,
  reason,
}: {
  title: string;
  level: SignalLevel;
  reason: string;
}) {
  const trend = TREND_LABEL[level];
  return (
    <div className="border border-gray-200 rounded-lg p-3 text-center">
      <p className="text-xs text-gray-400 mb-1">{title}</p>
      <p className={clsx('text-lg font-bold', trend.color)}>{trend.text}</p>
      <p className="text-[11px] text-gray-400 mt-1 leading-tight">{reason}</p>
    </div>
  );
}
