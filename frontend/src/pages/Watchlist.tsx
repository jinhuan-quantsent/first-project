import { useState, useEffect, useCallback } from 'react';
import {
  fetchWatchlist,
  addWatchlistItem,
  deleteWatchlistItem,
} from '../api/watchlist';
import { searchFunds } from '../api/fund';
import type { WatchlistItem, FundSearchItem, SentimentLabel } from '../types';
import SentimentBadge from '../components/common/SentimentBadge';
import SignalLights from '../components/common/SignalLights';
import LoadingSpinner from '../components/common/LoadingSpinner';
import ErrorMessage from '../components/common/ErrorMessage';
import {
  Trash2,
  Star,
  Bell,
  Plus,
  Search,
  X,
  AlertTriangle,
  TrendingUp,
  TrendingDown,
  Minus,
} from 'lucide-react';
import { clsx } from 'clsx';

/* ================================================================
   Mock 数据
   ================================================================ */
function mockWatchlist(): WatchlistItem[] {
  return [
    { id: 1, fund_code: '000001', fund_name: '华夏成长混合', added_at: '2025-03-15', notes: '长期定投标的', alert_threshold: -5, sort_order: 1, current_nav: 1.2345, daily_return: 0.85, week_return: 1.23, month_return: -2.15 },
    { id: 2, fund_code: '000002', fund_name: '易方达消费行业股票', added_at: '2025-02-20', notes: '', alert_threshold: 0, sort_order: 2, current_nav: 3.8762, daily_return: -0.42, week_return: -1.05, month_return: 3.78 },
    { id: 3, fund_code: '000003', fund_name: '天弘沪深300ETF联接A', added_at: '2025-04-01', notes: '底仓配置', alert_threshold: -3, sort_order: 3, current_nav: 1.1056, daily_return: 0.23, week_return: 0.56, month_return: 1.34 },
    { id: 4, fund_code: '000004', fund_name: '招商中证白酒指数(LOF)A', added_at: '2025-01-10', notes: '波动较大注意仓位', alert_threshold: -8, sort_order: 4, current_nav: 1.5678, daily_return: 1.52, week_return: 3.21, month_return: -5.67 },
  ];
}

function mockSentiment(fundCode: string): {
  score: number;
  label: SentimentLabel;
  shortTerm: SentimentLabel;
  midTerm: SentimentLabel;
  longTerm: SentimentLabel;
  hasDivergence: boolean;
  divergenceType?: 'bullish' | 'bearish';
  factors: { name: string; score: number; label: SentimentLabel }[];
} {
  const hash = fundCode.split('').reduce((a, c) => a + c.charCodeAt(0), 0);
  const score = 20 + (hash % 65);
  const labels: SentimentLabel[] = ['extreme_fear', 'fear', 'neutral', 'greed', 'extreme_greed'];
  const labelIdx = Math.min(4, Math.floor(score / 20));

  return {
    score,
    label: labels[labelIdx],
    shortTerm: labels[Math.min(4, labelIdx)],
    midTerm: labels[Math.min(4, (labelIdx + 1) % 5)],
    longTerm: labels[Math.min(4, Math.max(0, labelIdx - 1))],
    hasDivergence: hash % 3 === 0,
    divergenceType: hash % 2 === 0 ? 'bullish' : 'bearish',
    factors: [
      { name: '波动率', score: 35 + (hash % 30), label: labels[Math.min(4, Math.floor((35 + (hash % 30)) / 20))] },
      { name: '成交量', score: 50 + (hash % 40), label: labels[Math.min(4, Math.floor((50 + (hash % 40)) / 20))] },
      { name: '动量', score: 45 + (hash % 35), label: labels[Math.min(4, Math.floor((45 + (hash % 35)) / 20))] },
      { name: '资金流', score: 55 + (hash % 25), label: labels[Math.min(4, Math.floor((55 + (hash % 25)) / 20))] },
    ],
  };
}

