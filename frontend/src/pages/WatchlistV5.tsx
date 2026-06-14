/**
 * WatchlistV5 - V5.0 自选页
 * 自适应网格小卡片 + 点击展开详情（非跳转）
 */
import { useState, useCallback, useEffect } from 'react';
import type { WatchlistItem, SignalLevel } from '../../types';
import { Star, Trash2, ChevronDown, ChevronUp, TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { clsx } from 'clsx';
import { fetchWatchlistV5, removeWatchlistV5 } from '../api/watchlistV5';
import { fetchV5Sentiment } from '../api/marketV5';

/* ============================================================
   子组件
   ============================================================ */

/** 涨跌文本 class（A股：红涨绿跌） */
function returnCls(v: number): string {
  if (v > 0) return 'text-red-500';
  if (v < 0) return 'text-green-500';
  return 'text-gray-400';
}

/** 小卡片（折叠态） */
function FundCard({
  item,
  signal,
  expanded,
  onToggle,
  onRemove,
}: {
  item: WatchlistItem;
  signal: { signalLevel: SignalLevel; confidenceStars: number } | undefined;
  expanded: boolean;
  onToggle: () => void;
  onRemove: () => void;
}) {
  const fundShortName = (item as any).fund_short_name || item.fund_name;

  return (
    <div
      onClick={onToggle}
      className="card p-3 cursor-pointer hover:shadow-md transition-shadow relative group"
    >
      {/* 删除按钮（悬停显示） */}
      <button
        onClick={(e) => { e.stopPropagation(); onRemove(); }}
        className="absolute top-1 right-1 p-0.5 rounded opacity-0 group-hover:opacity-100
                   hover:bg-red-50 text-gray-300 hover:text-red-500 transition-all"
      >
        <Trash2 className="w-3 h-3" />
      </button>

      <div className="flex items-center gap-2 mb-1.5">
        <span className="text-[10px] font-mono text-gray-400">{item.fund_code}</span>
        {signal && (
          <span
            className="text-[9px] px-1 py-0.5 rounded-full text-white"
            style={{ backgroundColor: signal.signalLevel === 'S+' ? '#059669' : signal.signalLevel === 'S' ? '#10B981' : signal.signalLevel === 'A' ? '#6EE7B7' : '#FBBF24' }}
          >
            {signal.signalLevel}
          </span>
        )}
      </div>

      <p className="text-xs font-medium text-gray-800 truncate">{fundShortName}</p>

      <div className="flex items-center gap-2 mt-1.5 text-[10px]">
        <span className={returnCls(item.daily_return)}>
          {item.daily_return >= 0 ? '+' : ''}{item.daily_return.toFixed(2)}%
        </span>
        <span className="text-gray-300">|</span>
        <span className={returnCls(item.month_return)}>
          月{item.month_return >= 0 ? '+' : ''}{item.month_return.toFixed(2)}%
        </span>
      </div>

      <div className="flex justify-center mt-1.5">
        {signal && [1, 2, 3, 4].map((s) => (
          <Star
            key={s}
            className={`w-2.5 h-2.5 ${s <= signal.confidenceStars ? 'text-yellow-400 fill-yellow-400' : 'text-gray-300'}`}
          />
        ))}
      </div>

      <div className="flex justify-center mt-1">
        {expanded ? <ChevronUp className="w-3 h-3 text-gray-400" /> : <ChevronDown className="w-3 h-3 text-gray-400" />}
      </div>
    </div>
  );
}

/** 展开详情（嵌入卡片下方） */
function FundCardExpanded({
  item,
  signal,
}: {
  item: WatchlistItem;
  signal: { signalLevel: SignalLevel; confidenceStars: number } | undefined;
}) {
  const fundShortName = (item as any).fund_short_name || item.fund_name;

  return (
    <div className="mt-2 p-3 bg-gray-50 rounded-lg space-y-2 text-xs animate-fadeIn">
      <h4 className="font-bold text-gray-700">基金详情</h4>
      <div className="grid grid-cols-2 gap-x-3 gap-y-1 text-[10px]">
        <div><span className="text-gray-400">基金名称</span><p className="font-medium text-gray-700">{item.fund_name}</p></div>
        <div><span className="text-gray-400">添加日期</span><p className="font-medium text-gray-700">{item.added_at}</p></div>
        <div><span className="text-gray-400">当前净值</span><p className="font-mono font-medium">{item.current_nav.toFixed(4)}</p></div>
        <div><span className="text-gray-400">周收益</span><p className={returnCls(item.week_return)}>{item.week_return >= 0 ? '+' : ''}{item.week_return.toFixed(2)}%</p></div>
      </div>
      {signal && (
        <div className="pt-1 border-t border-gray-100">
          <span className="text-gray-400">V5 信号：</span>
          <span className="font-medium" style={{ color: signal.signalLevel === 'S+' ? '#059669' : signal.signalLevel === 'S' ? '#10B981' : '#6EE7B7' }}>
            {signal.signalLevel}（{signal.confidenceStars}星置信度）
          </span>
        </div>
      )}
    </div>
  );
}

/* ============================================================
   主页面
   ============================================================ */
export default function WatchlistV5() {
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [signals, setSignals] = useState<Record<string, { signalLevel: SignalLevel; confidenceStars: number }>>({});
  const [expandedId, setExpandedId] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  /** 加载自选列表 + 信号 */
  useEffect(() => {
    let cancelled = false;
    const loadData = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await fetchWatchlistV5();
        if (cancelled) return;
        setItems(data);

        // 并行获取每只基金的V5信号
        const signalEntries = await Promise.all(
          data.map(async (item) => {
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
          setError(err?.message || '加载自选列表失败');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    loadData();
    return () => { cancelled = true; };
  }, []);

  const handleToggle = useCallback((id: number) => {
    setExpandedId((prev) => (prev === id ? null : id));
  }, []);

  const handleRemove = useCallback(async (id: number) => {
    try {
      await removeWatchlistV5(id);
      setItems((prev) => prev.filter((it) => it.id !== id));
    } catch (err: any) {
      // 删除失败时提示，不静默降级
      alert(err?.message || '删除自选失败，请重试');
    }
  }, []);

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto space-y-4">
        <div>
          <h1 className="text-xl font-bold text-gray-800">我的自选 V5.0</h1>
          <p className="text-xs text-gray-400 mt-0.5">点击卡片展开详情 · 悬停可删除</p>
        </div>
        <div className="card p-8 text-center">
          <div className="inline-block w-6 h-6 border-2 border-brand-500 border-t-transparent rounded-full animate-spin" />
          <p className="text-gray-400 text-sm mt-2">加载自选列表...</p>
        </div>
      </div>
    );
  }

  if (error) {
    return (
      <div className="max-w-4xl mx-auto space-y-4">
        <div>
          <h1 className="text-xl font-bold text-gray-800">我的自选 V5.0</h1>
          <p className="text-xs text-gray-400 mt-0.5">点击卡片展开详情 · 悬停可删除</p>
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
        <h1 className="text-xl font-bold text-gray-800">我的自选 V5.0</h1>
        <p className="text-xs text-gray-400 mt-0.5">点击卡片展开详情 · 悬停可删除</p>
      </div>

      {items.length === 0 ? (
        <div className="card p-8 text-center">
          <Star className="w-8 h-8 text-gray-300 mx-auto mb-2" />
          <p className="text-gray-400 text-sm">暂无自选基金</p>
          <p className="text-[10px] text-gray-300 mt-1">在基金查询页点击★添加自选</p>
        </div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
          {items.map((it) => (
            <div key={it.id}>
              <FundCard
                item={it}
                signal={signals[it.fund_code]}
                expanded={expandedId === it.id}
                onToggle={() => handleToggle(it.id)}
                onRemove={() => handleRemove(it.id)}
              />
              {expandedId === it.id && (
                <FundCardExpanded item={it} signal={signals[it.fund_code]} />
              )}
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
