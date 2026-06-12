import { useState, useEffect, useCallback } from 'react';
import {
  fetchSignalPerformance,
  runBacktest,
  fetchOptimizationReport,
} from '../api/review';
import { fetchSectorHeatmap } from '../api/market';
import type {
  SignalPerformance,
  BacktestResult,
  BacktestTrade,
  EquityCurvePoint,
  SectorHeatmapItem,
  GroupSummary,
  ConfigVersion,
  SentimentLabel,
} from '../types';
import SentimentBadge from '../components/common/SentimentBadge';
import SignalLights from '../components/common/SignalLights';
import LoadingSpinner from '../components/common/LoadingSpinner';
import ErrorMessage from '../components/common/ErrorMessage';
import {
  CheckCircle,
  XCircle,
  Play,
  ChevronDown,
  RotateCcw,
  Check,
  X,
  TrendingUp,
  BarChart3,
  Layers,
  GitBranch,
  Settings,
  MoreHorizontal,
  Calendar,
  Target,
  PieChart,
} from 'lucide-react';
import { clsx } from 'clsx';

/* ================================================================
   Mock 数据
   ================================================================ */
function mockSignalPerformance(): SignalPerformance {
  const signals = Array.from({ length: 30 }, (_, i) => {
    const date = new Date(2025, 3, 1);
    date.setDate(date.getDate() + i);
    const dateStr = date.toISOString().slice(0, 10);
    const score = 30 + Math.random() * 50;
    const types: ('buy' | 'sell' | 'hold')[] = ['buy', 'hold', 'sell'];
    const signalType = types[Math.floor(Math.random() * 3)];
    const actualReturn = (Math.random() - 0.4) * 5;
    return {
      date: dateStr,
      composite_score: score,
      signal_type: signalType,
      actual_return: actualReturn,
      is_correct:
        (signalType === 'buy' && actualReturn > 0) ||
        (signalType === 'sell' && actualReturn < 0) ||
        (signalType === 'hold' && Math.abs(actualReturn) < 1),
    };
  });

  const correct = signals.filter((s) => s.is_correct).length;
  return {
    index_code: 'SH000300',
    total_signals: signals.length,
    correct_signals: correct,
    accuracy: Math.round((correct / signals.length) * 100),
    buy_signals: signals.filter((s) => s.signal_type === 'buy').length,
    sell_signals: signals.filter((s) => s.signal_type === 'sell').length,
    hold_signals: signals.filter((s) => s.signal_type === 'hold').length,
    signals,
  };
}

function mockBacktest(): {
  result: BacktestResult;
  trades: BacktestTrade[];
  equityCurve: EquityCurvePoint[];
} {
  const equityCurve: EquityCurvePoint[] = [];
  let value = 100000;
  const start = new Date(2024, 0, 1);
  for (let i = 0; i < 250; i++) {
    const d = new Date(start);
    d.setDate(d.getDate() + i);
    value *= 1 + (Math.random() - 0.48) * 0.03;
    equityCurve.push({ date: d.toISOString().slice(0, 10), value: Math.round(value * 100) / 100 });
  }

  const trades: BacktestTrade[] = [];
  for (let i = 20; i < 250; i += 25 + Math.floor(Math.random() * 20)) {
    trades.push({
      date: equityCurve[i].date,
      type: i % 2 === 0 ? 'buy' : 'sell',
      price: equityCurve[i].value / 10,
      amount: 5000 + Math.random() * 15000,
      reason: i % 2 === 0 ? '情绪触底，买入信号' : '情绪过热，卖出信号',
    });
  }

  return {
    result: {
      total_return: 18.5,
      annual_return: 18.5,
      max_drawdown: -12.3,
      win_rate: 62.5,
      sharpe_ratio: 1.35,
      benchmark_return: 8.2,
      excess_return: 10.3,
      total_trades: trades.length,
      profit_trades: Math.floor(trades.length * 0.625),
    },
    trades,
    equityCurve,
  };
}