function mockSearchResults(keyword: string): FundSearchItem[] {
  const all: FundSearchItem[] = [
    { fund_code: '000001', fund_name: '华夏成长混合', fund_short_name: '华夏成长', fund_type: '混合型', nav: 1.2345, daily_return: 0.85, week_return: 1.23, month_return: -2.15, year_return: 12.8, fund_size: 89.5, risk_level: '中高风险' },
    { fund_code: '000005', fund_name: '广发稳健增长混合A', fund_short_name: '广发稳健', fund_type: '混合型', nav: 1.8932, daily_return: 0.12, week_return: 0.34, month_return: 1.89, year_return: 15.6, fund_size: 67.8, risk_level: '中风险' },
    { fund_code: '000007', fund_name: '富国天惠成长混合(LOF)A', fund_short_name: '富国天惠', fund_type: '混合型', nav: 2.3410, daily_return: 0.56, week_return: 1.78, month_return: 4.56, year_return: 18.9, fund_size: 112.6, risk_level: '中高风险' },
    { fund_code: '000009', fund_name: '嘉实新兴产业股票', fund_short_name: '嘉实新兴', fund_type: '股票型', nav: 2.1234, daily_return: 1.23, week_return: 2.45, month_return: 5.67, year_return: 25.4, fund_size: 78.3, risk_level: '高风险' },
    { fund_code: '000010', fund_name: '博时主题行业混合(LOF)', fund_short_name: '博时主题', fund_type: '混合型', nav: 1.6789, daily_return: 0.34, week_return: -0.56, month_return: 2.34, year_return: 10.2, fund_size: 134.5, risk_level: '中高风险' },
  ];

  if (!keyword.trim()) return [];
  const kw = keyword.toLowerCase().trim();
  return all.filter(
    (f) =>
      f.fund_code.includes(kw) ||
      f.fund_name.toLowerCase().includes(kw) ||
      f.fund_short_name.toLowerCase().includes(kw)
  );
}

/* ================================================================
   Tooltip 组件
   ================================================================ */
function SentimentTooltip({
  fundCode,
  fundName,
  children,
}: {
  fundCode: string;
  fundName: string;
  children: React.ReactNode;
}) {
  const [show, setShow] = useState(false);
  const s = mockSentiment(fundCode);

  return (
    <div
      className="relative inline-block"
      onMouseEnter={() => setShow(true)}
      onMouseLeave={() => setShow(false)}
    >
      {children}
      {show && (
        <div className="absolute z-50 left-1/2 -translate-x-1/2 bottom-full mb-2 w-64 bg-white rounded-xl shadow-lg border border-gray-200 p-3 pointer-events-none">
          <div className="text-xs font-bold text-gray-700 mb-2">{fundName}</div>
          <div className="space-y-1.5">
            {s.factors.map((f) => (
              <div key={f.name} className="flex items-center justify-between">
                <span className="text-xs text-gray-500">{f.name}</span>
                <div className="flex items-center gap-1.5">
                  <div className="w-16 h-1.5 bg-gray-200 rounded-full overflow-hidden">
                    <div
                      className="h-full rounded-full"
                      style={{
                        width: `${f.score}%`,
                        background:
                          f.label === 'extreme_fear'
                            ? 'var(--sentiment-extreme-fear)'
                            : f.label === 'fear'
                            ? 'var(--sentiment-fear)'
                            : f.label === 'neutral'
                            ? 'var(--sentiment-neutral)'
                            : f.label === 'greed'
                            ? 'var(--sentiment-greed)'
                            : 'var(--sentiment-extreme-greed)',
                      }}
                    />
                  </div>
                  <span className="text-xs font-mono text-gray-600 w-6 text-right">{f.score}</span>
                </div>
              </div>
            ))}
          </div>
          <div className="absolute left-1/2 -translate-x-1/2 bottom-0 translate-y-full">
            <div className="w-2 h-2 bg-white border-r border-b border-gray-200 rotate-45" />
          </div>
        </div>
      )}
    </div>
  );
}

/* ================================================================
   主组件
   ================================================================ */
