/**
 * PortfolioV5 - V5.0 持仓页（模板对齐增强版）
 * 持仓汇总 + 可展开条目 + 迷你走势图 + 持仓股票 + 基金评估 + 执行按钮
 */
import { useState, useCallback, useEffect, useMemo } from 'react';
import type { PortfolioItem, PortfolioSummary, SignalLevel } from '../types';
import { Plus, TrendingUp, TrendingDown, Minus, Briefcase, BarChart3, Eye } from 'lucide-react';
import { clsx } from 'clsx';
import ExecutionButton from '../components/fundsearch/ExecutionButton';
import {
  fetchPortfolioV5,
  fetchAdviceHistoryV5,
  fetchTradeRecordsV5,
  executePositionV5,
} from '../api/portfolioV5';
import { fetchV5Sentiment } from '../api/marketV5';

/* ============================================================
   信号颜色映射
   ============================================================ */
const SIGNAL_BG: Record<string, string> = {
  'S+': 'bg-purple-100 text-purple-700', S: 'bg-blue-100 text-blue-700',
  A: 'bg-cyan-100 text-cyan-700', B: 'bg-lime-100 text-lime-700',
  C: 'bg-yellow-100 text-yellow-700', D: 'bg-orange-100 text-orange-700',
  E: 'bg-red-100 text-red-700',
};

/* ============================================================
   子组件
   ============================================================ */

/** 持仓汇总卡片 */
function PortfolioSummaryCard({ data }: { data: PortfolioSummary }) {
  const returnClass = data.total_return_rate >= 0 ? 'text-red-500' : 'text-green-500';
  const dailyClass  = data.daily_return    >= 0 ? 'text-red-500' : 'text-green-500';
  return (
    <div className="card p-4 grid grid-cols-2 md:grid-cols-4 gap-4">
      <div>
        <p className="text-[10px] text-gray-400">总市值</p>
        <p className="text-lg font-bold text-gray-800">¥{(data.total_value / 10000).toFixed(2)}万</p>
      </div>
      <div>
        <p className="text-[10px] text-gray-400">累计收益</p>
        <p className={`text-lg font-bold ${returnClass}`}>
          {data.total_return >= 0 ? '+' : ''}¥{(data.total_return / 10000).toFixed(2)}万
        </p>
      </div>
      <div>
        <p className="text-[10px] text-gray-400">今日收益</p>
        <p className={`text-lg font-bold ${dailyClass}`}>
          {data.daily_return >= 0 ? '+' : ''}¥{data.daily_return.toFixed(0)}
        </p>
      </div>
      <div>
        <p className="text-[10px] text-gray-400">核心/卫星比</p>
        <p className="text-lg font-bold text-gray-800">
          {Math.round(data.core_ratio * 100)}% / {Math.round(data.satellite_ratio * 100)}%
        </p>
      </div>
    </div>
  );
}