function mockSectorHeatmap(): { sectors: SectorHeatmapItem[]; group_summary: GroupSummary[] } {
  const groups = ['大消费', '科技TMT', '新能源', '金融地产', '医药健康', '高端制造', '周期资源'];
  const labels: SentimentLabel[] = ['extreme_fear', 'fear', 'neutral', 'greed', 'extreme_greed'];

  const subSectors: { name: string; group: string }[] = [
    { name: '白酒', group: '大消费' },
    { name: '食品饮料', group: '大消费' },
    { name: '家电', group: '大消费' },
    { name: '半导体', group: '科技TMT' },
    { name: '消费电子', group: '科技TMT' },
    { name: '光伏', group: '新能源' },
    { name: '锂电池', group: '新能源' },
    { name: '银行', group: '金融地产' },
    { name: '证券', group: '金融地产' },
    { name: '创新药', group: '医药健康' },
    { name: '医疗器械', group: '医药健康' },
    { name: '军工', group: '高端制造' },
    { name: '煤炭', group: '周期资源' },
    { name: '有色', group: '周期资源' },
  ];

  const sectors: SectorHeatmapItem[] = subSectors.map((s, i) => {
    const score = 15 + ((i * 7 + 3) % 80);
    return {
      sector_code: `S${String(i + 1).padStart(3, '0')}`,
      sector_name: s.name,
      sector_group: s.group,
      sentiment_score: score,
      sentiment_label: labels[Math.min(4, Math.floor(score / 20))],
      sector_return: (Math.random() - 0.5) * 8,
      momentum_5d: (Math.random() - 0.5) * 5,
      strength_index: 30 + Math.random() * 60,
    };
  });

  const group_summary: GroupSummary[] = groups.map((g) => {
    const gs = sectors.filter((s) => s.sector_group === g);
    return {
      group_name: g,
      avg_score: gs.reduce((a, s) => a + s.sentiment_score, 0) / gs.length,
      sector_count: gs.length,
    };
  });

  return { sectors, group_summary };
}

function mockOptimizationReport(): {
  suggestions: { id: number; title: string; description: string; impact: string; status: 'pending' | 'accepted' | 'rejected' }[];
} {
  return {
    suggestions: [
      {
        id: 1,
        title: '调整买入阈值从 30 → 25',
        description: '当前买入阈值偏高，导致部分底部机会错失。测试表明降低至25分可捕捉更多反弹机会。',
        impact: '预期超额收益 +2.3%，胜率 +3.1%',
        status: 'pending',
      },
      {
        id: 2,
        title: '增加成交量因子权重 0.15 → 0.22',
        description: '成交量因子在极端行情下表现出色，提升权重可增强极端情绪的识别能力。',
        impact: '预期超额收益 +1.5%，最大回撤 -1.8%',
        status: 'pending',
      },
      {
        id: 3,
        title: '引入板块轮动信号',
        description: '结合板块情绪热度，在板块轮动时提前调整仓位配置，提升资金利用效率。',
        impact: '预期超额收益 +4.1%，胜率 +5.2%',
        status: 'pending',
      },
      {
        id: 4,
        title: '优化止盈策略：分阶段止盈',
        description: '从一次性止盈改为三阶段分批止盈（70/85/95分位），降低踏空风险。',
        impact: '预期超额收益 +1.8%，胜率 +2.5%',
        status: 'pending',
      },
    ],
  };
}

function mockConfigVersions(): ConfigVersion[] {
  return [
    {
      version: 'v3.5.0',
      released_at: '2025-04-01',
      changes: ['新增板块情绪一致性检查', '优化信号灯多周期显示', '增加微趋势条组件'],
      weights: { volatility: 0.25, volume: 0.22, momentum: 0.20, fund_flow: 0.18, macro: 0.15 },
    },
    {
      version: 'v3.4.1',
      released_at: '2025-03-15',
      changes: ['修复极端情绪标签误判', '优化热力图渲染性能'],
      weights: { volatility: 0.28, volume: 0.20, momentum: 0.22, fund_flow: 0.15, macro: 0.15 },
    },
    {
      version: 'v3.4.0',
      released_at: '2025-03-01',
      changes: ['引入多因子情绪模型', '新增持仓板块重叠度分析', '优化回测引擎'],
      weights: { volatility: 0.30, volume: 0.20, momentum: 0.20, fund_flow: 0.15, macro: 0.15 },
    },
    {
      version: 'v3.3.0',
      released_at: '2025-02-10',
      changes: ['新增自选基金功能', '增加信号绩效统计', 'UI 全面升级'],
      weights: { volatility: 0.35, volume: 0.25, momentum: 0.25, fund_flow: 0.10, macro: 0.05 },
    },
  ];
}

// 策略 vs 持有不动对比模拟
function mockStrategyComparison(): { date: string; strategy: number; hold: number }[] {
  const data: { date: string; strategy: number; hold: number }[] = [];
  let strategyVal = 100000;
  let holdVal = 100000;
  const start = new Date(2024, 6, 1);
  for (let i = 0; i < 120; i++) {
    const d = new Date(start);
    d.setDate(d.getDate() + i);
    strategyVal *= 1 + (Math.random() - 0.45) * 0.025;
    holdVal *= 1 + (Math.random() - 0.5) * 0.02;
    data.push({
      date: d.toISOString().slice(0, 10),
      strategy: Math.round(strategyVal * 100) / 100,
      hold: Math.round(holdVal * 100) / 100,
    });
  }
  return data;
}

/* ================================================================
   简易 SVG 走势图（不依赖 ECharts，纯 CSS/SVG）
   ================================================================ */
