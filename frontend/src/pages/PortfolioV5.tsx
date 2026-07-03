/**
 * PortfolioV5 - 持仓页重设计 V5
 * 总览头部 + 列表行 + 详情展开面板
 * 对齐设计稿 Image4 + Image5
 */
import { useState, useCallback, useEffect, useRef, useMemo } from 'react';
import type { PortfolioItem, PortfolioSummary, SignalLevel } from '../types';
import { SIGNAL_LABELS } from '../types';
import PositionDetailPanel, { type PositionDetailData } from '../components/portfolio/PositionDetailPanel';
import SectorFundCard from '../components/sector/SectorFundCard';
import { Briefcase, Pencil, Check, X, ChevronDown, ChevronUp, Lightbulb } from 'lucide-react';
import { clsx } from 'clsx';
import {
  fetchPortfolioV5,
  executePositionV5,
  updatePortfolioMarketValue,
  fetchAdviceHistoryV5,
  fetchTradeRecordsV5,
  fetchCashV5,
  updateCashV5,
  deletePortfolioV5,
  increasePosition,
  decreasePosition,
  fetchPositionAdviceV5,
} from '../api/portfolioV5';
import { fetchV5Sentiment } from '../api/marketV5';
import { fetchSectorFunds } from '../api/sectorDetailV5';
import type { SectorFund } from '../types/positionRating';
import { toast } from '../components/common/Toast';
import StarRating from '../components/portfolio/StarRating';
import client from '../api/client';

/* ============================================================
   Gate角标样式映射 + 轨道标签样式映射
   ============================================================ */
const GATE_BADGE: Record<string, { label: string; cls: string }> = {
  'gate-1': { label: '止损线', cls: 'bg-red-100 text-red-700 text-xs px-1.5 py-0.5 rounded' },
  'gate-2': { label: '趋势破位', cls: 'bg-red-100 text-red-700 text-xs px-1.5 py-0.5 rounded' },
  'gate-e': { label: '过热提示', cls: 'bg-amber-100 text-amber-700 text-xs px-1.5 py-0.5 rounded' },
};

const REGIME_BADGE: Record<string, { label: string; cls: string }> = {
  'contrarian': { label: '逆向', cls: 'text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded text-xs' },
  'excluded': { label: '排除', cls: 'text-red-500 bg-red-50 px-1.5 py-0.5 rounded text-xs' },
  'bear': { label: '熊市', cls: 'text-gray-500 bg-gray-100 px-1.5 py-0.5 rounded text-xs' },
  'sideways': { label: '震荡', cls: 'text-gray-400 bg-gray-50 px-1.5 py-0.5 rounded text-xs' },
  'bull': { label: '牛市', cls: 'text-green-600 bg-green-50 px-1.5 py-0.5 rounded text-xs' },
  'extreme_volatility': { label: '极端波动', cls: 'text-red-600 bg-red-50 px-1.5 py-0.5 rounded text-xs' },
};

// 轨道标签 — 基于 track_type（每日动态信号产物，非标的固定属性）
const TRACK_BADGE: Record<string, { label: string; cls: string }> = {
  'contrarian': { label: '逆向', cls: 'text-amber-600 bg-amber-50 px-1.5 py-0.5 rounded text-xs' },
  'trend_follow': { label: '趋势', cls: 'text-teal-600 bg-teal-50 px-1.5 py-0.5 rounded text-xs' },
  'excluded': { label: '排除', cls: 'text-red-500 bg-red-50 px-1.5 py-0.5 rounded text-xs' },
};

// 操作建议标签
const ACTION_BADGE: Record<string, { label: string; cls: string }> = {
  'increase': { label: '建议加仓', cls: 'bg-red-50 text-red-600 text-[10px] px-1.5 py-0.5 rounded font-medium' },
  'decrease': { label: '建议减仓', cls: 'bg-green-50 text-green-600 text-[10px] px-1.5 py-0.5 rounded font-medium' },
  'hold': { label: '持有', cls: 'bg-gray-50 text-gray-500 text-[10px] px-1.5 py-0.5 rounded font-medium' },
  'watch': { label: '观望', cls: 'bg-amber-50 text-amber-600 text-[10px] px-1.5 py-0.5 rounded font-medium' },
};

/* ============================================================
   信号颜色映射
   ============================================================ */
const SIGNAL_BG: Record<string, string> = {
  'S+': 'bg-emerald-100 text-emerald-700',
  S: 'bg-green-100 text-green-700',
  A: 'bg-teal-100 text-teal-700',
  B: 'bg-amber-100 text-amber-700',
  C: 'bg-orange-100 text-orange-700',
  D: 'bg-red-100 text-red-700',
  E: 'bg-rose-100 text-rose-700',
};

/* ============================================================
   工具函数
   ============================================================ */