/** SVG 迷你走势图（30天净值） */
function MiniChart({ values, width = 200, height = 48 }: { values: number[]; width?: number; height?: number }) {
  if (!values || values.length < 2) {
    return (
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full" style={{ height: `${height}px` }}>
        <text x={width / 2} y={height / 2} textAnchor="middle" fill="#CBD5E1" fontSize="8">暂无数据</text>
      </svg>
    );
  }

  const padX = 4, padY = 4;
  const innerW = width - padX * 2, innerH = height - padY * 2;
  const minV = Math.min(...values), maxV = Math.max(...values);
  const rangeV = maxV - minV || 1;

  const points = values.map((v, i) => {
    const x = padX + (i / (values.length - 1)) * innerW;
    const y = padY + innerH - ((v - minV) / rangeV) * innerH;
    return `${x},${y}`;
  });

  const isUp = values[values.length - 1] >= values[0];
  const strokeColor = isUp ? '#EF4444' : '#22C55E';
  const fillColor = isUp ? '#FEE2E2' : '#DCFCE7';

  // 面积路径
  const areaPath = `M${points[0].split(',')[0]},${padY + innerH} ` +
    points.map((p, i) => `${i === 0 ? 'L' : ''}${p}`).join(' L') +
    ` L${padX + innerW},${padY + innerH} Z`;
  const linePath = `M${points.join(' L')}`;

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full" style={{ height: `${height}px` }}>
      <defs>
        <linearGradient id={`miniGrad-${isUp ? 'up' : 'down'}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={strokeColor} stopOpacity="0.15" />
          <stop offset="100%" stopColor={strokeColor} stopOpacity="0.02" />
        </linearGradient>
      </defs>
      <path d={areaPath} fill={`url(#miniGrad-${isUp ? 'up' : 'down'})`} />
      <path d={linePath} fill="none" stroke={strokeColor} strokeWidth="1.5" />
    </svg>
  );
}

/** 前8大持仓股票 */
function TopHoldings({ stocks }: { stocks: { name: string; pct: number; change: number }[] }) {
  if (!stocks || stocks.length === 0) {
    return (
      <div className="text-[10px] text-gray-300 text-center py-2">
        持仓股票数据暂无
      </div>
    );
  }

  return (
    <div className="space-y-1">
      <p className="text-[10px] text-gray-500 font-medium flex items-center gap-1">
        <BarChart3 className="w-3 h-3" /> 前{stocks.length}大持仓股票
      </p>
      <div className="grid grid-cols-2 gap-x-4 gap-y-0.5">
        {stocks.map((s, i) => (
          <div key={i} className="flex items-center justify-between text-[10px]">
            <span className="text-gray-600 truncate">{s.name}</span>
            <span className="flex items-center gap-1 shrink-0 ml-2">
              <span className="text-gray-400 font-mono">{(s.pct * 100).toFixed(1)}%</span>
              <span className={`font-mono ${s.change >= 0 ? 'text-red-500' : 'text-green-500'}`}>
                {s.change >= 0 ? '+' : ''}{s.change.toFixed(2)}%
              </span>
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

/** 基金评估（短/中/长期） */
function FundEvaluation({ evaluation }: {
  evaluation?: {
    short_term: { label: string; score: number; reason: string };
    mid_term: { label: string; score: number; reason: string };
    long_term: { label: string; score: number; reason: string };
  };
}) {
  if (!evaluation) {
    return (
      <div className="text-[10px] text-gray-300 text-center py-2">
        基金评估数据暂无
      </div>
    );
  }

  const terms = [
    { key: 'short_term', label: '短期', data: evaluation.short_term },
    { key: 'mid_term', label: '中期', data: evaluation.mid_term },
    { key: 'long_term', label: '长期', data: evaluation.long_term },
  ] as const;

  const scoreColor = (score: number) => {
    if (score >= 70) return 'text-red-500';
    if (score >= 40) return 'text-yellow-600';
    return 'text-green-500';
  };

  return (
    <div className="space-y-1.5">
      <p className="text-[10px] text-gray-500 font-medium flex items-center gap-1">
        <Eye className="w-3 h-3" /> 基金评估
      </p>
      <div className="grid grid-cols-3 gap-2">
        {terms.map(t => (
          <div key={t.key} className="bg-gray-50 rounded p-2 text-center">
            <p className="text-[9px] text-gray-400">{t.label}</p>
            <p className={`text-sm font-bold ${scoreColor(t.data.score)}`}>{t.data.label}</p>
            <p className="text-[9px] text-gray-400">{t.data.score}分</p>
          </div>
        ))}
      </div>
    </div>
  );
}

function ChevronIcon({ expanded }: { expanded: boolean }) {
  return (
    <svg className={`w-4 h-4 text-gray-400 transition-transform ${expanded ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
    </svg>
  );
}

/** 单条持仓条目（可展开 + 增强内容） */
function PositionItem({
  item,
  onToggle,
  expanded,
  signal,
  onExecute,
  navHistory,
  topStocks,
  evaluation,
}: {
  item: PortfolioItem;
  onToggle: () => void;
  expanded: boolean;
  signal: { signalLevel: SignalLevel; confidenceStars: number } | undefined;
  onExecute: () => Promise<void>;
  navHistory?: number[];
  topStocks?: { name: string; pct: number; change: number }[];
  evaluation?: {
    short_term: { label: string; score: number; reason: string };
    mid_term: { label: string; score: number; reason: string };
    long_term: { label: string; score: number; reason: string };
  };
}) {
  const returnClass = item.return_rate >= 0 ? 'text-red-500' : 'text-green-500';
  const dailyClass  = item.daily_return >= 0 ? 'text-red-500' : 'text-green-500';
  const tagColor = item.portfolio_tag === 'core' ? 'bg-brand-50 text-brand-600' : 'bg-amber-50 text-amber-700';
  const fundShortName = (item as any).fund_short_name || item.fund_name;

  return (
    <div className="border-t border-gray-100">
      {/* 主行 */}
      <div
        onClick={onToggle}
        className="flex items-center gap-3 px-4 py-3 cursor-pointer hover:bg-gray-50 transition-colors"
      >
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-xs font-mono text-gray-400">{item.fund_code}</span>
            <span className="text-sm font-medium text-gray-800 truncate">{fundShortName}</span>
            <span className={`text-[10px] px-1.5 py-0.5 rounded ${tagColor}`}>
              {item.portfolio_tag === 'core' ? '核心' : '卫星'}
            </span>
            {signal && (
              <span className={`text-[10px] px-1.5 py-0.5 rounded font-bold ${SIGNAL_BG[signal.signalLevel] || ''}`}>
                {signal.signalLevel}
              </span>
            )}
          </div>
          <p className="text-[10px] text-gray-400 mt-0.5">
            持仓 {item.weight_pct * 100}% | 成本 {item.cost_nav.toFixed(4)}
          </p>
        </div>

        {/* 迷你走势图 */}
        {navHistory && navHistory.length > 1 && (
          <div className="w-20 shrink-0 hidden sm:block">
            <MiniChart values={navHistory} width={80} height={28} />
          </div>
        )}

        <div className="text-right shrink-0">
          <p className="text-sm font-mono font-medium text-gray-800">¥{(item.market_value / 10000).toFixed(2)}万</p>
          <p className={`text-xs font-mono ${returnClass}`}>
            {item.return_rate >= 0 ? '+' : ''}{item.return_rate.toFixed(2)}%
          </p>
        </div>

        <div className={`text-xs font-mono shrink-0 w-16 text-right ${dailyClass}`}>
          {item.daily_return >= 0 ? '+' : ''}{item.daily_return.toFixed(0)}
        </div>

        <ChevronIcon expanded={expanded} />
      </div>

      {/* 展开区域 */}
      {expanded && (
        <div className="px-4 pb-4 space-y-3 animate-fadeIn">
          {/* 操作建议 */}
          <div className="bg-gray-50 rounded-lg p-3 flex items-center justify-between">
            <div className="text-xs text-gray-500">
              当前仓位 <span className="font-bold text-gray-800">{(item.weight_pct * 100).toFixed(0)}%</span>
            </div>
            <ExecutionButton
              fundCode={item.fund_code}
              fundName={fundShortName}
              signalLevel={signal?.signalLevel ?? 'B'}
              confidenceStars={signal?.confidenceStars ?? 3}
              currentPositionPct={item.weight_pct}
              targetPositionPct={Math.min(0.95, item.weight_pct + 0.10)}
              onExecute={onExecute}
            />
          </div>

          {/* 增强内容网格 */}
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {/* 迷你走势图（展开版） */}
            <div className="bg-gray-50 rounded-lg p-3">
              <p className="text-[10px] text-gray-400 mb-1">近30天净值走势</p>
              <MiniChart values={navHistory || []} width={260} height={64} />
              <div className="flex justify-between mt-1">
                <span className="text-[9px] text-gray-300">30天前</span>
                <span className="text-[9px] text-gray-300">今天</span>
              </div>
            </div>

            {/* 持仓股票 */}
            <div className="bg-gray-50 rounded-lg p-3">
              <TopHoldings stocks={topStocks || []} />
            </div>

            {/* 基金评估 */}
            <div className="bg-gray-50 rounded-lg p-3">
              <FundEvaluation evaluation={evaluation} />
            </div>
          </div>

          {/* 简要信息 */}
          <div className="grid grid-cols-3 gap-2 text-[10px] text-gray-400">
            <div>买入日期：{item.buy_date}</div>
            <div>持有份额：{item.holding_shares.toLocaleString()}</div>
            <div>当前净值：{item.current_nav.toFixed(4)}</div>
          </div>
        </div>
      )}
    </div>
  );
}

/* ============================================================
   主页面组件
   ============================================================ */
export default function PortfolioV5() {
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [tab, setTab] = useState<'positions' | 'advice' | 'trades'>('positions');

  // API 数据状态
  const [summary, setSummary] = useState<PortfolioSummary | null>(null);
  const [items, setItems] = useState<PortfolioItem[]>([]);
  const [advice, setAdvice] = useState<any[]>([]);
  const [trades, setTrades] = useState<any[]>([]);
  const [signals, setSignals] = useState<Record<string, { signalLevel: SignalLevel; confidenceStars: number }>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // 增强数据（mock占位，后续接真实API）
  const [navHistories, setNavHistories] = useState<Record<string, number[]>>({});
  const [topStocksMap, setTopStocksMap] = useState<Record<string, { name: string; pct: number; change: number }[]>>({});
  const [evaluationsMap, setEvaluationsMap] = useState<Record<string, any>>({});

  const toggleExpand = useCallback((id: number) => {
    setExpandedId(prev => prev === id ? null : id);
  }, []);

  /** 加载持仓数据 */
  useEffect(() => {
    let cancelled = false;
    const loadData = async () => {
      setLoading(true);
      setError(null);
      try {
        const [portfolioData, adviceData, tradeData] = await Promise.all([
          fetchPortfolioV5(),
          fetchAdviceHistoryV5().catch(() => ({ items: [], stats: {} })),
          fetchTradeRecordsV5().catch(() => ({ items: [] })),
        ]);

        if (cancelled) return;

        const safePortfolioData = portfolioData || { items: [], summary: null };
        const safeItems = Array.isArray(safePortfolioData.items) ? safePortfolioData.items : [];
        const safeSummary = safePortfolioData.summary || null;

        setSummary(safeSummary);
        setItems(safeItems);
        setAdvice(adviceData?.items ?? []);
        setTrades(tradeData?.items ?? []);

        if (safeItems.length === 0) {
          if (!cancelled) setLoading(false);
          return;
        }

        // 并行获取每只基金的V5信号
        const signalEntries = await Promise.all(
          safeItems.map(async (item) => {
            try {
              const sentiment = await fetchV5Sentiment(item.fund_code);
              return [item.fund_code, {
                signalLevel: sentiment.signal_level as SignalLevel,
                confidenceStars: sentiment.confidence_stars,
              }] as [string, { signalLevel: SignalLevel; confidenceStars: number }];
            } catch {
              return null;
            }
          }),
        );

        if (cancelled) return;

        const signalMap: Record<string, { signalLevel: SignalLevel; confidenceStars: number }> = {};
        signalEntries.forEach((entry) => {
          if (entry) signalMap[entry[0]] = entry[1];
        });
        setSignals(signalMap);

        // 生成模拟增强数据（TODO: 接真实API）
        const mockNavHistories: Record<string, number[]> = {};
        const mockTopStocks: Record<string, { name: string; pct: number; change: number }[]> = {};
        const mockEvaluations: Record<string, any> = {};

        safeItems.forEach(item => {
          // 模拟30天净值走势
          const baseNav = item.current_nav || 1.0;
          const navs: number[] = [];
          for (let d = 30; d >= 0; d--) {
            const noise = (Math.random() - 0.48) * 0.02;
            const trend = item.return_rate > 0 ? 0.001 : -0.001;
            const nav = baseNav * (1 + trend * (30 - d) + noise * Math.sqrt(30 - d));
            navs.push(parseFloat(nav.toFixed(4)));
          }
          mockNavHistories[item.fund_code] = navs;

          // 模拟前8大持仓股票
          const stockNames = ['贵州茅台', '宁德时代', '招商银行', '中国平安', '隆基绿能', '比亚迪', '腾讯控股', '美的集团'];
          const totalPct = 0.55;
          mockTopStocks[item.fund_code] = stockNames.slice(0, 8).map((name, i) => ({
            name,
            pct: parseFloat(((totalPct / 8) * (1 - i * 0.05)).toFixed(3)),
            change: parseFloat(((Math.random() - 0.45) * 4).toFixed(2)),
          }));

          // 模拟基金评估
          const signal = signalMap[item.fund_code]?.signalLevel || 'B';
          const isFear = ['S+', 'S', 'A'].includes(signal);
          mockEvaluations[item.fund_code] = {
            short_term: {
              label: isFear ? '加仓' : '观望',
              score: isFear ? 75 : 35,
              reason: isFear ? '恐惧区间' : '贪婪区间',
            },
            mid_term: {
              label: item.return_rate > 0 ? '持有' : '减仓',
              score: item.return_rate > 0 ? 65 : 30,
              reason: item.return_rate > 0 ? '正收益' : '负收益',
            },
            long_term: {
              label: '定投',
              score: 55,
              reason: '长期配置',
            },
          };
        });

        setNavHistories(mockNavHistories);
        setTopStocksMap(mockTopStocks);
        setEvaluationsMap(mockEvaluations);
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

  /** 执行仓位调整 */
  const handleExecute = useCallback(async (item: PortfolioItem) => {
    const signal = signals[item.fund_code];
    await executePositionV5({
      fund_code: item.fund_code,
      target_position_pct: Math.min(0.95, item.weight_pct + 0.10),
      signal_level: signal?.signalLevel ?? 'B',
      confidence_stars: signal?.confidenceStars ?? 3,
    });
  }, [signals]);

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto space-y-4">
        <div>
          <h1 className="text-xl font-bold text-gray-800">我的持仓 V5.0</h1>
          <p className="text-xs text-gray-400 mt-0.5">持仓汇总 · 仓位建议 · 走势分析</p>
        </div>
        <div className="card p-8 text-center">
          <div className="inline-block w-6 h-6 border-2 border-brand-500 border-t-transparent rounded-full animate-spin" />
          <p className="text-gray-400 text-sm mt-2">加载持仓数据...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-4xl mx-auto space-y-4">
        <div>
          <h1 className="text-xl font-bold text-gray-800">我的持仓 V5.0</h1>
          <p className="text-xs text-gray-400 mt-0.5">持仓汇总 · 仓位建议 · 走势分析</p>
        </div>
        <div className="card p-8 text-center">
          <p className="text-red-500 text-sm">{error}</p>
          <button onClick={() => window.location.reload()}
            className="mt-3 px-4 py-1.5 text-xs bg-brand-500 text-white rounded-lg hover:bg-brand-600">
            重试
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-4xl mx-auto space-y-4">
      <div>
        <h1 className="text-xl font-bold text-gray-800">我的持仓 V5.0</h1>
        <p className="text-xs text-gray-400 mt-0.5">持仓汇总 · 仓位建议 · 走势分析</p>
      </div>

      {/* 汇总 */}
      {summary && <PortfolioSummaryCard data={summary} />}

      {/* Tab 切换 */}
      <div className="flex gap-1">
        {([
          { key: 'positions', label: `持仓 (${items.length})` },
          { key: 'advice',    label: '历史建议' },
          { key: 'trades',    label: '交易记录' },
        ] as { key: 'positions' | 'advice' | 'trades'; label: string }[]).map(t => (
          <button key={t.key} onClick={() => setTab(t.key)}
            className={`px-3 py-1.5 text-xs rounded-lg border transition-colors ${
              tab === t.key ? 'bg-brand-500 text-white border-brand-500' : 'bg-white text-gray-500 border-gray-200 hover:bg-gray-50'
            }`}>
            {t.label}
          </button>
        ))}
      </div>

      {/* 持仓列表 */}
      {tab === 'positions' && (
        <div className="card overflow-hidden">
          {items.length === 0 ? (
            <div className="p-8 text-center">
              <Briefcase className="w-8 h-8 text-gray-300 mx-auto mb-2" />
              <p className="text-gray-500 text-sm font-medium">暂无持仓数据</p>
              <p className="text-[10px] text-gray-300 mt-1">添加持仓基金后，即可查看仓位建议和交易操作</p>
            </div>
          ) : (
            items.map(item => (
              <PositionItem
                key={item.id}
                item={item}
                expanded={expandedId === item.id}
                onToggle={() => toggleExpand(item.id)}
                signal={signals[item.fund_code]}
                onExecute={() => handleExecute(item)}
                navHistory={navHistories[item.fund_code]}
                topStocks={topStocksMap[item.fund_code]}
                evaluation={evaluationsMap[item.fund_code]}
              />
            ))
          )}
        </div>
      )}

      {/* 历史建议 */}
      {tab === 'advice' && (
        <div className="card p-4 space-y-2">
          {advice.length === 0 ? (
            <div className="py-6 text-center">
              <p className="text-gray-500 text-sm font-medium">暂无历史建议</p>
              <p className="text-[10px] text-gray-300 mt-1">执行仓位调整后，建议记录将在此展示</p>
            </div>
          ) : (
            advice.map((a: any, i: number) => (
              <div key={i} className="flex items-center gap-3 text-sm border-b border-gray-50 pb-2">
                <span className="text-[10px] text-gray-400 w-20">{a.date}</span>
                <span className="font-mono text-xs">{a.fund_code}</span>
                <span className={`text-[10px] px-1.5 py-0.5 rounded ${SIGNAL_BG[a.signal_level] || 'bg-gray-100 text-gray-600'}`}>
                  {a.signal_level}
                </span>
                <span className="text-xs text-gray-600">{a.action}</span>
                <span className="text-[10px] text-gray-400 flex-1 truncate">{a.reason}</span>
              </div>
            ))
          )}
        </div>
      )}

      {/* 交易记录 */}
      {tab === 'trades' && (
        <div className="card p-4 space-y-2">
          {trades.length === 0 ? (
            <div className="py-6 text-center">
              <p className="text-gray-500 text-sm font-medium">暂无交易记录</p>
              <p className="text-[10px] text-gray-300 mt-1">执行仓位操作后，交易记录将在此展示</p>
            </div>
          ) : (
            trades.map((t: any, i: number) => (
              <div key={i} className="flex items-center gap-3 text-sm border-b border-gray-50 pb-2">
                <span className="text-[10px] text-gray-400 w-20">{t.date}</span>
                <span className={`text-xs font-medium ${t.action === '买入' ? 'text-red-500' : 'text-green-500'}`}>
                  {t.action}
                </span>
                <span className="font-mono text-xs">{t.fund_code}</span>
                <span className="text-xs text-gray-600">¥{t.amount?.toLocaleString?.() ?? t.price?.toLocaleString?.() ?? '-'}</span>
                <span className="text-[10px] text-gray-400 flex-1 truncate">{t.reason}</span>
              </div>
            ))
          )}
        </div>
      )}
    </div>
  );
}
