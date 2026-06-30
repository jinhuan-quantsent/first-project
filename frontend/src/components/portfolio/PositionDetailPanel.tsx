/**
 * PositionDetailPanel - 持仓详情展开面板
 * 包含：合规星级+推荐理由 / 操作建议 / 趋势解读 / 绩效记录 / 交易记录 / 走势图 / 重仓股 / 基础评级 / 今日评估
 */
import { useMemo, useState } from 'react';
import type { SignalLevel } from '../../types';
import SentimentBadge from '../common/SentimentBadge';
import ExpandableReason, { adaptReason, inferActionAdvice } from '../common/ExpandableReason';
import { Star, TrendingUp, ChevronUp, BarChart3, Activity, FileText, Award, Play, Shield, RefreshCw, TrendingDown, Minus, AlertTriangle, Trash2 } from 'lucide-react';
import client from '../../api/client';
import { clsx } from 'clsx';

/* ============================================================
   类型
   ============================================================ */
export interface PositionDetailData {
  fundCode: string;
  fundName: string;
  marketValue: number;
  dailyReturn: number;
  holdingReturn: number;
  holdingReturnRate: number;
  /** 持有份额（用于计算每日盈亏） */
  holdingShares: number;
  /** 成本净值 */
  costNav: number;
  /** 当前净值 */
  currentNav: number;
  /** 持仓起始日（格式 YYYY-MM-DD 或 YYYYMMDD） */
  buyDate: string;
  signalLevel: SignalLevel;
  confidenceStars: number;
  signalReason: string;

  /** 合规星级 */
  complianceStars: number;
  complianceDirection: 'new' | 'recent_close';
  operationTag: '加仓' | '减仓' | '持有' | '买入';
  recommendationReason: string;
  updateNote: string;

  /** 绩效记录 */
  winRate: number;
  winRateDetail: string;
  performanceRecords: {
    date: string;
    signal: string;
    operation: string;
    correctUp: boolean;
    correctDown: boolean;
    returnPct: number;
    reason: string;
  }[];

  /** 交易记录 */
  tradeRecords: {
    date: string;
    type: string;
    amount: number;
    nav: number;
    fee: number;
  }[];

  /** 净值走势 */
  navHistory: { date: string; nav: number; daily_return?: number }[];

  /** 趋势解读（来自后端 trend_text） */
  trendText?: string;
  /** 市场现状（来自后端 market_status） */
  marketStatus?: string;

  /** 趋势卫士完整结构化数据 */
  trendGuard?: {
    trend_signal: string;       // 上升/下降/震荡
    macd_signal: string;        // 金叉/死叉/中性
    oscillation_silence: boolean;
    gate_triggered: { gate: string; reason: string; threshold?: number } | null;
    operation_suggestion: string;
    trend_narrative: string;
  };

  /** 重仓股 */
  topHoldings: {
    name: string;
    pct: number;
    description: string;
  }[];

  /** 基础评级 */
  morningStarRating: number;
  ratingDetails: string[];

  /** 今日评估 */
  todayEvaluation: string;
  shortTerm: { label: string; reason: string };
  midTerm: { label: string; reason: string };
  longTerm: { label: string; reason: string };
}

interface PositionDetailPanelProps {
  data: PositionDetailData;
  onCollapse: () => void;
  onExecute?: () => Promise<void>;
  onDelete?: () => Promise<void>;
}

/* ============================================================
   工具函数
   ============================================================ */