/** 格式化金额（自动万元） */
function formatMoney(v: number): string {
  if (Math.abs(v) >= 10000) {
    return `¥${(v / 10000).toFixed(2)}万`;
  }
  return `¥${v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/** 格式化金额（始终完整） */
function formatMoneyFull(v: number): string {
  return `¥${v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/** 格式化涨跌值（A股：红涨绿跌） */
function formatChangeValue(v: number): { text: string; cls: string } {
  const sign = v >= 0 ? '+' : '';
  const cls = v >= 0 ? 'text-red-500' : 'text-green-500';
  return {
    text: `${sign}¥${Math.abs(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`,
    cls,
  };
}

/** 格式化涨跌率 */
function formatChangeRate(v: number): { text: string; cls: string } {
  const sign = v >= 0 ? '+' : '';
  const cls = v >= 0 ? 'text-red-500' : 'text-green-500';
  return { text: `${sign}${v.toFixed(2)}%`, cls };
}

/** 四舍五入到2位小数 */
function round2(v: number): number {
  return Math.round(v * 100) / 100;
}

/* ============================================================
   Mock 数据生成器
   为详情面板生成合理的 mock 数据
   ============================================================ */
function buildRealDetailData(
  item: PortfolioItem,
  signal: { signalLevel: SignalLevel; confidenceStars: number; factorDetails?: any[] } | undefined,
  navHistory: { date: string; nav: number; daily_return?: number }[] | undefined,
  topStocks: { name: string; pct: number; change: number }[] | undefined,
  evaluation: any | undefined,
  sentimentDetail: any | undefined,
  adviceData?: { items: any[]; stats: any } | undefined,
  tradeRecords?: any[] | undefined,
  overallTargetPct?: number | null,
  positionAdvice?: {
    trendText?: string; marketStatus?: string; trendGuard?: any;
    action?: string; reason?: string; target_position_pct?: number; trend_guard_text?: string;
  } | undefined,
  totalValue?: number,
  cashAmount?: number,
  totalAssets?: number,
): PositionDetailData {
  const signalLevel = signal?.signalLevel ?? 'B';
  const signalLabel = SIGNAL_LABELS[signalLevel] ?? '中性';

  // 操作建议完全依赖后端 action 字段，前端不做信号级判断
  const backendAction = positionAdvice?.action;
  let operationTag: PositionDetailData['operationTag'] = '持有';
  if (backendAction === 'increase') operationTag = '加仓';
  else if (backendAction === 'decrease') operationTag = '减仓';
  else if (backendAction === 'hold') operationTag = '持有';
  // action 为 null/undefined -> 默认持有（数据异常兜底）

  const opReason = positionAdvice?.reason || '';
  const backendTargetPct = positionAdvice?.target_position_pct;
  const backendTrendGuardText = positionAdvice?.trend_guard_text || positionAdvice?.trendText || '';

  // 从 V5 因子详情构建推荐理由
  const factorNames: Record<string, string> = {
    VOL: '波动率', TURN: '换手率', RATIO: '涨跌比', NEWF: '新高占比',
    MARGIN: '融资融券', ERP: '股债利差', RSI: 'RSI指标',
    FLOW: '北向资金', ETF: 'ETF流入', POS: '基金仓位', NBF: '非银融资',
    PCR: '看跌看涨比', NHNL: '新高新低', ADR: '涨跌比',
    INDUSTRY_DIVERGENCE: '行业分歧度',
  };

  // 优先使用后端返回的 reason
  let recommendationReason = opReason || '';
  if (sentimentDetail?.factors && Array.isArray(sentimentDetail.factors)) {
    const topFactors = [...sentimentDetail.factors]
      .sort((a: any, b: any) => (b.sigmoid_score || b.raw_score || 0) - (a.sigmoid_score || a.raw_score || 0))
      .slice(0, 3);
    const factorTexts = topFactors.map((f: any) =>
      `${factorNames[f.name] || f.name}${Math.round((f.sigmoid_score || f.raw_score || 0) * 100)}分`
    );
    recommendationReason = `基于${signalLabel}信号分析，当前市场情绪处于${signalLabel}区间(${signal?.confidenceStars ?? 3}星置信)。${factorTexts.join('+')}触发${signalLabel}信号，建议${operationTag}。该基金近期表现${item.return_rate >= 0 ? '优于' : '弱于'}基准${Math.abs(item.return_rate).toFixed(1)}%，${operationTag === '加仓' ? '逆向操作逢低布局' : operationTag === '减仓' ? '止盈减仓控制风险' : '维持当前仓位观察'}。`;
  } else if (!recommendationReason) {
    recommendationReason = `基于${signalLabel}信号分析，当前市场情绪处于${signalLabel}区间(${signal?.confidenceStars ?? 3}星置信)，建议${operationTag}。该基金近期${item.return_rate >= 0 ? '表现优于基准' : '弱于基准'}${Math.abs(item.return_rate).toFixed(1)}%。`;
  }

  // 从 evaluation 构建 趋势判断
  const shortTerm = evaluation?.short_term
    ? { label: evaluation.short_term.label || evaluation.short_term.judgment || '中性', reason: evaluation.short_term.reason || `${evaluation.short_term.period || '短期'}: ${evaluation.short_term.return_pct?.toFixed(2) ?? 0}%` }
    : { label: signalLevel === 'S+' || signalLevel === 'S' ? '看多' : signalLevel === 'E' ? '看空' : '中性', reason: '基于信号推断' };

  const midTerm = evaluation?.mid_term
    ? { label: evaluation.mid_term.label || evaluation.mid_term.judgment || '中性', reason: evaluation.mid_term.reason || `${evaluation.mid_term.period || '中期'}: ${evaluation.mid_term.return_pct?.toFixed(2) ?? 0}%` }
    : { label: '中性', reason: '数据不足' };

  const longTerm = evaluation?.long_term
    ? { label: evaluation.long_term.label || evaluation.long_term.judgment || '长期配置', reason: evaluation.long_term.reason || '建议长期持有' }
    : { label: '长期配置', reason: '数据不足' };

  // 从 daily_return + signal 构建 今日评估
  const todayEvaluation = `净值估${item.daily_return >= 0 ? '增' : '减'}${Math.abs(item.daily_return).toFixed(2)}%，${signalLabel}信号${signal?.confidenceStars != null ? signal.confidenceStars + '星' : '低'}置信度`;

  // complianceStars 直接使用 V5 引擎置信度（1-4星制，不再二次换算）
  const complianceStars = signal?.confidenceStars ?? 0;

  return {
    fundCode: item.fund_code,
    fundName: (item as any).fund_short_name || item.fund_name,
    marketValue: item.market_value,
    dailyReturn: item.daily_return,
    holdingReturn: item.total_return,
    holdingReturnRate: item.return_rate,
    signalLevel,
    confidenceStars: signal?.confidenceStars ?? 3,
    signalReason: `${signalLevel}·${signalLabel}，${opReason || '维持持有'}`,

    complianceStars,
    complianceDirection: 'new',
    operationTag,
    recommendationReason,
    updateNote: `更新市值${formatMoney(item.market_value)}（${item.return_rate >= 0 ? '涨' : '跌'}${Math.abs(item.return_rate).toFixed(1)}%）`,

    winRate: adviceData?.stats?.win_rate ?? 0,
    winRateDetail: adviceData?.stats?.verified_count
      ? `${adviceData.stats.verified_count}条已验证`
      : '',
    performanceRecords: (adviceData?.items || []).slice(0, 10).map((a: any) => ({
      date: a.date?.slice(0, 10) || '',
      signal: a.signal_level || '',
      operation: a.advice_type === 'buy' ? '买入' : a.advice_type === 'reduce' ? '减仓' : a.advice_type === 'hold' ? '持有' : '观望',
      position: a.suggested_position != null ? `${a.suggested_position.toFixed(1)}%` : '-',
      isExecuted: !!a.is_executed,
      correctUp: a.is_verified && a.actual_result > 0,
      correctDown: a.is_verified && a.actual_result < 0,
      returnPct: a.actual_result || 0,
      reason: a.advice_content || '',
    })),

    tradeRecords: (tradeRecords || []).slice(0, 10).map((t: any) => ({
      date: t.date || '',
      type: t.type || '调仓',
      amount: t.amount || 0,
      nav: t.nav || 0,
      fee: t.fee || 0,
    })),

    navHistory: (navHistory ?? []).map((p) => ({
      date: p.date || '',
      nav: p.nav || 0,
      daily_return: p.daily_return,
    })),

    topHoldings: topStocks?.map(s => ({
      name: s.name,
      pct: s.pct * 100,
      description: s.name.includes('半导体') ? '半导体设备龙头，国产替代核心标的' :
        s.name.includes('金山') ? '办公软件龙头，AI赋能收入增速预期' :
        s.name.includes('中兴') ? '通信设备主业，产研投研能力领先' :
        `${s.name}核心标的`,
    })) ?? [],

    morningStarRating: 0,  // 暂无真实数据
    ratingDetails: [],  // 暂无真实数据

    todayEvaluation,
    shortTerm,
    midTerm,
    longTerm,
    trendText: positionAdvice?.trendText,
    marketStatus: positionAdvice?.marketStatus,
    trendGuard: positionAdvice?.trendGuard,
    // 后端决策结果（纯展示字段）
    action: backendAction ?? null,
    reason: opReason,
    targetPositionPct: backendTargetPct,
    totalValue: totalAssets ?? totalValue,
    cashAmount: cashAmount,
    totalAssets: totalAssets ?? totalValue,
    trendGuardText: backendTrendGuardText,
    currentPositionPct: positionAdvice?.current_position_pct ?? item.weight_pct,  // V5.1: 优先用positionAdvice总资产分母(含cash)，fallback旧weight_pct仅持仓
    // V5.1 新增字段
    suggestedTargetPct: positionAdvice?.suggested_target_pct,
    suggestedBuyAmount: positionAdvice?.suggested_buy_amount,
    suggestedSellAmount: positionAdvice?.suggested_sell_amount,
    denominatorType: positionAdvice?.denominator_type,
    cashWarning: positionAdvice?.cash_warning,
    portfolioConstraints: positionAdvice?.portfolio_constraints,
    constraintDetail: positionAdvice?.constraint_detail,
  };
}

/* ============================================================
   总览头部组件
   ============================================================ */
function PortfolioHeader({
  summary,
  cashAmount,
  onCashSave,
}: {
  summary: PortfolioSummary | null;
  cashAmount: number;
  onCashSave: (amount: number) => Promise<void>;
}) {
  const [editingCash, setEditingCash] = useState(false);
  const [cashInput, setCashInput] = useState('');
  const [savingCash, setSavingCash] = useState(false);

  if (!summary) {
    return (
      <div className="mb-4">
        <h1 className="text-xl font-bold text-gray-800">我的持仓</h1>
      </div>
    );
  }

  const yesterdayPL = formatChangeValue(summary.daily_return);
  const holdingPL = formatChangeValue(summary.total_return);
  const holdingRate = formatChangeRate(summary.total_return_rate);
  const totalAssets = summary.total_assets ?? (summary.total_value + cashAmount);

  const handleStartEditCash = () => {
    setCashInput(String(Math.round(cashAmount)));
    setEditingCash(true);
  };

  const handleSaveCash = async () => {
    const numVal = parseFloat(cashInput);
    if (isNaN(numVal) || numVal < 0) {
      toast.error('请输入有效金额');
      return;
    }
    setSavingCash(true);
    try {
      await onCashSave(numVal);
      setEditingCash(false);
      setCashInput('');
    } catch {
      // error handled by parent
    } finally {
      setSavingCash(false);
    }
  };

  const handleCancelEditCash = () => {
    setEditingCash(false);
    setCashInput('');
  };

  return (
    <div className="mb-4">
      {/* 标题行 */}
      <h1 className="text-xl font-bold text-gray-800 mb-3">我的持仓</h1>

      {/* 分隔线 */}
      <div className="border-t border-gray-200 mb-4" />

      {/* 三栏：持仓市值 | 可用现金 | 总资产 */}
      <div className="flex items-start justify-between gap-4 mb-4">
        {/* 持仓市值 */}
        <div className="flex-1">
          <p className="text-xs text-gray-400 mb-1">持仓市值</p>
          <p className="text-2xl font-bold text-gray-900 font-mono">
            {formatMoneyFull(summary.total_value)}
          </p>
        </div>

        {/* 可用现金（可编辑） */}
        <div className="flex-1">
          <p className="text-xs text-gray-400 mb-1">可用现金</p>
          {editingCash ? (
            <div className="flex items-center gap-1">
              <span className="text-sm text-gray-400">¥</span>
              <input
                type="text"
                value={cashInput}
                onChange={(e) => setCashInput(e.target.value.replace(/[^\d.]/g, ''))}
                onKeyDown={(e) => {
                  if (e.key === 'Enter') handleSaveCash();
                  if (e.key === 'Escape') handleCancelEditCash();
                }}
                className="w-24 text-lg font-bold text-gray-800 font-mono border border-[var(--brand-cyan)] rounded px-1 py-0.5 focus:outline-none focus:ring-1 focus:ring-[var(--brand-cyan)]"
                autoFocus
              />
              <button onClick={handleSaveCash} disabled={savingCash} className="text-green-500 hover:text-green-600 transition-colors">
                <Check className="w-4 h-4" />
              </button>
              <button onClick={handleCancelEditCash} className="text-gray-400 hover:text-gray-500 transition-colors">
                <X className="w-4 h-4" />
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-1">
              <p className="text-2xl font-bold text-gray-900 font-mono">
                {formatMoneyFull(cashAmount)}
              </p>
              <button
                onClick={handleStartEditCash}
                className="text-gray-300 hover:text-[var(--brand-cyan)] transition-colors ml-1"
                title="编辑现金"
              >
                <Pencil className="w-3 h-3" />
              </button>
            </div>
          )}
        </div>

        {/* 总资产 */}
        <div className="flex-1">
          <p className="text-xs text-gray-400 mb-1">总资产</p>
          <p className="text-2xl font-bold text-[var(--brand-cyan)] font-mono">
            {formatMoneyFull(totalAssets)}
          </p>
        </div>
      </div>

      {/* 4个统计指标 */}
      <div className="flex items-center gap-6 flex-wrap">
        <div className="text-right">
          <p className="text-[10px] text-gray-400 mb-0.5">最新盈亏</p>
          <p className={`text-sm font-bold font-mono ${yesterdayPL.cls}`}>
            {yesterdayPL.text}
          </p>
        </div>
        <div className="text-right">
          <p className="text-[10px] text-gray-400 mb-0.5">持仓盈亏</p>
          <p className={`text-sm font-bold font-mono ${holdingPL.cls}`}>
            {holdingPL.text}
          </p>
        </div>
        <div className="text-right">
          <p className="text-[10px] text-gray-400 mb-0.5">持有收益率</p>
          <p className={`text-sm font-bold font-mono ${holdingRate.cls}`}>
            {holdingRate.text}
          </p>
        </div>
        <div className="text-right">
          <p className="text-[10px] text-gray-400 mb-0.5">基金数量</p>
          <p className="text-sm font-bold text-gray-800">{summary.fund_count}</p>
        </div>
      </div>
    </div>
  );
}

/* ============================================================
   持仓列表行组件（支持行内编辑市值）
   ============================================================ */
function PositionCard({
  item,
  expanded,
  onToggle,
  signal,
  gates,
  targetPct,
  currentPct,
  trackType,
  regime,
  signalSwitched,
  action,
  editingCode,
  editValue,
  onStartEdit,
  onCancelEdit,
  onSaveEdit,
  onEditValueChange,
}: {
  item: PortfolioItem;
  expanded: boolean;
  onToggle: () => void;
  signal: { signalLevel: SignalLevel; confidenceStars: number } | undefined;
  gates: any;
  targetPct?: number | null;
  currentPct?: number | null;
  trackType: string | null | undefined;
  regime: string | null | undefined;
  signalSwitched: boolean | undefined;
  action?: string | null | undefined;
  editingCode: string | null;
  editValue: string;
  onStartEdit: (fundCode: string) => void;
  onCancelEdit: () => void;
  onSaveEdit: (fundCode: string) => void;
  onEditValueChange: (val: string) => void;
}) {
  const inputRef = useRef<HTMLInputElement>(null);
  const fundShortName = (item as any).fund_short_name || item.fund_name;
  const daily = formatChangeValue(item.daily_return);
  const holding = formatChangeValue(item.total_return);
  const holdingRate = formatChangeRate(item.return_rate);
  const signalLevel = signal?.signalLevel;
  const signalLabel = signalLevel ? SIGNAL_LABELS[signalLevel] : '';
  const isEditing = editingCode === item.fund_code;

  // Gate 状态
  const gate1Triggered = gates?.gate_1?.triggered;
  const gate2Triggered = gates?.gate_2?.triggered && !gates?.gate_2?.exempted;
  const gate2Exempted = gates?.gate_2?.exempted;
  const gateETriggered = gates?.gate_e?.triggered;
  const hasAlert = gate1Triggered || gate2Triggered || gateETriggered;
  const overallStatus = gates?.overall_status
    || (gate1Triggered || gate2Triggered ? 'stop_loss'
      : gateETriggered ? 'warning' : 'normal');

  // 卡片边框颜色基于风控状态
  const cardBorderCls = overallStatus === 'stop_loss'
    ? 'border-red-200 bg-red-50/30'
    : overallStatus === 'warning'
      ? 'border-amber-200 bg-amber-50/30'
      : 'border-gray-200 bg-white';

  useEffect(() => {
    if (isEditing && inputRef.current) {
      inputRef.current.focus();
      inputRef.current.select();
    }
  }, [isEditing]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') onSaveEdit(item.fund_code);
    if (e.key === 'Escape') onCancelEdit();
  };

  return (
    <div
      className={clsx(
        'rounded-xl border transition-all duration-200 overflow-hidden',
        cardBorderCls,
        expanded ? 'shadow-md md:col-span-2' : 'shadow-sm hover:shadow-md',
      )}
    >
      {/* 卡片头部：点击展开/收起 */}
      <div onClick={onToggle} className="cursor-pointer">
        {/* 第一行：基金名 + 信号徽章 */}
        <div className="flex items-start justify-between gap-2 px-4 pt-3">
          <div className="min-w-0 flex-1">
            <p className="text-sm font-bold text-gray-800 truncate">{fundShortName}</p>
            <div className="flex items-center gap-1 mt-0.5">
              <p className="text-[10px] text-gray-400 font-mono">{item.fund_code}</p>
              {signalSwitched && (
                <span className="text-[9px] text-orange-500 bg-orange-50 px-1 rounded">信号切换</span>
              )}
            </div>
          </div>
          <div className="flex items-center gap-1 shrink-0">
            {signal && (
              <span className={clsx(
                'text-[10px] px-1.5 py-0.5 rounded font-bold whitespace-nowrap',
                SIGNAL_BG[signalLevel ?? 'B'],
              )}>
                {signalLevel}·{signalLabel}
              </span>
            )}
            {signal && signal.confidenceStars > 0 && (
              <StarRating value={signal.confidenceStars} max={4} />
            )}
          </div>
        </div>

        {/* 第二行：标签条 */}
        <div className="flex items-center gap-1 px-4 mt-1.5 flex-wrap min-h-[20px]">
          {trackType && TRACK_BADGE[trackType] && (
            <span className={TRACK_BADGE[trackType].cls}>{TRACK_BADGE[trackType].label}</span>
          )}
          {action && ACTION_BADGE[action] && (
            <span className={ACTION_BADGE[action].cls}>{ACTION_BADGE[action].label}</span>
          )}
          {(!trackType || !TRACK_BADGE[trackType]) && regime && REGIME_BADGE[regime] && (
            <span className={REGIME_BADGE[regime].cls}>{REGIME_BADGE[regime].label}</span>
          )}
          {gate1Triggered && (
            <span className="bg-red-100 text-red-700 text-[10px] px-1.5 py-0.5 rounded font-medium">止损线</span>
          )}
          {gate2Triggered && (
            <span className="bg-red-100 text-red-700 text-[10px] px-1.5 py-0.5 rounded font-medium">趋势破位</span>
          )}
          {gate2Exempted && !gate2Triggered && (
            <span className="bg-gray-100 text-gray-500 text-[10px] px-1.5 py-0.5 rounded">MA20豁免</span>
          )}
          {gateETriggered && (
            <span className="bg-amber-100 text-amber-700 text-[10px] px-1.5 py-0.5 rounded font-medium">过热预警</span>
          )}
        </div>

        {/* 第三行：持仓市值 + 编辑 + 展开箭头 */}
        <div className="flex items-center justify-between gap-2 px-4 mt-2" onClick={(e) => e.stopPropagation()}>
          {isEditing ? (
            <div className="flex items-center gap-1">
              <span className="text-xs text-gray-400">¥</span>
              <input
                ref={inputRef}
                type="text"
                value={editValue}
                onChange={(e) => onEditValueChange(e.target.value)}
                onKeyDown={handleKeyDown}
                onBlur={() => onSaveEdit(item.fund_code)}
                className="w-24 text-lg font-bold text-gray-800 font-mono border border-[var(--brand-cyan)] rounded px-1 py-0.5 focus:outline-none focus:ring-1 focus:ring-[var(--brand-cyan)]"
              />
              <button onClick={() => onSaveEdit(item.fund_code)} className="text-green-500 hover:text-green-600 transition-colors">
                <Check className="w-4 h-4" />
              </button>
              <button onClick={(e) => { e.stopPropagation(); onCancelEdit(); }} className="text-gray-400 hover:text-gray-500 transition-colors">
                <X className="w-4 h-4" />
              </button>
            </div>
          ) : (
            <div className="flex items-center gap-1">
              <span className="text-xl font-bold text-gray-900 font-mono">{formatMoney(item.market_value)}</span>
              <button
                onClick={(e) => { e.stopPropagation(); onStartEdit(item.fund_code); }}
                className="text-gray-300 hover:text-[var(--brand-cyan)] transition-colors ml-0.5"
                title="编辑持仓"
              >
                <Pencil className="w-3 h-3" />
              </button>
            </div>
          )}
          {expanded ? (
            <ChevronUp className="w-4 h-4 text-gray-400" />
          ) : (
            <ChevronDown className="w-4 h-4 text-gray-400" />
          )}
        </div>

        {/* 净值信息行：成本净值 / 最新净值 / 持有份额 / 持仓天数 */}
        <div className="grid grid-cols-4 md:grid-cols-4 gap-1 px-3 md:px-4 mt-1.5 pb-1 border-t border-gray-50 pt-1.5">
          <div>
            <p className="text-[9px] text-gray-400">成本净值</p>
            <p className="text-[10px] font-mono text-gray-600">{item.cost_nav > 0 ? item.cost_nav.toFixed(4) : '-'}</p>
          </div>
          <div>
            <p className="text-[9px] text-gray-400">最新净值</p>
            <p className="text-[10px] font-mono text-gray-600">{item.current_nav > 0 ? item.current_nav.toFixed(4) : '-'}</p>
          </div>
          <div>
            <p className="text-[9px] text-gray-400">持有份额</p>
            <p className="text-[10px] font-mono text-gray-600">{item.holding_shares > 0 ? item.holding_shares.toLocaleString('zh-CN', { maximumFractionDigits: 2 }) : '-'}</p>
          </div>
          <div>
            <p className="text-[9px] text-gray-400">持仓天数</p>
            <p className="text-[10px] font-mono text-gray-600">{
              (() => {
                if (!item.buy_date) return '-';
                const days = Math.floor((Date.now() - new Date(item.buy_date).getTime()) / 86400000);
                return days > 0 ? `${days}天` : '今天';
              })()
            }</p>
          </div>
        </div>

        {/* 第四行：3 列收益数据 */}
        <div className="grid grid-cols-3 gap-1 md:gap-2 px-3 md:px-4 mt-1 pb-2">
          <div>
            <p className="text-[9px] text-gray-400">最新盈亏</p>
            <p className={clsx('text-xs font-bold font-mono', daily.cls)}>{daily.text}</p>
          </div>
          <div>
            <p className="text-[9px] text-gray-400">持有盈亏</p>
            <p className={clsx('text-xs font-bold font-mono', holding.cls)}>{holding.text}</p>
          </div>
          <div>
            <p className="text-[9px] text-gray-400">收益率</p>
            <p className={clsx('text-xs font-bold font-mono', holdingRate.cls)}>{holdingRate.text}</p>
          </div>
        </div>

        {/* 第五行：仓位进度条 */}
        {targetPct != null && currentPct != null && (() => {
          const t = Math.min(targetPct, 1);
          const c = Math.min(currentPct, 1);
          const isOver = currentPct > targetPct;
          return (
            <div className="px-4 pb-3">
              <div className="flex items-center justify-between mb-0.5">
                <span className="text-[9px] text-gray-400">
                  仓位 {(currentPct * 100).toFixed(1)}%
                  {isOver && <span className="text-red-400 ml-1">超配</span>}
                </span>
                <span className="text-[9px] text-gray-300">目标 {(targetPct * 100).toFixed(0)}%</span>
              </div>
              <div className="relative h-1.5 w-full bg-gray-100 rounded-full">
                <div
                  className={clsx('absolute h-full rounded-full transition-all', isOver ? 'bg-red-300' : 'bg-teal-400')}
                  style={{ width: `${Math.max(t, 0.02) * 100}%` }}
                />
                <div
                  className="absolute h-2 w-[2px] bg-gray-700 -top-[1px] rounded"
                  style={{ left: `${c * 100}%` }}
                />
              </div>
            </div>
          );
        })()}
      </div>
    </div>
  );
}

/* ============================================================
   主页面组件
   ============================================================ */
export default function PortfolioV5() {
  const [expandedId, setExpandedId] = useState<number | null>(null);

  // API 数据状态
  const [summary, setSummary] = useState<PortfolioSummary | null>(null);
  const [items, setItems] = useState<PortfolioItem[]>([]);
  const [signals, setSignals] = useState<Record<string, { signalLevel: SignalLevel; confidenceStars: number; factorDetails?: any[] }>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // 行内编辑状态
  const [editingCode, setEditingCode] = useState<string | null>(null);
  const [editValue, setEditValue] = useState('');
  const [saving, setSaving] = useState(false);

  // 增强数据
  const [navHistories, setNavHistories] = useState<Record<string, { date: string; nav: number; daily_return?: number }[]>>({});
  const [positionAdviceMap, setPositionAdviceMap] = useState<Record<string, { trendText?: string; marketStatus?: string; trendGuard?: any; action?: string; reason?: string; target_position_pct?: number; trend_guard_text?: string }>>({});
  const [positionAdviceFromDetailMap, setPositionAdviceFromDetailMap] = useState<Record<string, any>>({});
  const [trendGuardFromDetailMap, setTrendGuardFromDetailMap] = useState<Record<string, any>>({});
  const [marketStatusFromDetailMap, setMarketStatusFromDetailMap] = useState<Record<string, string>>({});
  const [topStocksMap, setTopStocksMap] = useState<Record<string, { name: string; pct: number; change: number }[]>>({});
  const [evaluationsMap, setEvaluationsMap] = useState<Record<string, any>>({});
  const [sentimentDetailsMap, setSentimentDetailsMap] = useState<Record<string, any>>({});

  // 信号切换检测
  const [signalSwitchedMap, setSignalSwitchedMap] = useState<Record<string, boolean>>({});

  // 整体仓位目标（从V5引擎获取）
  const [overallTargetPct, setOverallTargetPct] = useState<number | null>(null);

  // 建议记录 + 交易记录
  const [adviceMap, setAdviceMap] = useState<Record<string, { items: any[]; stats: any }>>({});
  const [tradeMap, setTradeMap] = useState<Record<string, any[]>>({});

  // 现金管理
  const [cashAmount, setCashAmount] = useState(0);
  const [savingCash, setSavingCash] = useState(false);

  // TODO: 接入真实API (T4/T6完成后) — 建仓推荐基金
  const [recommendedFunds, setRecommendedFunds] = useState<SectorFund[]>([]);
  const [showRecommendations, setShowRecommendations] = useState(false);

  /* ---- Gate 总览统计 + 风险排序 ---- */
  const gateStats = useMemo(() => {
    let stopLossCount = 0, warningCount = 0, normalCount = 0;
    items.forEach(item => {
      const gates = trendGuardFromDetailMap[item.fund_code]?.gates;
      const status = gates?.overall_status
        || (gates?.gate_1?.triggered || gates?.gate_2?.triggered ? 'stop_loss'
          : gates?.gate_e?.triggered ? 'warning' : 'normal');
      if (status === 'stop_loss') stopLossCount++;
      else if (status === 'warning') warningCount++;
      else normalCount++;
    });
    return { stopLossCount, warningCount, normalCount };
  }, [items, trendGuardFromDetailMap]);

  const sortedItems = useMemo(() => {
    const statusPriority: Record<string, number> = { 'stop_loss': 0, 'warning': 1, 'normal': 2 };
    const signalPriority: Record<string, number> = { 'E': 3, 'D': 4, 'C': 5, 'B': 6, 'A': 7, 'S': 8, 'S+': 9 };
    const getOverallStatus = (code: string) => {
      const gates = trendGuardFromDetailMap[code]?.gates;
      return gates?.overall_status
        || (gates?.gate_1?.triggered || gates?.gate_2?.triggered ? 'stop_loss'
          : gates?.gate_e?.triggered ? 'warning' : 'normal');
    };
    return [...items].sort((a, b) => {
      const pa = statusPriority[getOverallStatus(a.fund_code)] ?? 99;
      const pb = statusPriority[getOverallStatus(b.fund_code)] ?? 99;
      if (pa !== pb) return pa - pb;
      const sa = signals[a.fund_code]?.signalLevel ?? 'B';
      const sb = signals[b.fund_code]?.signalLevel ?? 'B';
      return (signalPriority[sa] ?? 6) - (signalPriority[sb] ?? 6);
    });
  }, [items, trendGuardFromDetailMap, signals]);

  const toggleExpand = useCallback((id: number) => {
    setExpandedId(prev => prev === id ? null : id);
  }, []);

  /** 开始编辑市值 */
  const handleStartEdit = useCallback((fundCode: string) => {
    const item = items.find(i => i.fund_code === fundCode);
    if (item) {
      setEditingCode(fundCode);
      setEditValue(String(Math.round(item.market_value)));
    }
  }, [items]);

  /** 取消编辑 */
  const handleCancelEdit = useCallback(() => {
    setEditingCode(null);
    setEditValue('');
  }, []);

  /** 保存市值编辑 */
  const handleSaveEdit = useCallback(async (fundCode: string) => {
    if (saving) return;
    const numVal = parseFloat(editValue);
    if (isNaN(numVal) || numVal <= 0) {
      toast.error('请输入有效的金额');
      return;
    }

    const item = items.find(i => i.fund_code === fundCode);
    if (!item) return;

    setSaving(true);
    try {
      const result = await updatePortfolioMarketValue(item.id, numVal);
      // 更新本地数据（同时重算 summary 联动）
      setItems(prev => {
        const updated = prev.map(i =>
          i.fund_code === fundCode
            ? {
                ...i,
                market_value: result.market_value ?? numVal,
                current_nav: result.current_nav ?? i.current_nav,
                total_return: result.total_return ?? i.total_return,
                return_rate: result.return_rate ?? i.return_rate,
              }
            : i
        );
        // 重算 summary（持仓市值/持仓盈亏/持有收益率/最新盈亏）
        const totalValue = updated.reduce((s, i) => s + (i.market_value || 0), 0);
        const totalReturn = updated.reduce((s, i) => s + (i.total_return || 0), 0);
        const totalCost = updated.reduce((s, i) => s + (i.cost_nav || 0) * (i.holding_shares || 0), 0);
        const totalReturnRate = totalCost > 0 ? round2((totalValue / totalCost - 1) * 100) : 0;
        const dailyReturn = updated.reduce((s, i) => s + (i.daily_return || 0), 0);
        setSummary(prev => prev ? {
          ...prev,
          total_value: round2(totalValue),
          total_return: round2(totalReturn),
          total_return_rate: totalReturnRate,
          daily_return: round2(dailyReturn),
          total_assets: round2(totalValue + (prev.cash_amount || 0)),
        } : prev);
        return updated;
      });
      setEditingCode(null);
      setEditValue('');
      toast.success('持仓市值已更新');
    } catch (err: any) {
      toast.error(err?.response?.data?.message || '更新失败');
    } finally {
      setSaving(false);
    }
  }, [editValue, items, saving]);

  /** 保存现金 */
  const handleSaveCash = useCallback(async (amount: number) => {
    setSavingCash(true);
    try {
      const result = await updateCashV5(amount);
      setCashAmount(result.cash_amount);
      // 更新本地 summary
      setSummary(prev => prev ? {
        ...prev,
        cash_amount: result.cash_amount,
        total_assets: (prev.total_value || 0) + result.cash_amount,
      } : prev);
      toast.success('现金已更新');
    } catch (err: any) {
      toast.error(err?.response?.data?.message || '更新失败');
      throw err;
    } finally {
      setSavingCash(false);
    }
  }, []);

  /** 删除持仓 */
  const handleDelete = useCallback(async (itemId: number) => {
    try {
      await deletePortfolioV5(itemId);
      // 从本地列表中移除
      setItems(prev => prev.filter(i => i.id !== itemId));
      setExpandedId(null);
      toast.success('持仓已删除，市值已退还到现金');
      // 重新加载持仓数据以更新 summary
      try {
        const portfolioData = await fetchPortfolioV5();
        setSummary(portfolioData.summary);
        setItems(portfolioData.items);
        const cashData = await fetchCashV5();
        setCashAmount(cashData.cash_amount);
      } catch {
        // 静默降级
      }
    } catch (err: any) {
      toast.error(err?.response?.data?.message || '删除失败');
      throw err;
    }
  }, []);

  /** 手动加仓 */
  const handleIncrease = useCallback(async (item: PortfolioItem, amount: number, date: string) => {
    try {
      await increasePosition(item.id, amount, date);
      toast.success(`加仓成功：¥${amount.toLocaleString()}`);
      // 重新加载持仓列表和现金
      try {
        const portfolioData = await fetchPortfolioV5();
        setSummary(portfolioData.summary);
        setItems(portfolioData.items);
        const cashData = await fetchCashV5();
        setCashAmount(cashData.cash_amount);
      } catch {
        // 静默降级
      }
    } catch (err: any) {
      toast.error(err?.response?.data?.message || '加仓失败');
      throw err;
    }
  }, []);

  /** 手动减仓 */
  const handleDecrease = useCallback(async (item: PortfolioItem, amount: number, date: string) => {
    try {
      await decreasePosition(item.id, amount, date);
      toast.success(`减仓成功：¥${amount.toLocaleString()}`);
      // 重新加载持仓列表和现金
      try {
        const portfolioData = await fetchPortfolioV5();
        setSummary(portfolioData.summary);
        setItems(portfolioData.items);
        const cashData = await fetchCashV5();
        setCashAmount(cashData.cash_amount);
      } catch {
        // 静默降级
      }
    } catch (err: any) {
      toast.error(err?.response?.data?.message || '减仓失败');
      throw err;
    }
  }, []);

  /** 加载持仓数据 */
  useEffect(() => {
    let cancelled = false;
    const loadData = async () => {
      setLoading(true);
      setError(null);
      try {
        const [portfolioData, cashData] = await Promise.all([
          fetchPortfolioV5().catch(() => null),
          fetchCashV5().catch(() => null as any),
        ]);

        if (cancelled) return;

        const safePortfolioData = portfolioData || { items: [], summary: null };
        const safeItems = Array.isArray(safePortfolioData.items) ? safePortfolioData.items : [];
        const safeSummary = safePortfolioData.summary || null;

        setSummary(safeSummary);
        setItems(safeItems);

        if (cashData && !cancelled) setCashAmount(cashData.cash_amount);

        if (safeItems.length === 0) {
          if (!cancelled) setLoading(false);
          return;
        }

        // 并行获取：V5信号 + 详情数据 + 市场快照（减少串行批次）
        const [signalEntries, detailEntries, snapRes] = await Promise.all([
          Promise.all(
            safeItems.map(async (item) => {
              try {
                const sentiment = await fetchV5Sentiment(item.fund_code);
                return [item.fund_code, {
                  signalLevel: sentiment.signal_level as SignalLevel,
                  confidenceStars: sentiment.confidence_stars,
                  factorDetails: sentiment.factor_details || [],
                }] as [string, { signalLevel: SignalLevel; confidenceStars: number; factorDetails?: any[] }];
              } catch {
                return null;
              }
            }),
          ),
          Promise.all(
            safeItems.map(async (item) => {
              try {
                const resp = await client.get(`/api/v5/portfolio/fund-detail?fund_code=${item.fund_code}`);
                const data = resp.data?.data;
                if (!data) return null;
                return [item.fund_code, data] as [string, any];
              } catch {
                return null;
              }
            }),
          ),
          client.get('/api/v5/market/snapshot').catch(() => null),
        ]);

        if (cancelled) return;

        const signalMap: Record<string, { signalLevel: SignalLevel; confidenceStars: number; factorDetails?: any[] }> = {};
        signalEntries.forEach((entry) => {
          if (entry) signalMap[entry[0]] = entry[1];
        });
        // Fallback: 基金代码调 sentiment API 会 404，从 fund-detail 的 positionAdvice 补全置信度
        detailEntries.forEach((entry) => {
          if (!entry) return;
          const [fc, data] = entry;
          if (signalMap[fc]) return; // 已有直接情绪数据则跳过
          const pa = data?.positionAdvice;
          if (pa?.confidence_stars != null || pa?.signal_level) {
            signalMap[fc] = {
              signalLevel: (pa.signal_level || "B") as SignalLevel,
              confidenceStars: pa.confidence_stars ?? 0,
              factorDetails: [],
            };
          }
        });
        setSignals(signalMap);

        // snapData 已在上面与 sentiment+fund-detail 并行获取
        try {
          const snapData = snapRes?.data?.data;
          if (snapData?.composite_score !== undefined && snapData?.signal_level) {
            // 根据信号等级和当前仓位估算目标仓位（简化版，复用V5仓位矩阵逻辑）
            const currentPosPct = safeSummary?.core_ratio ?? 0.5;
            const signalLevel = snapData.signal_level as string;
            const posMatrix: Record<string, number> = {
              'S+': 0.80, 'S': 0.70, 'A': 0.60, 'B': 0.50,
              'C': 0.40, 'D': 0.30, 'E': 0.20,
            };
            const target = posMatrix[signalLevel] ?? 0.50;
            setOverallTargetPct(target);
          }
        } catch {
          // 静默降级
        }

        // 从详情API提取增强数据
        const realNavHistories: Record<string, number[]> = {};
        const realTopStocks: Record<string, { name: string; pct: number; change: number }[]> = {};
        const realEvaluations: Record<string, any> = {};
        const realSentimentDetails: Record<string, any> = {};
        const realTrendGuardFromDetail: Record<string, any> = {};
        const realMarketStatusFromDetail: Record<string, string> = {};
        const realPositionAdviceFromDetail: Record<string, any> = {};

        detailEntries.forEach((entry) => {
          if (!entry) return;
          const [code, detail] = entry;

          const navH = detail.nav_history || [];
          if (navH.length > 1) {
            realNavHistories[code] = navH.map((p: any) => ({
              date: p.date || '',
              nav: p.nav || p.adj_nav || 0,
              daily_return: p.daily_return,
            })).filter((p: any) => p.nav > 0);
          }

          const holdings = detail.top_holdings || [];
          if (holdings.length > 0) {
            realTopStocks[code] = holdings.map((h: any) => ({
              name: h.stock_name || `${h.exchange}${h.stock_code}`,
              pct: (h.weight_pct || 0) / 100,
              change: h.daily_change || 0,
            }));
          }

          const eval_ = detail.evaluation;
          if (eval_) {
            realEvaluations[code] = {
              short_term: {
                label: eval_.short_term?.judgment || '中性',
                score: Math.round((eval_.short_term?.return_pct || 0) * 10 + 50),
                reason: `${eval_.short_term?.period || '短期'}: ${eval_.short_term?.return_pct?.toFixed(2) || 0}%`,
              },
              mid_term: {
                label: eval_.mid_term?.judgment || '中性',
                score: Math.round((eval_.mid_term?.return_pct || 0) * 5 + 50),
                reason: `${eval_.mid_term?.period || '中期'}: ${eval_.mid_term?.return_pct?.toFixed(2) || 0}%`,
              },
              long_term: {
                label: eval_.long_term?.judgment || '长期配置',
                score: 55,
                reason: eval_.long_term?.judgment || '建议长期持有',
              },
            };
          }

          // 提取情绪因子详情
          if (detail.sentiment_detail || detail.factors) {
            realSentimentDetails[code] = detail.sentiment_detail || { factors: detail.factors };
          }

          // 提取趋势卫士数据（来自 /fund-detail 接口）
          if (detail.trend_guard) {
            realTrendGuardFromDetail[code] = detail.trend_guard;
          }

          // 提取市场现状（来自 /fund-detail 接口）
          if (detail.market_status) {
            realMarketStatusFromDetail[code] = detail.market_status;
          }

          // 提取仓位建议（来自 /fund-detail 接口的 positionAdvice）
          if (detail.positionAdvice) {
            const pa = detail.positionAdvice;
            realPositionAdviceFromDetail[code] = {
              action: pa.action,
              reason: pa.reason,
              target_position_pct: pa.target_position_pct,
              trend_guard_text: pa.trend_guard_text,
              trendText: pa.trend_text,
              marketStatus: detail.market_status,
              trendGuard: detail.trend_guard,
            };
          }
        });

        setNavHistories(realNavHistories);
        setTopStocksMap(realTopStocks);
        setEvaluationsMap(realEvaluations);
        setSentimentDetailsMap(realSentimentDetails);
        setTrendGuardFromDetailMap(realTrendGuardFromDetail);
        setMarketStatusFromDetailMap(realMarketStatusFromDetail);
        setPositionAdviceFromDetailMap(realPositionAdviceFromDetail);

        // 信号切换检测 — 从 fund-detail 响应的 signal_switched_today 字段提取
        // （替代独立的 /signal-switched 批量API调用，Phase 2 优化）
        const newSwitchMap: Record<string, boolean> = {};
        detailEntries.forEach((entry) => {
          if (!entry) return;
          const [code, detail] = entry;
          if (detail?.signal_switched_today) {
            newSwitchMap[code] = true;
          }
        });
        if (!cancelled) setSignalSwitchedMap(newSwitchMap);

        // 并行获取建议历史 + 交易记录
        try {
          const [adviceEntries, tradeEntries, posAdviceEntries] = await Promise.all([
            Promise.all(
              safeItems.map(async (item) => {
                try {
                  const adviceData = await fetchAdviceHistoryV5(item.fund_code);
                  return [item.fund_code, adviceData] as [string, any];
                } catch {
                  return null;
                }
              }),
            ),
            Promise.all(
              safeItems.map(async (item) => {
                try {
                  const tradeData = await fetchTradeRecordsV5(item.fund_code);
                  return [item.fund_code, tradeData.items || []] as [string, any[]];
                } catch {
                  return null;
                }
              }),
            ),
            Promise.all(
              safeItems.map(async (item) => {
                try {
                  const posAdvice: any = await fetchPositionAdviceV5(item.fund_code, item.weight_pct);
                  return [item.fund_code, {
                    trendText: posAdvice?.trend_text,
                    marketStatus: posAdvice?.market_status,
                    trendGuard: posAdvice?.trend_guard,
                  }] as [string, any];
                } catch {
                  return null;
                }
              }),
            ),
          ]);

          if (cancelled) return;

          const realAdviceMap: Record<string, { items: any[]; stats: any }> = {};
          adviceEntries.forEach((entry) => {
            if (entry) realAdviceMap[entry[0]] = entry[1];
          });
          setAdviceMap(realAdviceMap);

          const realTradeMap: Record<string, any[]> = {};
          tradeEntries.forEach((entry) => {
            if (entry) realTradeMap[entry[0]] = entry[1];
          });
          setTradeMap(realTradeMap);

          const realPosAdviceMap: Record<string, { trendText?: string; marketStatus?: string; trendGuard?: any }> = {};
          posAdviceEntries.forEach((entry) => {
            if (entry) realPosAdviceMap[entry[0]] = entry[1];
          });
          setPositionAdviceMap(realPosAdviceMap);
        } catch {
          // 非关键数据，静默失败
        }
      } catch (err: any) {
        if (!cancelled) {
          setError(err?.message || '加载持仓数据失败');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    loadData();
    return () => { cancelled = true; };
  }, []);

  // TODO: 接入真实API (T4/T6完成后) — 加载建仓推荐基金
  useEffect(() => {
    // 阶段1: 使用 Mock 数据（加载医药生物板块的强烈建仓基金作为推荐）
    fetchSectorFunds('801150').then((funds) => {
      setRecommendedFunds(funds);
    }).catch(() => { /* silent */ });
  }, []);

  /** 执行仓位调整（V5引擎精确目标仓位） */
  const handleExecute = useCallback(async (item: PortfolioItem) => {
    const signal = signals[item.fund_code];
    // 调用V5引擎获取精确目标仓位，而非写死+10%
    try {
      const advice = await fetchPositionAdviceV5(item.fund_code, item.weight_pct);
      await executePositionV5({
        fund_code: item.fund_code,
        target_position_pct: advice.target_pct ?? Math.min(0.95, item.weight_pct + 0.10),
        signal_level: signal?.signalLevel ?? 'B',
        confidence_stars: signal?.confidenceStars ?? 3,
      });
    } catch {
      // 降级到信号级判断
      await executePositionV5({
        fund_code: item.fund_code,
        target_position_pct: Math.min(0.95, item.weight_pct + 0.10),
        signal_level: signal?.signalLevel ?? 'B',
        confidence_stars: signal?.confidenceStars ?? 3,
      });
    }
  }, [signals]);

  // =============== 渲染 ===============

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto space-y-4">
        <PortfolioHeader summary={null} cashAmount={cashAmount} onCashSave={handleSaveCash} />
        <div className="card p-8 text-center">
          <div className="inline-block w-6 h-6 border-2 border-[var(--brand-cyan)] border-t-transparent rounded-full animate-spin" />
          <p className="text-gray-400 text-sm mt-2">加载持仓数据...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-4xl mx-auto space-y-4">
        <PortfolioHeader summary={null} cashAmount={cashAmount} onCashSave={handleSaveCash} />
        <div className="card p-8 text-center">
          <p className="text-red-500 text-sm">{error}</p>
          <button
            onClick={() => window.location.reload()}
            className="mt-3 px-4 py-1.5 text-xs bg-[var(--brand-cyan)] text-white rounded-lg hover:bg-[var(--brand-cyan-dark)] transition-colors"
          >
            重试
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto">
      {/* 总览头部 */}
      <PortfolioHeader summary={summary} cashAmount={cashAmount} onCashSave={handleSaveCash} />

      {/* Gate 风控总览行 — 基于 overall_status 三档统计 */}
      {items.length > 0 && (() => {
        const sl = gateStats.stopLossCount;
        const wn = gateStats.warningCount;
        const hasAlert = sl > 0 || wn > 0;
        return (
          <div className="flex items-center gap-3 mt-2 mb-1 px-1">
            {hasAlert ? (
              <>
                {sl > 0 && <span className="text-xs font-semibold text-red-600">&#9888; {sl}只待止损</span>}
                {wn > 0 && <span className="text-xs font-semibold text-amber-600">&#9889; {wn}只预警</span>}
              </>
            ) : (
              <span className="text-xs font-semibold text-green-600">&#10003; 所有持仓风控正常</span>
            )}
          </div>
        );
      })()}

      {/* 持仓卡片网格 */}
      {items.length === 0 ? (
        <div className="card p-8 text-center mt-4">
          <Briefcase className="w-8 h-8 text-gray-300 mx-auto mb-2" />
          <p className="text-gray-500 text-sm font-medium">暂无持仓数据</p>
          <p className="text-xs text-gray-300 mt-1">添加持仓基金后，即可查看仓位建议和交易操作</p>
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2 md:gap-3 mt-4">
          {sortedItems.map(item => {
            const isExpanded = expandedId === item.id;
            const detailData = buildRealDetailData(
              item,
              signals[item.fund_code],
              navHistories[item.fund_code],
              topStocksMap[item.fund_code],
              evaluationsMap[item.fund_code],
              { factors: signals[item.fund_code]?.factorDetails },
              adviceMap[item.fund_code],
              tradeMap[item.fund_code],
              overallTargetPct,
              positionAdviceFromDetailMap[item.fund_code]
                ? {
                    ...positionAdviceFromDetailMap[item.fund_code],
                    marketStatus: positionAdviceFromDetailMap[item.fund_code].marketStatus || marketStatusFromDetailMap[item.fund_code],
                    trendGuard: positionAdviceFromDetailMap[item.fund_code].trendGuard || trendGuardFromDetailMap[item.fund_code],
                  }
                : positionAdviceMap[item.fund_code]
                  ? {
                      ...positionAdviceMap[item.fund_code],
                      marketStatus: positionAdviceMap[item.fund_code].marketStatus || marketStatusFromDetailMap[item.fund_code],
                      trendGuard: positionAdviceMap[item.fund_code].trendGuard || trendGuardFromDetailMap[item.fund_code],
                    }
                  : {
                      marketStatus: marketStatusFromDetailMap[item.fund_code],
                      trendText: trendGuardFromDetailMap[item.fund_code]?.trend_narrative,
                      trendGuard: trendGuardFromDetailMap[item.fund_code],
                    },
              summary?.total_assets ?? summary?.total_value,
              summary?.cash_amount ?? 0,
              summary?.total_assets ?? summary?.total_value,
            );

            return (
              <div key={item.id} className={clsx(isExpanded && 'md:col-span-2')}>
                <PositionCard
                  item={item}
                  expanded={isExpanded}
                  onToggle={() => toggleExpand(item.id)}
                  signal={signals[item.fund_code]}
                  gates={trendGuardFromDetailMap[item.fund_code]?.gates}
                  targetPct={positionAdviceFromDetailMap[item.fund_code]?.target_position_pct != null ? positionAdviceFromDetailMap[item.fund_code].target_position_pct / 100 : undefined}
                  currentPct={item.weight_pct}
                  trackType={positionAdviceFromDetailMap[item.fund_code]?.track_type || trendGuardFromDetailMap[item.fund_code]?.sector_track}
                  regime={positionAdviceFromDetailMap[item.fund_code]?.regime || positionAdviceFromDetailMap[item.fund_code]?.marketStatus?.regime}
                  signalSwitched={signalSwitchedMap[item.fund_code]}
                  action={positionAdviceFromDetailMap[item.fund_code]?.action}
                  editingCode={editingCode}
                  editValue={editValue}
                  onStartEdit={handleStartEdit}
                  onCancelEdit={handleCancelEdit}
                  onSaveEdit={handleSaveEdit}
                  onEditValueChange={setEditValue}
                />

                {/* 展开详情面板 — 在卡片下方全宽显示 */}
                {isExpanded && (
                  <div className="rounded-xl border border-gray-200 bg-white shadow-sm mt-1 p-4">
                    <PositionDetailPanel
                      data={detailData}
                      signalSwitched={signalSwitchedMap[item.fund_code]}
                      trackType={positionAdviceFromDetailMap[item.fund_code]?.track_type || trendGuardFromDetailMap[item.fund_code]?.sector_track}
                      onCollapse={() => setExpandedId(null)}
                      onDelete={() => handleDelete(item.id)}
                      onIncrease={async (amount, date) => {
                        try {
                          await handleIncrease(item, amount, date);
                        } catch {
                          // 错误已在 handleIncrease 中处理
                        }
                      }}
                      onDecrease={async (amount, date) => {
                        try {
                          await handleDecrease(item, amount, date);
                        } catch {
                          // 错误已在 handleDecrease 中处理
                        }
                      }}
                      onExecute={async () => {
                        try {
                          await handleExecute(item);
                          toast.success('仓位调整已执行');
                        } catch (err: any) {
                          toast.error(err?.response?.data?.message || '执行失败');
                        }
                      }}
                    />
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* 建仓推荐区 — 复用 SectorFundCard 组件 */}
      {recommendedFunds.length > 0 && (
        <div className="mt-4">
          <button
            onClick={() => setShowRecommendations((prev) => !prev)}
            className="flex items-center gap-2 mb-2 text-gray-600 hover:text-gray-800"
          >
            {showRecommendations ? <ChevronDown className="w-4 h-4" /> : <ChevronUp className="w-4 h-4" />}
            <Lightbulb className="w-4 h-4 text-yellow-500" />
            <h3 className="text-sm font-bold">建仓推荐</h3>
            <span className="text-[10px] text-gray-400">基于板块情绪评级</span>
          </button>
          {showRecommendations && (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {recommendedFunds.map((fund) => (
                <SectorFundCard key={fund.fund_code} fund={fund} compact />
              ))}
            </div>
          )}
        </div>
      )}
    </div>
  );
}
