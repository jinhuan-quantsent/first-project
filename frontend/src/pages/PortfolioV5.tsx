/**
 * PortfolioV5 - 持仓页重设计 V5
 * 总览头部 + 列表行 + 详情展开面板
 * 对齐设计稿 Image4 + Image5
 */
import { useState, useCallback, useEffect, useRef } from 'react';
import type { PortfolioItem, PortfolioSummary, SignalLevel } from '../types';
import { SIGNAL_LABELS } from '../types';
import PositionDetailPanel, { type PositionDetailData } from '../components/portfolio/PositionDetailPanel';
import { Briefcase, Pencil, Check, X, ChevronDown, ChevronUp } from 'lucide-react';
import { clsx } from 'clsx';
import {
  fetchPortfolioV5,
  executePositionV5,
  updatePortfolioMarketValue,
  fetchAdviceHistoryV5,
  fetchTradeRecordsV5,
} from '../api/portfolioV5';
import { fetchV5Sentiment } from '../api/marketV5';
import { toast } from '../components/common/Toast';
import client from '../api/client';

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
  positionAdvice?: { trendText?: string; marketStatus?: string; trendGuard?: any } | undefined,
): PositionDetailData {
  const signalLevel = signal?.signalLevel ?? 'B';
  const signalLabel = SIGNAL_LABELS[signalLevel] ?? '中性';

  // 双层建议体系：信号+整体仓位交叉判断
  const getOperationTag = (
    sigLevel: string,
    currentWeightPct: number,
    overallTargetPct?: number,
  ): { tag: PositionDetailData['operationTag']; reason: string } => {
    // 纯信号判断
    const signalTag =
      sigLevel === 'S+' || sigLevel === 'S' ? '加仓' :
      sigLevel === 'D' || sigLevel === 'E' ? '减仓' :
      sigLevel === 'A' ? '买入' : '持有';

    // 无整体目标时直接返回信号级判断
    if (overallTargetPct === undefined || overallTargetPct === null) {
      return { tag: signalTag, reason: `基于${SIGNAL_LABELS[sigLevel]}信号` };
    }

    // 有整体目标 → 交叉判断
    const needReduce = currentWeightPct > overallTargetPct * 1.1;  // 当前权重超目标10%+
    const needAdd = currentWeightPct < overallTargetPct * 0.9;      // 当前权重低目标10%-

    if (signalTag === '减仓' && needReduce) {
      return { tag: '减仓', reason: `${SIGNAL_LABELS[sigLevel]}信号+整体仓位需降，优先减持` };
    }
    if (signalTag === '加仓' && needAdd) {
      return { tag: '加仓', reason: `${SIGNAL_LABELS[sigLevel]}信号+整体仓位偏低，优先增持` };
    }
    if (signalTag === '减仓' && !needReduce) {
      return { tag: '持有', reason: `虽${SIGNAL_LABELS[sigLevel]}信号，但整体仓位已偏低，暂不减持` };
    }
    if (signalTag === '加仓' && !needAdd) {
      return { tag: '持有', reason: `虽${SIGNAL_LABELS[sigLevel]}信号，但整体仓位已偏高，暂不加仓` };
    }
    return { tag: signalTag, reason: `基于${SIGNAL_LABELS[sigLevel]}信号，与整体仓位一致` };
  };

  const { tag: operationTag, reason: opReason } = getOperationTag(
    signalLevel,
    item.weight_pct,
    overallTargetPct ?? undefined,
  );

  // 从 V5 因子详情构建推荐理由
  const factorNames: Record<string, string> = {
    VOL: '波动率', TURN: '换手率', RATIO: '涨跌比', NEWF: '新高占比',
    MARGIN: '融资融券', ERP: '股债利差', RSI: 'RSI指标',
    FLOW: '北向资金', ETF: 'ETF流入', POS: '基金仓位', NBF: '非银融资',
    PCR: '看跌看涨比', NHNL: '新高新低', ADR: '涨跌比',
    INDUSTRY_DIVERGENCE: '行业分歧度',
  };

  let recommendationReason = '';
  if (sentimentDetail?.factors && Array.isArray(sentimentDetail.factors)) {
    const topFactors = [...sentimentDetail.factors]
      .sort((a: any, b: any) => (b.sigmoid_score || b.raw_score || 0) - (a.sigmoid_score || a.raw_score || 0))
      .slice(0, 3);
    const factorTexts = topFactors.map((f: any) =>
      `${factorNames[f.name] || f.name}${Math.round((f.sigmoid_score || f.raw_score || 0) * 100)}分`
    );
    recommendationReason = `基于${signalLabel}信号分析，当前市场情绪处于${signalLabel}区间(${signal?.confidenceStars ?? 3}星置信)。${factorTexts.join('+')}触发${signalLabel}信号，建议${operationTag}。该基金近期表现${item.return_rate >= 0 ? '优于' : '弱于'}基准${Math.abs(item.return_rate).toFixed(1)}%，${operationTag === '加仓' ? '逆向操作逢低布局' : operationTag === '减仓' ? '止盈减仓控制风险' : '维持当前仓位观察'}。`;
  } else {
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
  const todayEvaluation = `净值估${item.daily_return >= 0 ? '增' : '减'}${Math.abs(item.daily_return).toFixed(2)}%，${signalLabel}信号${signal?.confidenceStars ?? 3}星置信度`;

  // complianceStars 从 confidence_stars 推算（5星→4.8, 4星→4.5, 3星→4.0）
  const complianceStars = Math.max(1, Math.min(5, (signal?.confidenceStars ?? 3) * 0.95 + 1));

  return {
    fundCode: item.fund_code,
    fundName: (item as any).fund_short_name || item.fund_name,
    marketValue: item.market_value,
    dailyReturn: item.daily_return,
    holdingReturn: item.total_return,
    holdingReturnRate: item.return_rate,
    signalLevel,
    confidenceStars: signal?.confidenceStars ?? 3,
    signalReason: `${signalLevel}·${signalLabel}，${operationTag === '加仓' ? '逆向加仓机会' : operationTag === '减仓' ? '止盈减仓信号' : '维持持有'}`,

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
  };
}

/* ============================================================
   总览头部组件
   ============================================================ */
function PortfolioHeader({ summary }: { summary: PortfolioSummary | null }) {
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

  return (
    <div className="mb-4">
      {/* 标题行 */}
      <h1 className="text-xl font-bold text-gray-800 mb-3">我的持仓</h1>

      {/* 分隔线 */}
      <div className="border-t border-gray-200 mb-4" />

      {/* 总览区 */}
      <div className="flex items-start justify-between flex-wrap gap-4">
        {/* 左：持仓总金额 */}
        <div>
          <p className="text-xs text-gray-400 mb-1">持仓总金额（元）</p>
          <p className="text-3xl font-bold text-gray-900 font-mono">
            {formatMoneyFull(summary.total_value)}
          </p>
        </div>

        {/* 右：4个统计指标 */}
        <div className="flex items-center gap-6 flex-wrap">
          <div className="text-right">
            <p className="text-[10px] text-gray-400 mb-0.5">昨日盈亏</p>
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
    </div>
  );
}

/* ============================================================
   持仓列表行组件（支持行内编辑市值）
   ============================================================ */
function PositionRow({
  item,
  expanded,
  onToggle,
  signal,
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

  // 自动聚焦输入框
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
    <div className={clsx(
      'border-b border-gray-100 last:border-b-0',
      expanded && 'bg-gray-50/50',
    )}>
      {/* 主行：可点击展开 */}
      <div
        onClick={onToggle}
        className="flex items-center gap-2 px-4 py-3 cursor-pointer hover:bg-gray-50 transition-colors"
      >
        {/* 左侧：基金名+代码 (~30%) */}
        <div className="flex-1 min-w-0">
          <p className="text-sm font-medium text-gray-800 truncate">{fundShortName}</p>
          <p className="text-[11px] text-gray-400 font-mono">{item.fund_code}</p>
        </div>

        {/* 中间偏左：持仓市值+编辑 (~20%) */}
        <div className="shrink-0 flex items-center gap-1 min-w-[100px]" onClick={(e) => e.stopPropagation()}>
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
                className="w-20 text-sm font-bold text-gray-800 font-mono border border-[var(--brand-cyan)] rounded px-1 py-0.5 focus:outline-none focus:ring-1 focus:ring-[var(--brand-cyan)]"
              />
              <button
                onClick={() => onSaveEdit(item.fund_code)}
                className="text-green-500 hover:text-green-600 transition-colors"
              >
                <Check className="w-3.5 h-3.5" />
              </button>
              <button
                onClick={(e) => { e.stopPropagation(); onCancelEdit(); }}
                className="text-gray-400 hover:text-gray-500 transition-colors"
              >
                <X className="w-3.5 h-3.5" />
              </button>
            </div>
          ) : (
            <>
              <span className="text-sm font-bold text-gray-800 font-mono">{formatMoney(item.market_value)}</span>
              <button
                onClick={(e) => { e.stopPropagation(); onStartEdit(item.fund_code); }}
                className="text-gray-300 hover:text-[var(--brand-cyan)] transition-colors"
                title="编辑持仓"
              >
                <Pencil className="w-3 h-3" />
              </button>
            </>
          )}
        </div>

        {/* 中间：昨收+持有 (~25%) */}
        <div className="shrink-0 text-right space-y-0.5 min-w-[120px]">
          <p className={`text-xs font-mono ${daily.cls}`}>
            昨收 {daily.text}
          </p>
          <p className={`text-xs font-mono ${holding.cls}`}>
            持有 {holding.text}
          </p>
          <p className={`text-[10px] font-mono ${holdingRate.cls}`}>
            ({holdingRate.text})
          </p>
        </div>

        {/* 右侧：信号徽章+原因+展开箭头 (~25%) */}
        <div className="shrink-0 flex items-center gap-2 min-w-[140px] justify-end">
          {signal && (
            <span className={`text-[10px] px-1.5 py-0.5 rounded font-bold whitespace-nowrap ${SIGNAL_BG[signalLevel ?? 'B']}`}>
              {signalLevel}·{signalLabel}
            </span>
          )}
          <span className="text-[10px] text-gray-400 truncate max-w-[80px]">
            {signal ? `${signalLabel}信号` : ''}
          </span>
          {expanded ? (
            <ChevronUp className="w-4 h-4 text-gray-400 shrink-0" />
          ) : (
            <ChevronDown className="w-4 h-4 text-gray-400 shrink-0" />
          )}
        </div>
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
  const [positionAdviceMap, setPositionAdviceMap] = useState<Record<string, { trendText?: string; marketStatus?: string; trendGuard?: any }>>({});
  const [trendGuardFromDetailMap, setTrendGuardFromDetailMap] = useState<Record<string, any>>({});
  const [topStocksMap, setTopStocksMap] = useState<Record<string, { name: string; pct: number; change: number }[]>>({});
  const [evaluationsMap, setEvaluationsMap] = useState<Record<string, any>>({});
  const [sentimentDetailsMap, setSentimentDetailsMap] = useState<Record<string, any>>({});

  // 整体仓位目标（从V5引擎获取）
  const [overallTargetPct, setOverallTargetPct] = useState<number | null>(null);

  // 建议记录 + 交易记录
  const [adviceMap, setAdviceMap] = useState<Record<string, { items: any[]; stats: any }>>({});
  const [tradeMap, setTradeMap] = useState<Record<string, any[]>>({});

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
      // 更新本地数据
      setItems(prev => prev.map(i =>
        i.fund_code === fundCode
          ? {
              ...i,
              market_value: result.market_value ?? numVal,
              current_nav: result.current_nav ?? i.current_nav,
              total_return: result.total_return ?? i.total_return,
              return_rate: result.return_rate ?? i.return_rate,
            }
          : i
      ));
      setEditingCode(null);
      setEditValue('');
      toast.success('持仓市值已更新');
    } catch (err: any) {
      toast.error(err?.response?.data?.message || '更新失败');
    } finally {
      setSaving(false);
    }
  }, [editValue, items, saving]);

  /** 加载持仓数据 */
  useEffect(() => {
    let cancelled = false;
    const loadData = async () => {
      setLoading(true);
      setError(null);
      try {
        const portfolioData = await fetchPortfolioV5();

        if (cancelled) return;

        const safePortfolioData = portfolioData || { items: [], summary: null };
        const safeItems = Array.isArray(safePortfolioData.items) ? safePortfolioData.items : [];
        const safeSummary = safePortfolioData.summary || null;

        setSummary(safeSummary);
        setItems(safeItems);

        if (safeItems.length === 0) {
          if (!cancelled) setLoading(false);
          return;
        }

        // 并行获取每只基金的V5信号 + 详情数据
        const [signalEntries, detailEntries] = await Promise.all([
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
        ]);

        if (cancelled) return;

        const signalMap: Record<string, { signalLevel: SignalLevel; confidenceStars: number; factorDetails?: any[] }> = {};
        signalEntries.forEach((entry) => {
          if (entry) signalMap[entry[0]] = entry[1];
        });
        setSignals(signalMap);

        // 获取整体仓位目标（V5引擎计算）
        try {
          const snapRes = await client.get('/api/v5/market/snapshot');
          const snapData = snapRes.data?.data;
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
        });

        setNavHistories(realNavHistories);
        setTopStocksMap(realTopStocks);
        setEvaluationsMap(realEvaluations);
        setSentimentDetailsMap(realSentimentDetails);
        setTrendGuardFromDetailMap(realTrendGuardFromDetail);

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
        <PortfolioHeader summary={null} />
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
        <PortfolioHeader summary={null} />
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
      <PortfolioHeader summary={summary} />

      {/* 持仓列表 */}
      <div className="card overflow-hidden mt-4">
        {items.length === 0 ? (
          <div className="p-8 text-center">
            <Briefcase className="w-8 h-8 text-gray-300 mx-auto mb-2" />
            <p className="text-gray-500 text-sm font-medium">暂无持仓数据</p>
            <p className="text-xs text-gray-300 mt-1">添加持仓基金后，即可查看仓位建议和交易操作</p>
          </div>
        ) : (
          items.map(item => {
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
              positionAdviceMap[item.fund_code]
                ? { ...positionAdviceMap[item.fund_code], trendGuard: positionAdviceMap[item.fund_code].trendGuard || trendGuardFromDetailMap[item.fund_code] }
                : { trendGuard: trendGuardFromDetailMap[item.fund_code] },
            );

            return (
              <div key={item.id}>
                {/* 列表行 */}
                <PositionRow
                  item={item}
                  expanded={isExpanded}
                  onToggle={() => toggleExpand(item.id)}
                  signal={signals[item.fund_code]}
                  editingCode={editingCode}
                  editValue={editValue}
                  onStartEdit={handleStartEdit}
                  onCancelEdit={handleCancelEdit}
                  onSaveEdit={handleSaveEdit}
                  onEditValueChange={setEditValue}
                />

                {/* 展开详情面板 */}
                {isExpanded && (
                  <PositionDetailPanel
                    data={detailData}
                    onCollapse={() => setExpandedId(null)}
                    onExecute={async () => {
                      try {
                        await handleExecute(item);
                        toast.success('仓位调整已执行');
                      } catch (err: any) {
                        toast.error(err?.response?.data?.message || '执行失败');
                      }
                    }}
                  />
                )}
              </div>
            );
          })
        )}
      </div>
    </div>
  );
}
