/**
 * FundDetailPanel - 右侧详情面板
 * 包含: 基本信息 + 情绪信号 + 今日评估 + 趋势判断
 */
import type { FundSearchItem, FundDetail, SignalLevel } from '../../types';
import { SIGNAL_LABELS } from '../../types';
import { X, AlertTriangle } from 'lucide-react';
import { clsx } from 'clsx';
import ExpandableReason, { adaptReason, inferActionAdvice } from '../common/ExpandableReason';

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
              <ExpandableReason
                reason={adaptReason(sentiment.reason, sentiment.signalLevel as SignalLevel | undefined)}
                signalLevel={sentiment.signalLevel as SignalLevel | undefined}
                actionAdvice={inferActionAdvice(sentiment.signalLevel as SignalLevel | undefined)}
                variant="panel"
                defaultExpanded={true}
              />
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

        {/* ===== 风险提示 ===== */}
        <section>
          <h4 className="text-xs font-medium text-gray-400 mb-2 flex items-center gap-1">
            <AlertTriangle className="w-3 h-3" />
            风险提示
          </h4>
          <FundRiskWarnings fund={fund} detail={detail} />
        </section>
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

/** 风险类型定义 */
interface RiskTag {
  label: string;
  level: 'high' | 'medium' | 'low';
  detail: string;
}

const RISK_LEVEL_STYLE = {
  high: 'bg-red-50 text-red-600 border-red-200',
  medium: 'bg-amber-50 text-amber-600 border-amber-200',
  low: 'bg-blue-50 text-blue-600 border-blue-200',
};

/**
 * 基金风险提示组件
 * 基于基金基本信息生成风险标签：
 * - 规模过小/过大
 * - 经理信息缺失
 * - 风格漂移（类型不匹配跟踪指数）
 * - 费率相关提示
 */
function FundRiskWarnings({ fund, detail }: { fund: FundSearchItem; detail: FundDetail | null }) {
  const risks: RiskTag[] = [];

  // 1. 规模风险
  const size = safeNum(fund.fund_size);
  if (size > 0 && size < 2) {
    risks.push({
      label: '迷你基金',
      level: 'high',
      detail: `规模仅${size.toFixed(1)}亿，存在清盘风险`,
    });
  } else if (size > 200) {
    risks.push({
      label: '超大基金',
      level: 'medium',
      detail: `规模${size.toFixed(1)}亿，船大难掉头，超额收益可能收窄`,
    });
  }

  // 2. 经理信息缺失
  if (!detail?.manager || detail.manager === '-' || detail.manager === '未知') {
    risks.push({
      label: '经理不明',
      level: 'medium',
      detail: '基金经理信息缺失，无法评估管理能力',
    });
  }

  // 3. 风格漂移检测（指数基金但无跟踪指数）
  if (fund.fund_type === '指数型' && detail?.tracking_index && detail.tracking_index === '-') {
    risks.push({
      label: '风格漂移',
      level: 'medium',
      detail: '指数型基金未标注跟踪指数，可能存在风格漂移',
    });
  }

  // 4. 新基金风险（成立不足1年）
  if (detail?.inception_date) {
    const inception = new Date(detail.inception_date);
    const ageYears = (Date.now() - inception.getTime()) / (365.25 * 24 * 60 * 60 * 1000);
    if (ageYears < 1) {
      risks.push({
        label: '新基金',
        level: 'medium',
        detail: `成立不足1年（${ageYears.toFixed(1)}年），历史数据不充分`,
      });
    }
  }

  // 5. 收益异常（年内涨跌幅超过40%或低于-30%）
  const yearReturn = safeNum(fund.year_return);
  if (Math.abs(yearReturn) > 40) {
    risks.push({
      label: yearReturn > 0 ? '收益异常高' : '跌幅过大',
      level: 'medium',
      detail: `年内${yearReturn > 0 ? '涨幅' : '跌幅'}${Math.abs(yearReturn).toFixed(1)}%，波动剧烈`,
    });
  }

  if (risks.length === 0) {
    return (
      <div className="flex items-center gap-2 py-2">
        <span className="w-2 h-2 rounded-full bg-emerald-400" />
        <span className="text-xs text-gray-500">暂无明显风险提示</span>
      </div>
    );
  }

  return (
    <div className="space-y-1.5">
      {risks.map((risk, idx) => (
        <div
          key={idx}
          className={clsx(
            'flex items-start gap-2 px-2.5 py-1.5 rounded-lg border',
            RISK_LEVEL_STYLE[risk.level],
          )}
        >
          <AlertTriangle className="w-3 h-3 mt-0.5 shrink-0" />
          <div className="min-w-0">
            <span className="text-xs font-medium">{risk.label}</span>
            <p className="text-[10px] opacity-80 mt-0.5 leading-tight">{risk.detail}</p>
          </div>
        </div>
      ))}
    </div>
  );
}