/** 格式化金额 */
function formatMoney(v: number): string {
  if (Math.abs(v) >= 10000) {
    return `¥${(v / 10000).toFixed(2)}万`;
  }
  return `¥${v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

/** 格式化涨跌（A股习惯：红涨绿跌） */
function formatChange(v: number, showPercent = false): { text: string; className: string } {
  const sign = v >= 0 ? '+' : '';
  const cls = v >= 0 ? 'text-red-500' : 'text-green-500';
  const text = showPercent ? `${sign}${v.toFixed(2)}%` : `${sign}¥${Math.abs(v).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  return { text, className: cls };
}

/* ============================================================
   SVG 走势图组件
   ============================================================ */
function NavTrendChart({ data }: { data: { date: string; nav: number }[] }) {
  const width = 680;
  const height = 140;
  const padX = 40;
  const padY = 20;
  const innerW = width - padX * 2;
  const innerH = height - padY * 2;

  const validData = useMemo(() => {
    if (!data || data.length < 2) return [];
    return data.filter(d => d.nav > 0);
  }, [data]);

  if (validData.length < 2) {
    return (
      <div className="flex items-center justify-center h-24 text-xs text-gray-300">
        暂无走势数据
      </div>
    );
  }

  const navs = validData.map(d => d.nav);
  const minNav = Math.min(...navs);
  const maxNav = Math.max(...navs);
  const rangeNav = maxNav - minNav || 1;

  const points = validData.map((d, i) => {
    const x = padX + (i / (validData.length - 1)) * innerW;
    const y = padY + innerH - ((d.nav - minNav) / rangeNav) * innerH;
    return { x, y, date: d.date, nav: d.nav };
  });

  const linePath = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ');
  const areaPath = `M${points[0].x},${padY + innerH} ` +
    points.map(p => `L${p.x},${p.y}`).join(' ') +
    ` L${points[points.length - 1].x},${padY + innerH} Z`;

  const isUp = navs[navs.length - 1] >= navs[0];
  const strokeColor = '#14B8A6';

  // X轴标签（取5个点）
  const xLabels = points.filter((_, i) => i % Math.max(1, Math.floor(points.length / 5)) === 0 || i === points.length - 1);

  // Y轴标签
  const ySteps = 4;
  const yLabels = Array.from({ length: ySteps + 1 }, (_, i) => {
    const val = minNav + (rangeNav * i) / ySteps;
    const y = padY + innerH - (i / ySteps) * innerH;
    return { val, y };
  });

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full" style={{ height: `${height}px` }}>
      <defs>
        <linearGradient id="navAreaGrad" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={strokeColor} stopOpacity="0.2" />
          <stop offset="100%" stopColor={strokeColor} stopOpacity="0.02" />
        </linearGradient>
      </defs>

      {/* Y轴网格线 */}
      {yLabels.map((yl, i) => (
        <g key={i}>
          <line x1={padX} y1={yl.y} x2={width - padX} y2={yl.y} stroke="#E2E8F0" strokeWidth="0.5" />
          <text x={padX - 4} y={yl.y + 3} textAnchor="end" fill="#94A3B8" fontSize="8">{yl.val.toFixed(4)}</text>
        </g>
      ))}

      {/* 面积填充 */}
      <path d={areaPath} fill="url(#navAreaGrad)" />

      {/* 折线 */}
      <path d={linePath} fill="none" stroke={strokeColor} strokeWidth="1.5" />

      {/* 最后一个点标记 */}
      {points.length > 0 && (
        <circle cx={points[points.length - 1].x} cy={points[points.length - 1].y} r="3" fill={strokeColor} />
      )}

      {/* X轴标签 */}
      {xLabels.map((p, i) => (
        <text key={i} x={p.x} y={height - 2} textAnchor="middle" fill="#94A3B8" fontSize="7">
          {p.date.slice(5)}
        </text>
      ))}
    </svg>
  );
}

/* ============================================================
   净值历史列表组件
   ============================================================ */
