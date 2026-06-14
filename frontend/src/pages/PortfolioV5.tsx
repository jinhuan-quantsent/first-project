/**
 * PortfolioV5 - V5.0 持仓页
 * 持仓汇总 + 可展开条目 + 执行按钮 + 历史建议 + 交易记录
 */
import { useState, useCallback, useEffect } from 'react';
import type { PortfolioItem, PortfolioSummary, SignalLevel } from '../../types';
import { Plus, TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { clsx } from 'clsx';
import ExecutionButton from '../../components/fundsearch/ExecutionButton';
import {
  fetchPortfolioV5,
  fetchAdviceHistoryV5,
  fetchTradeRecordsV5,
  executePositionV5,
} from '../api/portfolioV5';
import { fetchV5Sentiment } from '../api/marketV5';

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

/** 单条持仓条目（可展开） */
function PositionItem({
  item,
  onToggle,
  expanded,
  signal,
  onExecute,
}: {
  item: PortfolioItem;
  onToggle: () => void;
  expanded: boolean;
  signal: { signalLevel: SignalLevel; confidenceStars: number } | undefined;
  onExecute: () => Promise<void>;
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
          </div>
          <p className="text-[10px] text-gray-400 mt-0.5">
            持仓 {item.weight_pct * 100}% | 成本 {item.cost_nav.toFixed(4)}
          </p>
        </div>

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

function ChevronIcon({ expanded }: { expanded: boolean }) {
  return (
    <svg className={`w-4 h-4 text-gray-400 transition-transform ${expanded ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
    </svg>
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
        // 并行获取持仓、历史建议、交易记录
        const [portfolioData, adviceData, tradeData] = await Promise.all([
          fetchPortfolioV5(),
          fetchAdviceHistoryV5().catch(() => ({ items: [], stats: {} })),
          fetchTradeRecordsV5().catch(() => ({ items: [] })),
        ]);

        if (cancelled) return;

        setSummary(portfolioData.summary);
        setItems(portfolioData.items);
        setAdvice(adviceData.items);
        setTrades(tradeData.items);

        // 并行获取每只基金的V5信号
        const signalEntries = await Promise.all(
          portfolioData.items.map(async (item) => {
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
          <p className="text-xs text-gray-400 mt-0.5">持仓汇总 · 仓位建议 · 交易记录</p>
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
          <p className="text-xs text-gray-400 mt-0.5">持仓汇总 · 仓位建议 · 交易记录</p>
        </div>
        <div className="card p-8 text-center">
          <p className="text-red-500 text-sm">{error}</p>
          <button
            onClick={() => window.location.reload()}
            className="mt-3 px-4 py-1.5 text-xs bg-brand-500 text-white rounded-lg hover:bg-brand-600"
          >
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
        <p className="text-xs text-gray-400 mt-0.5">持仓汇总 · 仓位建议 · 交易记录</p>
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
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-3 py-1.5 text-xs rounded-lg border transition-colors ${
              tab === t.key
                ? 'bg-brand-500 text-white border-brand-500'
                : 'bg-white text-gray-500 border-gray-200 hover:bg-gray-50'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* 持仓列表 */}
      {tab === 'positions' && (
        <div className="card overflow-hidden">
          {items.map(item => (
            <PositionItem
              key={item.id}
              item={item}
              expanded={expandedId === item.id}
              onToggle={() => toggleExpand(item.id)}
              signal={signals[item.fund_code]}
              onExecute={() => handleExecute(item)}
            />
          ))}
        </div>
      )}

      {/* 历史建议 */}
      {tab === 'advice' && (
        <div className="card p-4 space-y-2">
          {advice.length === 0 ? (
            <p className="text-gray-400 text-xs text-center py-4">暂无历史建议</p>
          ) : (
            advice.map((a: any, i: number) => (
              <div key={i} className="flex items-center gap-3 text-sm border-b border-gray-50 pb-2">
                <span className="text-[10px] text-gray-400 w-20">{a.date}</span>
                <span className="font-mono text-xs">{a.fund_code}</span>
                <span className={`text-[10px] px-1.5 py-0.5 rounded ${
                  a.signal_level === 'S+' ? 'bg-signal-sp/20 text-signal-sp' :
                  a.signal_level === 'S'  ? 'bg-signal-s/20 text-signal-s'  :
                                                   'bg-signal-b/20 text-signal-b'
                }`}>{a.signal_level}</span>
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
            <p className="text-gray-400 text-xs text-center py-4">暂无交易记录</p>
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