export default function Watchlist() {
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<number | null>(null);

  // 添加自选
  const [showAddPanel, setShowAddPanel] = useState(false);
  const [searchKeyword, setSearchKeyword] = useState('');
  const [searchResults, setSearchResults] = useState<FundSearchItem[]>([]);
  const [searching, setSearching] = useState(false);
  const [adding, setAdding] = useState<string | null>(null);

  // 删除确认
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    fetchWatchlist()
      .then((data) => {
        setItems(data.items);
        setLoading(false);
      })
      .catch(() => {
        // Mock 兜底
        setItems(mockWatchlist());
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  // 搜索（用于添加自选）
  const handleAddSearch = useCallback(async () => {
    if (!searchKeyword.trim()) return;
    setSearching(true);
    try {
      const data = await searchFunds({ keyword: searchKeyword, page_size: 10 });
      setSearchResults(data.items);
    } catch {
      setSearchResults(mockSearchResults(searchKeyword));
    } finally {
      setSearching(false);
    }
  }, [searchKeyword]);

  // 添加自选
  const handleAdd = useCallback(
    async (fund: FundSearchItem) => {
      setAdding(fund.fund_code);
      try {
        await addWatchlistItem({ fund_code: fund.fund_code, fund_name: fund.fund_name });
        // 重新加载
        load();
        setShowAddPanel(false);
        setSearchKeyword('');
        setSearchResults([]);
      } catch {
        // Mock: 本地添加
        const newItem: WatchlistItem = {
          id: Date.now(),
          fund_code: fund.fund_code,
          fund_name: fund.fund_name,
          added_at: new Date().toISOString().slice(0, 10),
          notes: '',
          alert_threshold: 0,
          sort_order: items.length + 1,
          current_nav: fund.nav,
          daily_return: fund.daily_return,
          week_return: fund.week_return,
          month_return: fund.month_return,
        };
        setItems((prev) => [...prev, newItem]);
        setShowAddPanel(false);
        setSearchKeyword('');
        setSearchResults([]);
      } finally {
        setAdding(null);
      }
    },
    [load, items.length]
  );

  // 删除自选
  const handleDelete = useCallback(async (id: number) => {
    setDeleting(id);
    try {
      await deleteWatchlistItem(id);
      setItems((prev) => prev.filter((i) => i.id !== id));
    } catch {
      // Mock: 本地删除
      setItems((prev) => prev.filter((i) => i.id !== id));
    } finally {
      setDeleting(null);
      setConfirmDelete(null);
    }
  }, []);

  if (loading) return <LoadingSpinner text="加载自选列表..." />;
  if (error) return <ErrorMessage message={error} onRetry={load} />;

  return (
    <div className="max-w-4xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl md:text-2xl font-bold text-gray-800">我的自选</h1>
          <p className="text-xs md:text-sm text-gray-400 mt-1">跟踪关注的基金情绪变化</p>
        </div>
        <div className="flex items-center gap-3">
          <span className="text-xs text-gray-400">{items.length} 只基金</span>
          <button
            onClick={() => setShowAddPanel(!showAddPanel)}
            className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 text-white text-xs font-medium rounded-lg hover:bg-blue-700 transition-colors"
          >
            <Plus className="w-3.5 h-3.5" />
            添加自选
          </button>
        </div>
      </div>

      {/* ======== 添加自选面板 ======== */}
      {showAddPanel && (
        <div className="card p-4 animate-expand">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-bold text-gray-700">添加自选基金</h3>
            <button
              onClick={() => {
                setShowAddPanel(false);
                setSearchKeyword('');
                setSearchResults([]);
              }}
              className="p-1 text-gray-400 hover:text-gray-600"
            >
              <X className="w-4 h-4" />
            </button>
          </div>
          <div className="flex gap-2">
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" />
              <input
                type="text"
                value={searchKeyword}
                onChange={(e) => setSearchKeyword(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleAddSearch()}
                placeholder="搜索基金代码或名称..."
                className="w-full pl-9 pr-4 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <button
              onClick={handleAddSearch}
              disabled={searching}
              className="px-4 py-2 bg-blue-600 text-white text-xs rounded-lg hover:bg-blue-700 disabled:opacity-50"
            >
              {searching ? '搜索中...' : '搜索'}
            </button>
          </div>

          {searchResults.length > 0 && (
            <div className="mt-3 border border-gray-100 rounded-lg overflow-hidden max-h-64 overflow-y-auto">
              {searchResults.map((fund) => {
                const alreadyAdded = items.some((i) => i.fund_code === fund.fund_code);
                return (
                  <div
                    key={fund.fund_code}
                    className="flex items-center justify-between px-3 py-2.5 border-b border-gray-50 last:border-0 hover:bg-gray-50"
                  >
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-mono text-gray-400">{fund.fund_code}</span>
                        <span className="text-sm font-medium text-gray-700 truncate">
                          {fund.fund_short_name || fund.fund_name}
                        </span>
                        <span className="text-[10px] px-1 py-0.5 bg-gray-100 rounded text-gray-500">
                          {fund.fund_type}
                        </span>
                      </div>
                      <div className="flex items-center gap-3 mt-0.5 text-xs text-gray-400">
                        <span>净值 {fund.nav.toFixed(4)}</span>
                        <span className={fund.daily_return >= 0 ? 'text-red-400' : 'text-green-400'}>
                          日 {fund.daily_return >= 0 ? '+' : ''}
                          {fund.daily_return.toFixed(2)}%
                        </span>
                      </div>
                    </div>
                    <button
                      onClick={() => handleAdd(fund)}
                      disabled={alreadyAdded || adding === fund.fund_code}
                      className={clsx(
                        'ml-3 px-3 py-1 text-xs rounded-lg font-medium transition-colors shrink-0',
                        alreadyAdded
                          ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                          : 'bg-blue-50 text-blue-600 hover:bg-blue-100'
                      )}
                    >
                      {alreadyAdded ? '已添加' : adding === fund.fund_code ? '添加中...' : '添加'}
                    </button>
                  </div>
                );
              })}
            </div>
          )}
          {searchKeyword && !searching && searchResults.length === 0 && (
            <p className="mt-3 text-xs text-gray-400 text-center py-4">未找到相关基金</p>
          )}
        </div>
      )}

      {/* ======== 自选列表 ======== */}
      {items.length === 0 ? (
        <div className="card p-8 text-center">
          <Star className="w-10 h-10 text-gray-300 mx-auto mb-3" />
          <p className="text-gray-400">暂无自选基金</p>
          <p className="text-xs text-gray-300 mt-1">点击「添加自选」关注您感兴趣的基金</p>
        </div>
      ) : (
        <div className="space-y-3">
          {items.map((item) => {
            const s = mockSentiment(item.fund_code);
            return (
              <div
                key={item.id}
                className={clsx(
                  'card p-4 hover:shadow-md transition-all duration-200 group',
                  deleting === item.id && 'opacity-50'
                )}
              >
                <div className="flex items-start justify-between">
                  <div className="flex-1 min-w-0">
                    {/* 第一行：代码 + 名称 + 标签 */}
                    <div className="flex items-center gap-2 mb-1.5">
                      <span className="text-xs font-mono text-gray-400">{item.fund_code}</span>
                      <h3 className="font-medium text-gray-800 truncate">{item.fund_name}</h3>
                      {item.alert_threshold !== 0 && (
                        <span
                          className="flex items-center gap-0.5 text-[10px] px-1.5 py-0.5 bg-orange-50 text-orange-500 rounded"
                          title={`提醒阈值: ${item.alert_threshold}%`}
                        >
                          <Bell className="w-2.5 h-2.5" />
                          {item.alert_threshold}%
                        </span>
                      )}
                    </div>

                    {/* 备注 */}
                    {item.notes && (
                      <p className="text-xs text-gray-400 mb-2">{item.notes}</p>
                    )}

                    {/* 数据行 */}
                    <div className="flex flex-wrap items-center gap-x-5 gap-y-1 text-xs">
                      <span className="font-mono text-gray-500">净值: {item.current_nav.toFixed(4)}</span>
                      <span
                        className={clsx(
                          'font-mono',
                          item.daily_return >= 0 ? 'text-red-500' : 'text-green-500'
                        )}
                      >
                        日: {item.daily_return >= 0 ? '+' : ''}
                        {item.daily_return.toFixed(2)}%
                      </span>
                      <span
                        className={clsx(
                          'font-mono',
                          item.week_return >= 0 ? 'text-red-500' : 'text-green-500'
                        )}
                      >
                        周: {item.week_return >= 0 ? '+' : ''}
                        {item.week_return.toFixed(2)}%
                      </span>
                      <span
                        className={clsx(
                          'font-mono',
                          item.month_return >= 0 ? 'text-red-500' : 'text-green-500'
                        )}
                      >
                        月: {item.month_return >= 0 ? '+' : ''}
                        {item.month_return.toFixed(2)}%
                      </span>
                      <span className="text-gray-300">|</span>
                      <span className="text-gray-400 text-[10px]">
                        添加于 {item.added_at}
                      </span>
                    </div>

                    {/* 情绪信号行 */}
                    <div className="flex items-center gap-3 mt-2">
                      <SentimentTooltip fundCode={item.fund_code} fundName={item.fund_name}>
                        <div className="flex items-center gap-2 cursor-help">
                          <SentimentBadge sentiment={s.label} size="sm" />
                          <span className="text-xs font-bold text-gray-600">{s.score}分</span>
                        </div>
                      </SentimentTooltip>
                      <SignalLights
                        shortTerm={s.shortTerm}
                        midTerm={s.midTerm}
                        longTerm={s.longTerm}
                        hasDivergence={s.hasDivergence}
                        divergenceType={s.divergenceType}
                        size="sm"
                      />
                      {/* 趋势箭头 */}
                      <span
                        className={clsx(
                          'text-xs',
                          item.daily_return > 0.3
                            ? 'text-red-500'
                            : item.daily_return < -0.3
                            ? 'text-green-500'
                            : 'text-gray-400'
                        )}
                      >
                        {item.daily_return > 0.3 ? (
                          <TrendingUp className="w-3.5 h-3.5" />
                        ) : item.daily_return < -0.3 ? (
                          <TrendingDown className="w-3.5 h-3.5" />
                        ) : (
                          <Minus className="w-3.5 h-3.5" />
                        )}
                      </span>
                    </div>
                  </div>

                  {/* 删除按钮 */}
                  <div className="ml-3 shrink-0">
                    {confirmDelete === item.id ? (
                      <div className="flex items-center gap-1">
                        <button
                          onClick={() => handleDelete(item.id)}
                          disabled={deleting === item.id}
                          className="px-2 py-1 text-[10px] bg-red-500 text-white rounded hover:bg-red-600 transition-colors"
                        >
                          确认
                        </button>
                        <button
                          onClick={() => setConfirmDelete(null)}
                          className="px-2 py-1 text-[10px] bg-gray-200 text-gray-600 rounded hover:bg-gray-300 transition-colors"
                        >
                          取消
                        </button>
                      </div>
                    ) : (
                      <button
                        onClick={() => setConfirmDelete(item.id)}
                        className="p-1.5 text-gray-400 hover:text-red-500 transition-colors opacity-0 group-hover:opacity-100"
                        title="删除自选"
                      >
                        <Trash2 className="w-4 h-4" />
                      </button>
                    )}
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      )}

      <style>{`
        @keyframes expandDetail {
          from { opacity: 0; max-height: 0; transform: translateY(-8px); }
          to   { opacity: 1; max-height: 2000px; transform: translateY(0); }
        }
        .animate-expand {
          animation: expandDetail 200ms ease-out;
        }
      `}</style>
    </div>
  );
}