function NavHistoryList({ data, marketValue, holdingShares, buyDate, tradeRecords }: { data: { date: string; nav: number; daily_return?: number }[]; marketValue: number; holdingShares: number; buyDate: string; tradeRecords: { date: string; type: string; amount: number; nav: number; fee: number }[] }) {
  const sorted = useMemo(() => {
    if (!data || data.length === 0) return [];
    return [...data].reverse().slice(0, 15);
  }, [data]);

  // 从交易记录回推每个日期的有效份额
  // 逻辑：某日期的份额 = currentShares - Σ(该日期之后的加仓份额) + Σ(该日期之后的减仓份额)
  const sharesAtDate = useMemo(() => {
    if (!tradeRecords || holdingShares <= 0) return new Map<string, number>();

    // 计算每笔交易的份额变化
    const tradeShares: { date: string; delta: number }[] = [];
    for (const t of tradeRecords) {
      const normalizedDate = t.date.replace(/-/g, '').slice(0, 8);  // YYYYMMDD
      if (t.nav <= 0) continue;
      const delta = t.amount / t.nav;
      // 加仓/买入：之后日期份额更多 → 该日期之前份额要减去 delta
      if (t.type === '买入' || t.type === '加仓') {
        tradeShares.push({ date: normalizedDate, delta: -delta });  // 之前减
      }
      // 减仓/卖出：之后日期份额更少 → 该日期之前份额要加上 delta
      else if (t.type === '卖出' || t.type === '减仓') {
        tradeShares.push({ date: normalizedDate, delta: +delta });  // 之前加回
      }
    }

    // 按日期升序排序交易记录
    tradeShares.sort((a, b) => a.date.localeCompare(b.date));

    // 对每个 nav_history 日期，计算有效份额
    // 从当前份额开始，对该日期之后的交易累加 delta
    const map = new Map<string, number>();
    for (const item of sorted) {
      const itemDate = item.date.replace(/-/g, '').slice(0, 8);
      let effectiveShares = holdingShares;
      for (const ts of tradeShares) {
        // 该交易在 itemDate 之后 → 需要 apply delta
        if (ts.date > itemDate) {
          effectiveShares += ts.delta;
        }
      }
      // 不允许负份额（数据不完美时的兜底）
      map.set(itemDate, Math.max(0, effectiveShares));
    }
    return map;
  }, [sorted, tradeRecords, holdingShares]);

  if (sorted.length === 0) {
    return (
      <p className="text-[10px] text-gray-300 text-center py-2">暂无净值明细</p>
    );
  }

  return (
    <div className="max-h-[180px] overflow-y-auto">
      <table className="w-full text-[10px]">
        <thead className="sticky top-0 bg-gray-50">
          <tr className="text-gray-400 border-b border-gray-100">
            <th className="py-1 text-left font-medium">日期</th>
            <th className="py-1 text-right font-medium">净值</th>
            <th className="py-1 text-right font-medium">涨跌幅</th>
            <th className="py-1 text-right font-medium">每日盈亏</th>
          </tr>
        </thead>
        <tbody>
          {sorted.map((item, i) => {
            const ret = item.daily_return ?? 0;
            const retCls = ret > 0 ? 'text-red-500' : ret < 0 ? 'text-green-500' : 'text-gray-400';
            const retSign = ret > 0 ? '+' : '';
            // 格式化日期: "20260508" -> "05-08"
            const dateStr = item.date.length === 8
              ? `${item.date.slice(4, 6)}-${item.date.slice(6, 8)}`
              : item.date.slice(5);
            return (
              <tr key={i} className="border-b border-gray-50">
                <td className="py-1 text-gray-500 font-mono">{dateStr}</td>
                <td className="py-1 text-right text-gray-600 font-mono">{item.nav.toFixed(4)}</td>
                <td className={`py-1 text-right font-mono ${retCls}`}>
                  {retSign}{ret.toFixed(2)}%
                </td>
                <td className={`py-1 text-right font-mono ${retCls}`}>
                  {(() => {
                    const itemDate = item.date.replace(/-/g, '').slice(0, 8);
                    const holdDate = buyDate.replace(/-/g, '').slice(0, 8);
                    // 持仓起始日之前或无份额 → 不显示
                    if (!buyDate || itemDate < holdDate) return '-';
                    // 用回推的当日实际份额计算盈亏
                    const effShares = sharesAtDate.get(itemDate) ?? holdingShares;
                    if (effShares <= 0) return '-';
                    const pnl = effShares * item.nav * ret / 100;
                    return `${pnl >= 0 ? '+' : ''}${pnl.toFixed(2)}`;
                  })()}
                </td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}

/* ============================================================
   星级显示
   ============================================================ */
function StarRating({ value, max = 5 }: { value: number; max?: number }) {
  const clamped = Math.max(0, Math.min(max, value));
  return (
    <div className="flex items-center gap-0.5">
      {Array.from({ length: max }, (_, i) => (
        <Star
          key={i}
          className={clsx(
            'w-3 h-3',
            i < Math.floor(clamped)
              ? 'text-yellow-400 fill-yellow-400'
              : i < clamped
                ? 'text-yellow-400 fill-yellow-400/50'
                : 'text-gray-200'
          )}
        />
      ))}
      <span className="text-[10px] text-gray-400 ml-0.5">{clamped.toFixed(1)}</span>
    </div>
  );
}

/* ============================================================
   趋势卫士详情面板组件
   ============================================================ */
function TrendGuardPanel({ tg }: { tg: NonNullable<PositionDetailData['trendGuard']> }) {
  // 趋势方向图标和颜色
  const trendConfig = {
    '上升': { icon: TrendingUp, color: 'text-red-500', bg: 'bg-red-50', label: '上升趋势' },
    '下降': { icon: TrendingDown, color: 'text-green-500', bg: 'bg-green-50', label: '下降趋势' },
    '震荡': { icon: Minus, color: 'text-gray-500', bg: 'bg-gray-50', label: '震荡整理' },
  };
  const tc = trendConfig[tg.trend_signal as keyof typeof trendConfig] || trendConfig['震荡'];
  const TrendIcon = tc.icon;

  // MACD信号颜色
  const macdConfig = {
    '金叉': { color: 'text-red-500', bg: 'bg-red-50', label: 'MACD金叉（买入信号）' },
    '死叉': { color: 'text-green-500', bg: 'bg-green-50', label: 'MACD死叉（卖出信号）' },
    '中性': { color: 'text-gray-500', bg: 'bg-gray-50', label: 'MACD中性' },
  };
  const mc = macdConfig[tg.macd_signal as keyof typeof macdConfig] || macdConfig['中性'];

  // 闸门状态
  const gateConfig: Record<string, { color: string; bg: string; label: string }> = {
    'gate1': { color: 'text-orange-600', bg: 'bg-orange-50', label: '闸门1触发：过热减仓' },
    'gate2': { color: 'text-red-600', bg: 'bg-red-50', label: '闸门2触发：回撤止损' },
    'gate3': { color: 'text-red-700', bg: 'bg-red-100', label: '闸门3触发：极端恐慌' },
  };
  const gate = tg.gate_triggered;
  const gc = gate ? (gateConfig[gate.gate] || { color: 'text-gray-500', bg: 'bg-gray-50', label: gate.reason }) : { color: 'text-emerald-600', bg: 'bg-emerald-50', label: '三阶闸门未触发（安全）' };

  return (
    <div className="bg-gradient-to-r from-blue-50 to-indigo-50 rounded-lg p-3 space-y-2.5 border border-blue-100/50">
      {/* 标题行 */}
      <div className="flex items-center gap-2">
        <Shield className="w-3.5 h-3.5 text-blue-500" />
        <span className="text-xs font-medium text-gray-700">趋势卫士解读</span>
        <span className="text-[10px] text-gray-400 ml-auto">MA20 + MACD 双指标</span>
      </div>

      {/* 趋势方向 + MACD信号 并排 */}
      <div className="grid grid-cols-2 gap-2">
        {/* 趋势方向 */}
        <div className={clsx('rounded-md p-2 flex items-center gap-2', tc.bg)}>
          <TrendIcon className={clsx('w-4 h-4 shrink-0', tc.color)} />
          <div className="min-w-0">
            <p className="text-[10px] text-gray-400">MA20趋势</p>
            <p className={clsx('text-xs font-bold', tc.color)}>{tc.label}</p>
          </div>
        </div>

        {/* MACD信号 */}
        <div className={clsx('rounded-md p-2 flex items-center gap-2', mc.bg)}>
          <div className="min-w-0">
            <p className="text-[10px] text-gray-400">MACD指标</p>
            <p className={clsx('text-xs font-bold', mc.color)}>{mc.label}</p>
          </div>
        </div>
      </div>

      {/* 震荡市静音状态 */}
      {tg.oscillation_silence && (
        <div className="flex items-center gap-2 bg-amber-50 rounded-md p-1.5">
          <Minus className="w-3 h-3 text-amber-500 shrink-0" />
          <span className="text-[10px] text-amber-700">震荡市静音：当前为震荡市，建议持仓观望，避免频繁交易</span>
        </div>
      )}

      {/* 三阶清仓闸门状态 */}
      <div className={clsx('rounded-md p-2 flex items-center gap-2', gc.bg)}>
        {gate ? (
          <>
            <AlertTriangle className={clsx('w-3.5 h-3.5 shrink-0', gc.color)} />
            <div className="min-w-0">
              <p className={clsx('text-xs font-bold', gc.color)}>{gc.label}</p>
              {gate.reason && (
                <p className="text-[10px] text-gray-500 mt-0.5">{gate.reason}</p>
              )}
            </div>
          </>
        ) : (
          <>
            <Shield className="w-3.5 h-3.5 shrink-0 text-emerald-500" />
            <span className={clsx('text-xs font-medium', gc.color)}>{gc.label}</span>
          </>
        )}
      </div>

      {/* 操作建议 */}
      {tg.operation_suggestion && (
        <div className="flex items-start gap-2 bg-white/60 rounded-md p-2">
          <span className="text-[10px] text-gray-400 shrink-0 mt-0.5">操作建议</span>
          <span className="text-xs text-gray-700 font-medium leading-relaxed">{tg.operation_suggestion}</span>
        </div>
      )}

      {/* 趋势解读文案 */}
      {tg.trend_narrative && (
        <div className="flex items-start gap-2 bg-white/60 rounded-md p-2">
          <span className="text-[10px] text-gray-400 shrink-0 mt-0.5">综合解读</span>
          <span className="text-xs text-blue-600 font-medium leading-relaxed">{tg.trend_narrative}</span>
        </div>
      )}
    </div>
  );
}

/* ============================================================
   主组件
   ============================================================ */
export default function PositionDetailPanel({ data, onCollapse, onExecute, onDelete }: PositionDetailPanelProps) {


  // 仓位建议执行
  const [executeAmount, setExecuteAmount] = useState('');
  const [executing, setExecuting] = useState(false);

  // 数据回填
  const [backfilling, setBackfilling] = useState(false);
  const [dailyExecCount, setDailyExecCount] = useState(() => {
    // 从 localStorage 读取当日执行次数
    const key = `exec_count_${data.fundCode}_${new Date().toISOString().slice(0, 10)}`;
    return parseInt(localStorage.getItem(key) || '0', 10);
  });

  const DAILY_LIMIT = 3;
  const canExecute = dailyExecCount < DAILY_LIMIT;

  const handleExecute = async () => {
    if (!executeAmount || parseFloat(executeAmount) <= 0) return;
    if (!canExecute) return;
    if (!onExecute) return;

    setExecuting(true);
    try {
      await onExecute();
      // 更新执行计数
      const key = `exec_count_${data.fundCode}_${new Date().toISOString().slice(0, 10)}`;
      const newCount = dailyExecCount + 1;
      localStorage.setItem(key, String(newCount));
      setDailyExecCount(newCount);
      setExecuteAmount('');
    } finally {
      setExecuting(false);
    }
  };

  const handleBackfill = async () => {
    if (backfilling) return;
    setBackfilling(true);
    try {
      const resp = await client.post('/api/v5/admin/backfill-fund', { fund_code: data.fundCode });
      if (resp.data?.code === 0) {
        alert(resp.data?.data?.message || '数据回填成功');
      } else {
        alert(resp.data?.message || '回填失败');
      }
    } catch (err: any) {
      alert(err?.response?.data?.detail || err?.response?.data?.message || '回填请求失败');
    } finally {
      setBackfilling(false);
    }
  };

  return (
    <div className="bg-white border-t border-gray-100 animate-fadeIn">
      {/* ====== 子区1: 展开标题行 ====== */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-50">
        <div className="flex-1 min-w-0">
          <span className="text-sm font-bold text-gray-800 font-mono">{data.fundCode}</span>
        </div>

        {/* 市值+编辑 */}
        <div className="text-right shrink-0 mr-2">
          <p className="text-sm font-bold text-gray-800 font-mono">{formatMoney(data.marketValue)}</p>
          <button className="text-gray-300 hover:text-[var(--brand-cyan)] transition-colors text-xs ml-1" title="编辑">
            ✎
          </button>
        </div>



        {/* 信号+原因+收起 */}
        <div className="flex items-center gap-2 shrink-0 ml-2">
          <SentimentBadge level={data.signalLevel} size="sm" variant="inline" />
          <div className="max-w-[200px]">
            <ExpandableReason
              reason={adaptReason(data.signalReason, data.signalLevel)}
              signalLevel={data.signalLevel}
              actionAdvice={inferActionAdvice(data.signalLevel)}
              variant="compact"
              summaryMaxLength={20}
            />
          </div>
          {onDelete && (
            <button
              onClick={() => { if (confirm('确定删除该持仓？市值将退还到现金')) onDelete(); }}
              className="p-1 rounded hover:bg-red-50 transition-colors"
              title="删除持仓"
            >
              <Trash2 className="w-4 h-4 text-gray-400 hover:text-red-400" />
            </button>
          )}
          <button
            onClick={onCollapse}
            className="p-1 rounded hover:bg-gray-100 transition-colors"
          >
            <ChevronUp className="w-4 h-4 text-gray-400" />
          </button>
        </div>
      </div>

      <div className="px-4 py-3 space-y-4">
        {/* ====== 子区2: 合规星级 + 推荐理由 ====== */}
        <div className="bg-gray-50 rounded-lg p-3 space-y-2">
          <div className="flex items-center gap-3 flex-wrap">
            <span className="text-xs text-gray-500">
              {data.complianceDirection === 'new' ? '▲ 新仓' : '↓ 最近清仓'}
            </span>
            {data.complianceStars > 0 ? (
              <StarRating value={data.complianceStars} />
            ) : (
              <span className="text-[10px] text-gray-400">合规评级暂无数据</span>
            )}
            <span className={`text-xs px-2 py-0.5 rounded font-medium ${
              data.operationTag === '加仓' ? 'bg-red-50 text-red-600' :
              data.operationTag === '减仓' ? 'bg-green-50 text-green-600' :
              data.operationTag === '买入' ? 'bg-red-50 text-red-600' :
              'bg-gray-100 text-gray-600'
            }`}>
              {data.operationTag}
            </span>
          </div>
          <p className="text-xs text-gray-600 leading-relaxed">{data.recommendationReason}</p>
          {data.updateNote && (
            <p className="text-[10px] text-gray-400">{data.updateNote}</p>
          )}
        </div>

        {/* ====== 子区2.5: 操作建议执行 ====== */}
        {onExecute && (
          <div className="bg-gradient-to-r from-cyan-50 to-teal-50 rounded-lg p-3 space-y-2 border border-cyan-100/50">
            <div className="flex items-center gap-2">
              <Shield className="w-3.5 h-3.5 text-[var(--brand-cyan)]" />
              <span className="text-xs font-medium text-gray-700">操作建议执行</span>
              <span className={`text-[10px] ml-auto ${canExecute ? 'text-gray-400' : 'text-red-400'}`}>
                今日已执行 {dailyExecCount}/{DAILY_LIMIT} 次
              </span>
            </div>

            {data.operationTag === '持有' ? (
              <div className="flex items-center justify-center py-1.5">
                <span className="text-xs text-gray-500">当前建议持有，无需操作</span>
              </div>
            ) : (
              <div className="flex items-center gap-2">
                <span className="text-xs text-gray-500 shrink-0">
                  {data.operationTag === '加仓' || data.operationTag === '买入' ? '买入' : '卖出'}金额
                </span>
                <div className="flex-1 flex items-center gap-1">
                  <span className="text-xs text-gray-400">¥</span>
                  <input
                    type="text"
                    value={executeAmount}
                    onChange={(e) => setExecuteAmount(e.target.value.replace(/[^\d.]/g, ''))}
                    placeholder="输入金额"
                    disabled={!canExecute}
                    className="flex-1 text-sm font-mono border border-cyan-200 rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-[var(--brand-cyan)] disabled:bg-gray-100 disabled:text-gray-400"
                  />
                </div>
                <button
                  onClick={handleExecute}
                  disabled={!canExecute || !executeAmount || parseFloat(executeAmount) <= 0 || executing}
                  className={clsx(
                    'flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium transition-all',
                    canExecute && executeAmount && parseFloat(executeAmount) > 0 && !executing
                      ? 'bg-[var(--brand-cyan)] text-white hover:bg-[var(--brand-cyan-dark)] shadow-sm'
                      : 'bg-gray-100 text-gray-400 cursor-not-allowed'
                  )}
                >
                  <Play className="w-3 h-3" />
                  {executing ? '执行中...' : '执行'}
                </button>
              </div>
            )}

            {!canExecute && (
              <p className="text-[10px] text-red-400">今日执行次数已达上限，请明日再试</p>
            )}
          </div>
        )}

        {/* ====== 子区2.6: 趋势卫士解读（完整版） ====== */}
        {data.trendGuard ? (
          <TrendGuardPanel tg={data.trendGuard} />
        ) : (
          (data.trendText || data.marketStatus) && (
            <div className="bg-gradient-to-r from-blue-50 to-indigo-50 rounded-lg p-3 space-y-1.5 border border-blue-100/50">
              {data.marketStatus && (
                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-gray-400 shrink-0">市场现状</span>
                  <span className="text-xs text-gray-600 font-medium">{data.marketStatus}</span>
                </div>
              )}
              {data.trendText && (
                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-gray-400 shrink-0">趋势解读</span>
                  <span className="text-xs text-blue-600 font-medium">{data.trendText}</span>
                </div>
              )}
            </div>
          )
        )}

        {/* 数据回填按钮 */}
        <div className="flex items-center justify-end">
          <button
            onClick={handleBackfill}
            disabled={backfilling}
            className={clsx(
              'flex items-center gap-1 px-2.5 py-1 rounded-lg text-[10px] font-medium transition-all',
              backfilling
                ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                : 'bg-gray-50 text-gray-500 hover:bg-gray-100 hover:text-gray-700 border border-gray-200'
            )}
          >
            <RefreshCw className={clsx('w-3 h-3', backfilling && 'animate-spin')} />
            {backfilling ? '回填中...' : '数据回填'}
          </button>
        </div>

        {/* ====== 子区3: 绩效记录 ====== */}
        <div>
          <div className="flex items-center gap-2 mb-2">
            <Activity className="w-3.5 h-3.5 text-gray-400" />
            <span className="text-xs font-medium text-gray-600">绩效记录</span>
            <span className="text-[10px] text-gray-400 ml-auto">
              {data.winRate}% 胜率{data.winRateDetail && ` (${data.winRateDetail})`}
            </span>
          </div>
          {data.performanceRecords.length === 0 ? (
            <p className="text-[10px] text-gray-300 text-center py-2">暂无绩效记录</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-[10px]">
                <thead>
                  <tr className="text-gray-400 border-b border-gray-100">
                    <th className="py-1 text-left font-medium">日期</th>
                    <th className="py-1 text-left font-medium">操作</th>
                    <th className="py-1 text-left font-medium">仓位</th>
                    <th className="py-1 text-center font-medium">✓涨</th>
                    <th className="py-1 text-center font-medium">✓跌</th>
                    <th className="py-1 text-right font-medium">涨跌%</th>
                    <th className="py-1 text-left font-medium pl-2">原因</th>
                  </tr>
                </thead>
                <tbody>
                  {data.performanceRecords.slice(0, 5).map((rec, i) => {
                    const ret = formatChange(rec.returnPct, true);
                    return (
                      <tr key={i} className="border-b border-gray-50">
                        <td className="py-1 text-gray-500 font-mono">{rec.date}</td>
                        <td className="py-1">
                          <span className={`px-1 rounded text-[9px] font-medium ${
                            rec.signal === 'S+' ? 'bg-purple-100 text-purple-700' :
                            rec.signal === '⚠' ? 'bg-yellow-100 text-yellow-700' :
                            'bg-gray-100 text-gray-600'
                          }`}>
                            {rec.signal}
                          </span>
                          <span className="ml-1 text-gray-600">{rec.operation}</span>
                        </td>
                        <td className="py-1 text-gray-500">{rec.operation}</td>
                        <td className="py-1 text-center">{rec.correctUp ? '✓' : '☐'}</td>
                        <td className="py-1 text-center">{rec.correctDown ? '✓' : '☐'}</td>
                        <td className={`py-1 text-right font-mono ${ret.className}`}>{ret.text}</td>
                        <td className="py-1 text-gray-400 pl-2 truncate max-w-[160px]">{rec.reason}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* ====== 子区4: 交易记录 ====== */}
        <div>
          <div className="flex items-center gap-2 mb-2">
            <FileText className="w-3.5 h-3.5 text-gray-400" />
            <span className="text-xs font-medium text-gray-600">交易记录</span>
          </div>
          {data.tradeRecords.length === 0 ? (
            <p className="text-[10px] text-gray-300 text-center py-2">暂无交易记录</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-[10px]">
                <thead>
                  <tr className="text-gray-400 border-b border-gray-100">
                    <th className="py-1 text-left font-medium">日期</th>
                    <th className="py-1 text-left font-medium">类型</th>
                    <th className="py-1 text-right font-medium">金额</th>
                    <th className="py-1 text-right font-medium">净值</th>
                    <th className="py-1 text-right font-medium">费用</th>
                  </tr>
                </thead>
                <tbody>
                  {data.tradeRecords.map((rec, i) => (
                    <tr key={i} className="border-b border-gray-50">
                      <td className="py-1 text-gray-500 font-mono">{rec.date}</td>
                      <td className={`py-1 font-medium ${
                        rec.type === '买入' ? 'text-red-500' :
                        rec.type === '卖出' ? 'text-green-500' :
                        'text-gray-500'
                      }`}>{rec.type}</td>
                      <td className="py-1 text-right text-gray-600 font-mono">¥{rec.amount.toLocaleString()}</td>
                      <td className="py-1 text-right text-gray-500 font-mono">{rec.nav > 0 ? rec.nav.toFixed(4) : '-'}</td>
                      <td className="py-1 text-right text-gray-400 font-mono">{rec.fee > 0 ? rec.fee.toLocaleString() : '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>

        {/* ====== 子区5: 近期走势图 ====== */}
        <div>
          <div className="flex items-center justify-between mb-2">
            <div className="flex items-center gap-2">
              <TrendingUp className="w-3.5 h-3.5 text-gray-400" />
              <span className="text-xs font-medium text-gray-600">近期走势图</span>
            </div>
            <span className="text-[10px] text-gray-400">近3月</span>
          </div>
          <div className="bg-gray-50 rounded-lg p-2">
            <NavTrendChart data={data.navHistory} />
          </div>
          {/* 净值历史明细列表 */}
          <div className="mt-2">
            <NavHistoryList data={data.navHistory} marketValue={data.marketValue} holdingShares={data.holdingShares} buyDate={data.buyDate} tradeRecords={data.tradeRecords} />
          </div>
        </div>

        {/* ====== 子区6: 前N大重仓股 ====== */}
        <div>
          <div className="flex items-center gap-2 mb-2">
            <BarChart3 className="w-3.5 h-3.5 text-gray-400" />
            <span className="text-xs font-medium text-gray-600">
              前{Math.max(data.topHoldings.length, 1)}大重仓股
            </span>
          </div>
          {data.topHoldings.length === 0 ? (
            <p className="text-[10px] text-gray-300 text-center py-2">暂无重仓股数据</p>
          ) : (
            <div className="grid grid-cols-2 gap-x-4 gap-y-2">
              {data.topHoldings.map((stock, i) => (
                <div key={i} className="flex items-start justify-between">
                  <div className="min-w-0">
                    <p className="text-xs font-medium text-gray-700 truncate">{stock.name}</p>
                    <p className="text-[10px] text-gray-400 truncate">{stock.description}</p>
                  </div>
                  <span className="text-[10px] text-gray-500 font-mono shrink-0 ml-2">{stock.pct.toFixed(2)}%</span>
                </div>
              ))}
            </div>
          )}
        </div>

        {/* ====== 子区7: 基础评级 ====== */}
        <div>
          <div className="flex items-center gap-2 mb-2">
            <Award className="w-3.5 h-3.5 text-gray-400" />
            <span className="text-xs font-medium text-gray-600">基础评级</span>
          </div>
          {data.morningStarRating > 0 || data.ratingDetails.length > 0 ? (
            <div className="bg-gray-50 rounded-lg p-3 space-y-1.5">
              {data.morningStarRating > 0 && (
                <div className="flex items-center gap-2">
                  <span className="text-xs text-gray-500">晨星评级</span>
                  <StarRating value={data.morningStarRating} />
                </div>
              )}
              {data.ratingDetails.map((detail, i) => (
                <p key={i} className="text-[10px] text-gray-400">{detail}</p>
              ))}
            </div>
          ) : (
            <p className="text-[10px] text-gray-300 text-center py-2">基础评级暂无数据</p>
          )}
        </div>

        {/* ====== 子区8: 今日评估 + 趋势判断 ====== */}
        <div>
          <div className="flex items-center gap-2 mb-2">
            <span className="inline-block w-2 h-2 rounded-full bg-[var(--brand-cyan)]" />
            <span className="text-xs font-medium text-gray-600">今日评估</span>
          </div>
          <p className="text-xs text-gray-500 leading-relaxed mb-3">{data.todayEvaluation}</p>

          <div className="grid grid-cols-3 gap-3">
            {([
              { period: '短期', judgment: data.shortTerm.label, reason: data.shortTerm.reason },
              { period: '中期', judgment: data.midTerm.label, reason: data.midTerm.reason },
              { period: '长期', judgment: data.longTerm.label, reason: data.longTerm.reason },
            ]).map((term) => (
              <div key={term.period} className="bg-gray-50 rounded-lg p-3 text-center">
                <p className="text-[10px] text-gray-400 mb-1">{term.period}</p>
                <p className={`text-sm font-bold ${
                  term.judgment === '看多'
                    ? 'text-red-500'
                    : term.judgment === '看空'
                      ? 'text-green-500'
                      : 'text-gray-600'
                }`}>
                  {term.judgment}
                </p>
                <p className="text-[10px] text-gray-400 mt-0.5 truncate">{term.reason}</p>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
