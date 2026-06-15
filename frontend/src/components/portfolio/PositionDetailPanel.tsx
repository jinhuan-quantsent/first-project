/**
 * PositionDetailPanel - 持仓详情展开面板
 * 包含：合规星级+推荐理由 / 绩效记录 / 交易记录 / 走势图 / 重仓股 / 基础评级 / 今日评估
 */
import { useMemo } from 'react';
import type { SignalLevel } from '../../types';
import SentimentBadge from '../common/SentimentBadge';
import { Star, TrendingUp, ChevronUp, BarChart3, Activity, FileText, Award } from 'lucide-react';
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
  navHistory: { date: string; nav: number }[];

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
   主组件
   ============================================================ */
export default function PositionDetailPanel({ data, onCollapse }: PositionDetailPanelProps) {
  const daily = formatChange(data.dailyReturn);
  const holding = formatChange(data.holdingReturn);
  const holdingRate = formatChange(data.holdingReturnRate, true);

  return (
    <div className="bg-white border-t border-gray-100 animate-fadeIn">
      {/* ====== 子区1: 展开标题行 ====== */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-50">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-bold text-gray-800 truncate">{data.fundName}</span>
          </div>
          <span className="text-[10px] text-gray-400 font-mono">{data.fundCode}</span>
        </div>

        {/* 市值+编辑 */}
        <div className="text-right shrink-0 mr-2">
          <p className="text-sm font-bold text-gray-800 font-mono">{formatMoney(data.marketValue)}</p>
          <button className="text-gray-300 hover:text-[var(--brand-cyan)] transition-colors text-xs ml-1" title="编辑">
            ✎
          </button>
        </div>

        {/* 昨收/持有 */}
        <div className="text-right shrink-0 space-y-0.5">
          <p className={`text-xs font-mono ${daily.className}`}>
            昨收 {daily.text}
          </p>
          <p className={`text-xs font-mono ${holding.className}`}>
            持有 {holding.text}
            <span className={`ml-1 ${holdingRate.className}`}>({holdingRate.text})</span>
          </p>
        </div>

        {/* 信号+原因+收起 */}
        <div className="flex items-center gap-2 shrink-0 ml-2">
          <SentimentBadge level={data.signalLevel} size="sm" variant="inline" />
          <span className="text-[10px] text-gray-400 truncate max-w-[120px]">{data.signalReason}</span>
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
            <StarRating value={data.complianceStars} />
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
          <div className="bg-gray-50 rounded-lg p-3 space-y-1.5">
            <div className="flex items-center gap-2">
              <span className="text-xs text-gray-500">晨星评级</span>
              <StarRating value={data.morningStarRating} />
            </div>
            {data.ratingDetails.map((detail, i) => (
              <p key={i} className="text-[10px] text-gray-400">{detail}</p>
            ))}
          </div>
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