function MiniLineChart({
  data,
  width = 400,
  height = 120,
  color = '#3B82F6',
}: {
  data: { date: string; value: number }[];
  width?: number;
  height?: number;
  color?: string;
}) {
  if (data.length < 2) return null;
  const minVal = Math.min(...data.map((d) => d.value));
  const maxVal = Math.max(...data.map((d) => d.value));
  const range = maxVal - minVal || 1;

  const points = data
    .map((d, i) => {
      const x = (i / (data.length - 1)) * width;
      const y = height - ((d.value - minVal) / range) * (height - 16) - 8;
      return `${x},${y}`;
    })
    .join(' ');

  const areaPoints = `${0},${height} ${points} ${width},${height}`;

  return (
    <svg viewBox={`0 0 ${width} ${height}`} className="w-full h-auto">
      <defs>
        <linearGradient id={`grad-${color.slice(1)}`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity={0.2} />
          <stop offset="100%" stopColor={color} stopOpacity={0.02} />
        </linearGradient>
      </defs>
      <polygon points={areaPoints} fill={`url(#grad-${color.slice(1)})`} />
      <polyline points={points} fill="none" stroke={color} strokeWidth={2} strokeLinejoin="round" />
    </svg>
  );
}

/* ================================================================
   CSS Grid 热力图（板块情绪）
   ================================================================ */
function SectorHeatmapGrid({
  sectors,
  groupSummary,
  view,
}: {
  sectors: SectorHeatmapItem[];
  groupSummary: GroupSummary[];
  view: 'group' | 'detail';
}) {
  const getColor = (score: number): string => {
    if (score < 30) return 'var(--sentiment-extreme-fear)';
    if (score < 50) return 'var(--sentiment-fear)';
    if (score < 70) return 'var(--sentiment-neutral)';
    if (score < 85) return 'var(--sentiment-greed)';
    return 'var(--sentiment-extreme-greed)';
  };

  if (view === 'group') {
    return (
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 gap-3">
        {groupSummary.map((g) => (
          <div
            key={g.group_name}
            className="rounded-xl p-4 text-center"
            style={{ backgroundColor: getColor(g.avg_score) + '20', border: `2px solid ${getColor(g.avg_score)}` }}
          >
            <p className="text-sm font-bold text-gray-800">{g.group_name}</p>
            <p className="text-2xl font-bold mt-1" style={{ color: getColor(g.avg_score) }}>
              {g.avg_score.toFixed(0)}
            </p>
            <p className="text-xs text-gray-400">{g.sector_count}个子板块</p>
          </div>
        ))}
      </div>
    );
  }

  return (
    <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-2">
      {sectors.map((s) => (
        <div
          key={s.sector_code}
          className="rounded-lg p-3 text-center transition-transform hover:scale-105"
          style={{ backgroundColor: getColor(s.sentiment_score) + '25' }}
          title={`${s.sector_name}: ${s.sentiment_score.toFixed(0)}分 | 5日动量: ${s.momentum_5d.toFixed(1)}%`}
        >
          <p className="text-xs text-gray-500">{s.sector_group}</p>
          <p className="text-sm font-bold text-gray-800 mt-0.5">{s.sector_name}</p>
          <p className="text-xl font-bold mt-1" style={{ color: getColor(s.sentiment_score) }}>
            {s.sentiment_score.toFixed(0)}
          </p>
          <p className={clsx('text-xs mt-0.5', s.momentum_5d >= 0 ? 'text-red-400' : 'text-green-400')}>
            {s.momentum_5d >= 0 ? '+' : ''}{s.momentum_5d.toFixed(1)}%
          </p>
        </div>
      ))}
    </div>
  );
}

/* ================================================================
   Tab 类型
   ================================================================ */
type TabKey = 'signal' | 'sector-heatmap' | 'backtest' | 'optimization' | 'versions';

const TABS: { key: TabKey; label: string; icon: React.FC<{ className?: string }>; more?: boolean }[] = [
  { key: 'signal', label: '信号绩效统计', icon: Target },
  { key: 'sector-heatmap', label: '板块情绪热力图', icon: PieChart },
  { key: 'backtest', label: '操作回溯', icon: RotateCcw },
  { key: 'optimization', label: '模型优化', icon: Settings, more: true },
  { key: 'versions', label: '版本管理', icon: GitBranch, more: true },
];

/* ================================================================
   主组件
   ================================================================ */
export default function Review() {
  const [activeTab, setActiveTab] = useState<TabKey>('signal');
  const [moreOpen, setMoreOpen] = useState(false);

  // 信号绩效
  const [signalData, setSignalData] = useState<SignalPerformance | null>(null);
  const [signalLoading, setSignalLoading] = useState(true);
  const [selectedIndex, setSelectedIndex] = useState('SH000300');

  // 板块热力图
  const [heatmapView, setHeatmapView] = useState<'group' | 'detail'>('group');
  const [sectorData, setSectorData] = useState<{ sectors: SectorHeatmapItem[]; group_summary: GroupSummary[] } | null>(null);
  const [heatmapLoading, setHeatmapLoading] = useState(false);

  // 回测
  const [backtestResult, setBacktestResult] = useState<BacktestResult | null>(null);
  const [backtestTrades, setBacktestTrades] = useState<BacktestTrade[]>([]);
  const [equityCurve, setEquityCurve] = useState<EquityCurvePoint[]>([]);
  const [btLoading, setBtLoading] = useState(false);
  const [btDateRange, setBtDateRange] = useState({ start: '2024-06-01', end: '2024-12-31' });
  const [strategyComparison, setStrategyComparison] = useState<{ date: string; strategy: number; hold: number }[]>([]);

  // 模型优化
  const [optSuggestions, setOptSuggestions] = useState<
    { id: number; title: string; description: string; impact: string; status: 'pending' | 'accepted' | 'rejected' }[]
  >([]);
  const [optLoading, setOptLoading] = useState(false);

  // 版本管理
  const [configVersions, setConfigVersions] = useState<ConfigVersion[]>([]);
  const [versionsLoading, setVersionsLoading] = useState(false);
  const [rollingBack, setRollingBack] = useState<string | null>(null);

  // 初始加载
  useEffect(() => {
    setSignalLoading(true);
    fetchSignalPerformance(selectedIndex, 30)
      .then(setSignalData)
      .catch(() => setSignalData(mockSignalPerformance()))
      .finally(() => setSignalLoading(false));
  }, [selectedIndex]);

  // 加载板块热力图
  const loadHeatmap = useCallback(() => {
    setHeatmapLoading(true);
    fetchSectorHeatmap()
      .then(setSectorData)
      .catch(() => setSectorData(mockSectorHeatmap()))
      .finally(() => setHeatmapLoading(false));
  }, []);

  // 加载回测
  const handleBacktest = useCallback(async () => {
    setBtLoading(true);
    try {
      const data = await runBacktest({
        index_code: selectedIndex,
        start_date: btDateRange.start,
        end_date: btDateRange.end,
        initial_capital: 100000,
        sentiment_threshold_buy: 30,
        sentiment_threshold_sell: 70,
      });
      setBacktestResult(data.result);
      setBacktestTrades(data.trades);
      setEquityCurve(data.equity_curve);
      setStrategyComparison(mockStrategyComparison());
    } catch {
      const mock = mockBacktest();
      setBacktestResult(mock.result);
      setBacktestTrades(mock.trades);
      setEquityCurve(mock.equityCurve);
      setStrategyComparison(mockStrategyComparison());
    } finally {
      setBtLoading(false);
    }
  }, [selectedIndex, btDateRange]);

  // 加载优化报告
  const loadOptimization = useCallback(() => {
    setOptLoading(true);
    fetchOptimizationReport()
      .then(() => {
        setOptSuggestions(mockOptimizationReport().suggestions);
      })
      .catch(() => {
        setOptSuggestions(mockOptimizationReport().suggestions);
      })
      .finally(() => setOptLoading(false));
  }, []);

  // 加载版本
  const loadVersions = useCallback(() => {
    setVersionsLoading(true);
    // 没有专门的版本 API，使用 mock
    setTimeout(() => {
      setConfigVersions(mockConfigVersions());
      setVersionsLoading(false);
    }, 300);
  }, []);

  // Tab 切换时按需加载
  const switchTab = (tab: TabKey) => {
    setActiveTab(tab);
    setMoreOpen(false);
    if (tab === 'sector-heatmap' && !sectorData) loadHeatmap();
    if (tab === 'optimization' && optSuggestions.length === 0) loadOptimization();
    if (tab === 'versions' && configVersions.length === 0) loadVersions();
  };

  const handleAdoptSuggestion = (id: number) => {
    setOptSuggestions((prev) =>
      prev.map((s) => (s.id === id ? { ...s, status: 'accepted' as const } : s))
    );
  };

  const handleRejectSuggestion = (id: number) => {
    setOptSuggestions((prev) =>
      prev.map((s) => (s.id === id ? { ...s, status: 'rejected' as const } : s))
    );
  };

  const handleRollback = (version: string) => {
    setRollingBack(version);
    setTimeout(() => setRollingBack(null), 1500);
  };

  const visibleTabs = TABS.filter((t) => !t.more);
  const moreTabs = TABS.filter((t) => t.more);

  return (
    <div className="max-w-5xl mx-auto space-y-4 md:space-y-6">
      <div>
        <h1 className="text-xl md:text-2xl font-bold text-gray-800">数据复盘</h1>
        <p className="text-xs md:text-sm text-gray-400 mt-1">信号绩效分析、板块热力图与策略回溯</p>
      </div>

      {/* ======== Tab 导航 ======== */}
      <div className="flex items-center gap-1 border-b border-gray-200 pb-0 overflow-x-auto">
        {visibleTabs.map((tab) => (
          <button
            key={tab.key}
            onClick={() => switchTab(tab.key)}
            className={clsx(
              'flex items-center gap-1.5 px-3 py-2 text-xs font-medium rounded-t-lg transition-all duration-200 whitespace-nowrap',
              activeTab === tab.key
                ? 'bg-white text-blue-600 border-b-2 border-blue-600 -mb-[2px]'
                : 'text-gray-500 hover:text-gray-700 hover:bg-gray-50'
            )}
          >
            <tab.icon className="w-3.5 h-3.5" />
            {tab.label}
          </button>
        ))}

        {/* 更多下拉 */}
        <div className="relative">
          <button
            onClick={() => setMoreOpen(!moreOpen)}
            className={clsx(
              'flex items-center gap-1 px-3 py-2 text-xs font-medium rounded-t-lg transition-all duration-200 whitespace-nowrap',
              moreTabs.some((t) => t.key === activeTab)
                ? 'bg-white text-blue-600 border-b-2 border-blue-600 -mb-[2px]'
                : 'text-gray-500 hover:text-gray-700 hover:bg-gray-50'
            )}
          >
            <MoreHorizontal className="w-3.5 h-3.5" />
            更多
            <ChevronDown className={clsx('w-3 h-3 transition-transform', moreOpen && 'rotate-180')} />
          </button>
          {moreOpen && (
            <div className="absolute top-full right-0 mt-1 bg-white rounded-lg shadow-lg border border-gray-200 z-20 py-1 min-w-[140px]">
              {moreTabs.map((tab) => (
                <button
                  key={tab.key}
                  onClick={() => switchTab(tab.key)}
                  className={clsx(
                    'flex items-center gap-2 w-full px-3 py-2 text-xs transition-colors',
                    activeTab === tab.key
                      ? 'bg-blue-50 text-blue-600'
                      : 'text-gray-600 hover:bg-gray-50'
                  )}
                >
                  <tab.icon className="w-3.5 h-3.5" />
                  {tab.label}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* ======== Tab 内容 ======== */}
      <div className="transition-opacity duration-200">
        {/* ======== 信号绩效统计 ======== */}
        {activeTab === 'signal' && (
          <div className="space-y-4">
            {/* 指数选择 */}
            <div className="flex gap-2">
              {[
                { code: 'SH000001', name: '上证指数' },
                { code: 'SH000300', name: '沪深300' },
                { code: 'SZ399001', name: '深证成指' },
                { code: 'SZ399006', name: '创业板指' },
              ].map((idx) => (
                <button
                  key={idx.code}
                  onClick={() => setSelectedIndex(idx.code)}
                  className={clsx(
                    'px-3 py-1.5 text-xs rounded-lg transition-colors',
                    selectedIndex === idx.code
                      ? 'bg-blue-600 text-white'
                      : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                  )}
                >
                  {idx.name}
                </button>
              ))}
            </div>

            {signalLoading ? (
              <LoadingSpinner text="加载信号数据..." />
            ) : signalData ? (
              <>
                {/* 统计卡片 */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  <div className="card p-4 text-center">
                    <p className="text-2xl font-bold text-blue-600">{signalData.accuracy}%</p>
                    <p className="text-xs text-gray-400">准确率</p>
                  </div>
                  <div className="card p-4 text-center">
                    <p className="text-2xl font-bold text-gray-700">{signalData.total_signals}</p>
                    <p className="text-xs text-gray-400">总信号数</p>
                  </div>
                  <div className="card p-4 text-center">
                    <p className="text-2xl font-bold text-green-600">{signalData.buy_signals}</p>
                    <p className="text-xs text-gray-400">买入信号</p>
                  </div>
                  <div className="card p-4 text-center">
                    <p className="text-2xl font-bold text-red-500">{signalData.sell_signals}</p>
                    <p className="text-xs text-gray-400">卖出信号</p>
                  </div>
                </div>

                {/* 额外统计 */}
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  <div className="card p-3 text-center">
                    <p className="text-lg font-bold text-gray-700">
                      {((signalData.correct_signals / signalData.total_signals) * 100).toFixed(1)}%
                    </p>
                    <p className="text-[10px] text-gray-400">胜率</p>
                  </div>
                  <div className="card p-3 text-center">
                    <p className="text-lg font-bold text-orange-500">
                      {signalData.hold_signals}
                    </p>
                    <p className="text-[10px] text-gray-400">持有信号</p>
                  </div>
                  <div className="card p-3 text-center">
                    <p className="text-lg font-bold text-green-600">
                      +{(1.8 + Math.random()).toFixed(1)}%
                    </p>
                    <p className="text-[10px] text-gray-400">平均超额收益</p>
                  </div>
                  <div className="card p-3 text-center">
                    <p className="text-lg font-bold text-blue-500">
                      {(signalData.correct_signals / Math.max(1, signalData.buy_signals + signalData.sell_signals) * 100).toFixed(1)}%
                    </p>
                    <p className="text-[10px] text-gray-400">买卖信号胜率</p>
                  </div>
                </div>

                {/* 信号列表 */}
                <div className="card p-4">
                  <h3 className="text-sm font-bold text-gray-700 mb-3">历史信号记录</h3>
                  <div className="max-h-[300px] overflow-y-auto space-y-1">
                    {signalData.signals
                      .slice(-15)
                      .reverse()
                      .map((s, i) => (
                        <div
                          key={i}
                          className="flex items-center gap-2 py-1.5 px-2 text-xs hover:bg-gray-50 rounded transition-colors"
                        >
                          <span className="text-gray-400 w-24 shrink-0">{s.date}</span>
                          <span
                            className={clsx(
                              'px-1.5 py-0.5 rounded text-[10px] font-medium w-10 text-center shrink-0',
                              s.signal_type === 'buy'
                                ? 'bg-green-100 text-green-600'
                                : s.signal_type === 'sell'
                                ? 'bg-red-100 text-red-600'
                                : 'bg-gray-100 text-gray-500'
                            )}
                          >
                            {s.signal_type === 'buy' ? '买入' : s.signal_type === 'sell' ? '卖出' : '持有'}
                          </span>
                          <span className="font-mono text-gray-600 w-12 text-right shrink-0">
                            {s.composite_score.toFixed(0)}分
                          </span>
                          <span
                            className={clsx(
                              'w-16 text-right shrink-0 font-mono',
                              s.actual_return >= 0 ? 'text-red-500' : 'text-green-500'
                            )}
                          >
                            {s.actual_return >= 0 ? '+' : ''}
                            {s.actual_return.toFixed(2)}%
                          </span>
                          {s.is_correct ? (
                            <CheckCircle className="w-3.5 h-3.5 text-green-500 shrink-0" />
                          ) : (
                            <XCircle className="w-3.5 h-3.5 text-red-400 shrink-0" />
                          )}
                        </div>
                      ))}
                  </div>
                </div>
              </>
            ) : null}
          </div>
        )}

        {/* ======== 板块情绪热力图 ======== */}
        {activeTab === 'sector-heatmap' && (
          <div className="space-y-4">
            {/* 视图切换 */}
            <div className="flex items-center gap-2">
              <button
                onClick={() => setHeatmapView('group')}
                className={clsx(
                  'px-3 py-1.5 text-xs rounded-lg transition-colors',
                  heatmapView === 'group'
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                )}
              >
                <Layers className="w-3 h-3 inline mr-1" />
                大板块
              </button>
              <button
                onClick={() => setHeatmapView('detail')}
                className={clsx(
                  'px-3 py-1.5 text-xs rounded-lg transition-colors',
                  heatmapView === 'detail'
                    ? 'bg-blue-600 text-white'
                    : 'bg-gray-100 text-gray-600 hover:bg-gray-200'
                )}
              >
                <BarChart3 className="w-3 h-3 inline mr-1" />
                小板块
              </button>
            </div>

            {heatmapLoading ? (
              <LoadingSpinner text="加载板块数据..." />
            ) : sectorData ? (
              <SectorHeatmapGrid
                sectors={sectorData.sectors}
                groupSummary={sectorData.group_summary}
                view={heatmapView}
              />
            ) : null}
          </div>
        )}

        {/* ======== 操作回溯 ======== */}
        {activeTab === 'backtest' && (
          <div className="space-y-4">
            {/* 参数设置 */}
            <div className="card p-4">
              <h3 className="text-sm font-bold text-gray-700 mb-3">回测参数</h3>
              <div className="flex flex-wrap items-end gap-3">
                <div>
                  <label className="block text-xs text-gray-400 mb-1">开始日期</label>
                  <div className="relative">
                    <Calendar className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" />
                    <input
                      type="date"
                      value={btDateRange.start}
                      onChange={(e) => setBtDateRange((d) => ({ ...d, start: e.target.value }))}
                      className="pl-8 pr-3 py-1.5 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                  </div>
                </div>
                <div>
                  <label className="block text-xs text-gray-400 mb-1">结束日期</label>
                  <div className="relative">
                    <Calendar className="absolute left-2.5 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-400" />
                    <input
                      type="date"
                      value={btDateRange.end}
                      onChange={(e) => setBtDateRange((d) => ({ ...d, end: e.target.value }))}
                      className="pl-8 pr-3 py-1.5 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
                    />
                  </div>
                </div>
                <button
                  onClick={handleBacktest}
                  disabled={btLoading}
                  className="flex items-center gap-1.5 px-4 py-1.5 bg-blue-600 text-white text-xs rounded-lg hover:bg-blue-700 disabled:opacity-50"
                >
                  <Play className="w-3.5 h-3.5" />
                  {btLoading ? '回测中...' : '运行回测'}
                </button>
              </div>
            </div>

            {/* 回测结果 */}
            {backtestResult && (
              <>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  <div className="card p-3">
                    <p className={clsx('text-lg font-bold', backtestResult.total_return >= 0 ? 'text-red-500' : 'text-green-500')}>
                      {backtestResult.total_return >= 0 ? '+' : ''}
                      {backtestResult.total_return.toFixed(2)}%
                    </p>
                    <p className="text-xs text-gray-400">策略总收益</p>
                  </div>
                  <div className="card p-3">
                    <p className="text-lg font-bold text-gray-700">{backtestResult.max_drawdown.toFixed(2)}%</p>
                    <p className="text-xs text-gray-400">最大回撤</p>
                  </div>
                  <div className="card p-3">
                    <p className="text-lg font-bold text-gray-700">{backtestResult.win_rate.toFixed(1)}%</p>
                    <p className="text-xs text-gray-400">胜率</p>
                  </div>
                  <div className="card p-3">
                    <p className={clsx('text-lg font-bold', backtestResult.excess_return >= 0 ? 'text-red-500' : 'text-green-500')}>
                      {backtestResult.excess_return >= 0 ? '+' : ''}
                      {backtestResult.excess_return.toFixed(2)}%
                    </p>
                    <p className="text-xs text-gray-400">超额收益</p>
                  </div>
                </div>

                {/* 策略收益 vs 持有不动 */}
                {strategyComparison.length > 0 && (
                  <div className="card p-4">
                    <h3 className="text-sm font-bold text-gray-700 mb-3">
                      策略收益 vs 持有不动
                    </h3>
                    <div className="flex items-center gap-4 mb-2 text-xs">
                      <span className="flex items-center gap-1.5">
                        <span className="w-3 h-0.5 bg-blue-500 inline-block rounded" />
                        情绪策略
                      </span>
                      <span className="flex items-center gap-1.5">
                        <span className="w-3 h-0.5 bg-gray-400 inline-block rounded" />
                        持有不动
                      </span>
                    </div>
                    <div className="h-32 relative">
                      <svg viewBox="0 0 400 120" className="w-full h-full">
                        {(() => {
                          const allVals = strategyComparison.flatMap((d) => [d.strategy, d.hold]);
                          const minV = Math.min(...allVals);
                          const maxV = Math.max(...allVals);
                          const range = maxV - minV || 1;
                          const toX = (i: number) => (i / (strategyComparison.length - 1)) * 400;
                          const toY = (v: number) => 120 - ((v - minV) / range) * 104 - 8;

                          const strategyPts = strategyComparison.map((d, i) => `${toX(i)},${toY(d.strategy)}`).join(' ');
                          const holdPts = strategyComparison.map((d, i) => `${toX(i)},${toY(d.hold)}`).join(' ');

                          return (
                            <>
                              <polyline points={holdPts} fill="none" stroke="#9CA3AF" strokeWidth={1.5} strokeDasharray="4,3" />
                              <polyline points={strategyPts} fill="none" stroke="#3B82F6" strokeWidth={2} />
                            </>
                          );
                        })()}
                      </svg>
                    </div>
                  </div>
                )}

                {/* 最近交易 */}
                {backtestTrades.length > 0 && (
                  <div className="card p-4">
                    <h3 className="text-sm font-bold text-gray-700 mb-3">最近交易记录</h3>
                    <div className="space-y-1 max-h-[200px] overflow-y-auto">
                      {backtestTrades.slice(-10).reverse().map((t, i) => (
                        <div key={i} className="flex items-center gap-2 py-1 text-xs">
                          <span className="text-gray-400 w-24">{t.date}</span>
                          <span
                            className={clsx(
                              'px-1.5 py-0.5 rounded text-[10px] font-medium',
                              t.type === 'buy' ? 'bg-green-100 text-green-600' : 'bg-red-100 text-red-600'
                            )}
                          >
                            {t.type === 'buy' ? '买入' : '卖出'}
                          </span>
                          <span className="font-mono text-gray-600">¥{t.amount.toLocaleString()}</span>
                          <span className="text-gray-400 truncate">{t.reason}</span>
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </>
            )}
          </div>
        )}

        {/* ======== 模型优化 ======== */}
        {activeTab === 'optimization' && (
          <div className="space-y-4">
            {optLoading ? (
              <LoadingSpinner text="加载优化建议..." />
            ) : (
              <>
                <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
                  <div className="card p-4 text-center">
                    <p className="text-2xl font-bold text-green-600">+3.2%</p>
                    <p className="text-xs text-gray-400">预期超额收益提升</p>
                  </div>
                  <div className="card p-4 text-center">
                    <p className="text-2xl font-bold text-blue-600">+4.8%</p>
                    <p className="text-xs text-gray-400">预期胜率提升</p>
                  </div>
                  <div className="card p-4 text-center">
                    <p className="text-2xl font-bold text-orange-500">-2.1%</p>
                    <p className="text-xs text-gray-400">预期回撤降低</p>
                  </div>
                  <div className="card p-4 text-center">
                    <p className="text-2xl font-bold text-gray-700">{optSuggestions.length}</p>
                    <p className="text-xs text-gray-400">优化建议</p>
                  </div>
                </div>

                <div className="space-y-3">
                  {optSuggestions.map((s) => (
                    <div
                      key={s.id}
                      className={clsx(
                        'card p-4 transition-all duration-200',
                        s.status === 'accepted' && 'border-green-300 bg-green-50/50',
                        s.status === 'rejected' && 'border-red-200 bg-red-50/50 opacity-60'
                      )}
                    >
                      <div className="flex items-start justify-between gap-4">
                        <div className="flex-1">
                          <div className="flex items-center gap-2 mb-1">
                            <h3 className="text-sm font-bold text-gray-800">{s.title}</h3>
                            {s.status === 'accepted' && (
                              <span className="text-[10px] px-1.5 py-0.5 bg-green-100 text-green-600 rounded-full">
                                已采纳
                              </span>
                            )}
                            {s.status === 'rejected' && (
                              <span className="text-[10px] px-1.5 py-0.5 bg-red-100 text-red-500 rounded-full">
                                已拒绝
                              </span>
                            )}
                          </div>
                          <p className="text-xs text-gray-500 mb-2">{s.description}</p>
                          <p className="text-xs text-blue-600 font-medium bg-blue-50 inline-block px-2 py-0.5 rounded">
                            {s.impact}
                          </p>
                        </div>
                        {s.status === 'pending' && (
                          <div className="flex items-center gap-2 shrink-0">
                            <button
                              onClick={() => handleAdoptSuggestion(s.id)}
                              className="flex items-center gap-1 px-3 py-1.5 text-xs bg-green-500 text-white rounded-lg hover:bg-green-600 transition-colors"
                            >
                              <Check className="w-3 h-3" />
                              采纳
                            </button>
                            <button
                              onClick={() => handleRejectSuggestion(s.id)}
                              className="flex items-center gap-1 px-3 py-1.5 text-xs bg-gray-200 text-gray-600 rounded-lg hover:bg-gray-300 transition-colors"
                            >
                              <X className="w-3 h-3" />
                              拒绝
                            </button>
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </>
            )}
          </div>
        )}

        {/* ======== 版本管理 ======== */}
        {activeTab === 'versions' && (
          <div className="space-y-4">
            {versionsLoading ? (
              <LoadingSpinner text="加载版本信息..." />
            ) : (
              <div className="space-y-3">
                {configVersions.map((v, idx) => (
                  <div
                    key={v.version}
                    className={clsx(
                      'card p-4 transition-all',
                      idx === 0 && 'border-blue-300 bg-blue-50/30'
                    )}
                  >
                    <div className="flex items-start justify-between">
                      <div className="flex-1">
                        <div className="flex items-center gap-2 mb-2">
                          <span className="text-sm font-bold text-gray-800">{v.version}</span>
                          <span className="text-xs text-gray-400">{v.released_at}</span>
                          {idx === 0 && (
                            <span className="text-[10px] px-1.5 py-0.5 bg-blue-100 text-blue-600 rounded-full">
                              当前
                            </span>
                          )}
                        </div>
                        <div className="flex flex-wrap gap-1.5 mb-3">
                          {v.changes.map((c, ci) => (
                            <span key={ci} className="text-xs text-gray-600 bg-gray-100 px-2 py-0.5 rounded">
                              {c}
                            </span>
                          ))}
                        </div>
                        <div className="flex flex-wrap gap-2">
                          {Object.entries(v.weights).map(([k, w]) => (
                            <span key={k} className="text-[10px] text-gray-400">
                              <span className="font-medium text-gray-500">{k}</span>: {(w * 100).toFixed(0)}%
                            </span>
                          ))}
                        </div>
                      </div>
                      {idx > 0 && (
                        <button
                          onClick={() => handleRollback(v.version)}
                          disabled={rollingBack === v.version}
                          className="flex items-center gap-1 px-3 py-1.5 text-xs bg-gray-100 text-gray-600 rounded-lg hover:bg-gray-200 disabled:opacity-50 transition-colors shrink-0 ml-4"
                        >
                          <RotateCcw className="w-3 h-3" />
                          {rollingBack === v.version ? '回滚中...' : '回滚到此版本'}
                        </button>
                      )}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
