import { useState, useEffect, useCallback } from 'react';
import {
  fetchPortfolio,
  fetchPortfolioOverlap,
  addPortfolioItem,
  deletePortfolioItem,
} from '../api/portfolio';
import type {
  PortfolioItem,
  PortfolioSummary,
  PortfolioOverlap,
  SentimentLabel,
} from '../types';
import SentimentBadge from '../components/common/SentimentBadge';
import SignalLights from '../components/common/SignalLights';
import LoadingSpinner from '../components/common/LoadingSpinner';
import ErrorMessage from '../components/common/ErrorMessage';
import {
  AlertCircle,
  Plus,
  X,
  TrendingUp,
  TrendingDown,
  Trash2,
  PieChart,
} from 'lucide-react';
import { clsx } from 'clsx';

/* ================================================================
   Mock 数据
   ================================================================ */
function mockPortfolio(): { items: PortfolioItem[]; summary: PortfolioSummary } {
  const items: PortfolioItem[] = [
    { id: 1, fund_code: '000001', fund_name: '华夏成长混合', fund_type: '混合型', holding_shares: 15000, cost_nav: 1.1056, current_nav: 1.2345, market_value: 18517.5, total_return: 1933.5, return_rate: 11.67, daily_return: 0.85, buy_date: '2024-06-15', portfolio_tag: 'core', weight_pct: 28.5 },
    { id: 2, fund_code: '000002', fund_name: '易方达消费行业股票', fund_type: '股票型', holding_shares: 5000, cost_nav: 3.5210, current_nav: 3.8762, market_value: 19381.0, total_return: 1776.0, return_rate: 10.09, daily_return: -0.42, buy_date: '2024-08-20', portfolio_tag: 'satellite', weight_pct: 29.8 },
    { id: 3, fund_code: '000003', fund_name: '天弘沪深300ETF联接A', fund_type: '指数型', holding_shares: 10000, cost_nav: 1.0500, current_nav: 1.1056, market_value: 11056.0, total_return: 556.0, return_rate: 5.30, daily_return: 0.23, buy_date: '2024-09-01', portfolio_tag: 'core', weight_pct: 17.0 },
    { id: 4, fund_code: '000004', fund_name: '招商中证白酒指数(LOF)A', fund_type: '指数型', holding_shares: 8000, cost_nav: 1.7234, current_nav: 1.5678, market_value: 12542.4, total_return: -1244.8, return_rate: -9.03, daily_return: 1.52, buy_date: '2024-07-10', portfolio_tag: 'satellite', weight_pct: 19.3 },
    { id: 5, fund_code: '000008', fund_name: '工银瑞信双利债券A', fund_type: '债券型', holding_shares: 5000, cost_nav: 1.0621, current_nav: 1.0823, market_value: 5411.5, total_return: 101.0, return_rate: 1.90, daily_return: 0.02, buy_date: '2024-10-15', portfolio_tag: 'core', weight_pct: 5.4 },
  ];

  const totalValue = items.reduce((s, i) => s + i.market_value, 0);
  const totalReturn = items.reduce((s, i) => s + i.total_return, 0);
  const totalCost = items.reduce((s, i) => s + i.cost_nav * i.holding_shares, 0);
  const dailyReturn = items.reduce((s, i) => s + i.market_value * (i.daily_return / 100), 0);

  return {
    items,
    summary: {
      total_value: totalValue,
      total_return: totalReturn,
      total_return_rate: totalCost > 0 ? (totalReturn / totalCost) * 100 : 0,
      daily_return: dailyReturn,
      fund_count: items.length,
      core_ratio: items.filter((i) => i.portfolio_tag === 'core').reduce((s, i) => s + i.weight_pct, 0),
      satellite_ratio: items.filter((i) => i.portfolio_tag === 'satellite').reduce((s, i) => s + i.weight_pct, 0),
    },
  };
}

function mockOverlap(): PortfolioOverlap {
  return {
    overall_overlap_score: 42,
    overlap_level: 'medium',
    details: [
      { pair: ['华夏成长混合', '易方达消费行业股票'], overlap_score: 55, overlap_sectors: ['大消费', '白酒'], suggestion: '消费板块集中度偏高，建议分散' },
      { pair: ['华夏成长混合', '天弘沪深300ETF联接A'], overlap_score: 35, overlap_sectors: ['金融', '消费'], suggestion: '重叠度适中' },
      { pair: ['易方达消费行业股票', '招商中证白酒指数(LOF)A'], overlap_score: 72, overlap_sectors: ['白酒', '食品饮料', '大消费'], suggestion: '白酒板块重叠严重，注意风险集中' },
    ],
    suggestion: '整体持仓消费板块集中度偏高（42%），建议适当增加科技、医药等板块配置以分散风险。',
  };
}

function mockSentiment(fundCode: string): {
  score: number;
  label: SentimentLabel;
  shortTerm: SentimentLabel;
  midTerm: SentimentLabel;
  longTerm: SentimentLabel;
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
  };
}

// 板块重叠度热力图数据
const HEATMAP_SECTORS = ['大消费', '科技TMT', '新能源', '金融地产', '医药健康', '高端制造', '周期资源'];
function mockHeatmapData(items: PortfolioItem[]): { sector: string; fund: string; value: number }[] {
  const data: { sector: string; fund: string; value: number }[] = [];
  for (const item of items) {
    for (const sector of HEATMAP_SECTORS) {
      const hash = (item.fund_code + sector).split('').reduce((a, c) => a + c.charCodeAt(0), 0);
      data.push({
        sector,
        fund: item.fund_name.length > 6 ? item.fund_name.slice(0, 6) + '...' : item.fund_name,
        value: 5 + (hash % 90),
      });
    }
  }
  return data;
}

// 仓位调整建议
function mockRebalance(items: PortfolioItem[]): { fund: string; action: string; currentWeight: number; targetWeight: number; reason: string }[] {
  return [
    { fund: '华夏成长混合', action: '维持', currentWeight: 28.5, targetWeight: 28, reason: '核心仓位，情绪中性偏多，维持配置' },
    { fund: '易方达消费行业股票', action: '减仓', currentWeight: 29.8, targetWeight: 22, reason: '消费板块情绪过热，与白酒重叠度高，建议适度减仓' },
    { fund: '天弘沪深300ETF联接A', action: '加仓', currentWeight: 17.0, targetWeight: 22, reason: '大盘情绪中性偏低，估值合理，可适度增配' },
    { fund: '招商中证白酒指数(LOF)A', action: '减仓', currentWeight: 19.3, targetWeight: 12, reason: '白酒板块波动大，情绪回落，建议降低风险敞口' },
    { fund: '工银瑞信双利债券A', action: '加仓', currentWeight: 5.4, targetWeight: 16, reason: '债券情绪稳定，作为防御配置，建议提升占比' },
  ];
}

/* ================================================================
   CSS Grid 热力图组件
   ================================================================ */
function OverlapHeatmap({
  data,
  sectors,
  funds,
}: {
  data: { sector: string; fund: string; value: number }[];
  sectors: string[];
  funds: string[];
}) {
  // 色阶函数：0%→#F0FDF4, 50%→#FEF3C7, 100%→#FEE2E2
  const getColor = (value: number): string => {
    const pct = Math.max(0, Math.min(100, value)) / 100;
    if (pct < 0.5) {
      // 0 → 0.5: #F0FDF4 → #FEF3C7
      const t = pct / 0.5;
      const r = Math.round(0xf0 + t * (0xfe - 0xf0));
      const g = Math.round(0xfd + t * (0xf3 - 0xfd));
      const b = Math.round(0xf4 + t * (0xc7 - 0xf4));
      return `rgb(${r},${g},${b})`;
    } else {
      // 0.5 → 1: #FEF3C7 → #FEE2E2
      const t = (pct - 0.5) / 0.5;
      const r = Math.round(0xfe + t * (0xfe - 0xfe));
      const g = Math.round(0xf3 + t * (0xe2 - 0xf3));
      const b = Math.round(0xc7 + t * (0xe2 - 0xc7));
      return `rgb(${r},${g},${b})`;
    }
  };

  return (
    <div className="overflow-x-auto">
      <div className="inline-grid" style={{ gridTemplateColumns: `80px repeat(${sectors.length}, minmax(60px, 1fr))` }}>
        {/* Header */}
        <div className="h-8" />
        {sectors.map((s) => (
          <div key={s} className="h-8 flex items-center justify-center text-[10px] text-gray-500 font-medium whitespace-nowrap px-1">
            {s}
          </div>
        ))}

        {/* Rows */}
        {funds.map((fund) => (
          <div key={fund} className="contents">
            <div className="h-9 flex items-center text-xs text-gray-600 font-medium pr-2 whitespace-nowrap">
              {fund}
            </div>
            {sectors.map((sector) => {
              const cell = data.find((d) => d.sector === sector && d.fund === fund);
              const val = cell ? cell.value : 0;
              return (
                <div
                  key={`${fund}-${sector}`}
                  className="h-9 flex items-center justify-center text-[10px] font-mono text-gray-700 border border-white rounded-sm transition-colors"
                  style={{ backgroundColor: getColor(val) }}
                  title={`${fund} × ${sector}: ${val}%`}
                >
                  {val}%
                </div>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}

/* ================================================================
   主组件
   ================================================================ */
export default function Portfolio() {
  const [items, setItems] = useState<PortfolioItem[]>([]);
  const [summary, setSummary] = useState<PortfolioSummary | null>(null);
  const [overlap, setOverlap] = useState<PortfolioOverlap | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // 添加持仓表单
  const [showAddForm, setShowAddForm] = useState(false);
  const [addForm, setAddForm] = useState({ fund_code: '', fund_name: '', holding_shares: '', cost_nav: '', buy_date: '' });
  const [adding, setAdding] = useState(false);
  const [addError, setAddError] = useState<string | null>(null);

  // 删除确认
  const [confirmDelete, setConfirmDelete] = useState<number | null>(null);

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    Promise.all([fetchPortfolio(), fetchPortfolioOverlap()])
      .then(([pData, oData]) => {
        setItems(pData.items);
        setSummary(pData.summary);
        setOverlap(oData);
        setLoading(false);
      })
      .catch(() => {
        const mock = mockPortfolio();
        setItems(mock.items);
        setSummary(mock.summary);
        setOverlap(mockOverlap());
        setLoading(false);
      });
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const handleAdd = async () => {
    if (!addForm.fund_code || !addForm.holding_shares || !addForm.cost_nav) {
      setAddError('请填写基金代码、份额和成本价');
      return;
    }
    setAdding(true);
    setAddError(null);
    try {
      await addPortfolioItem({
        fund_code: addForm.fund_code,
        fund_name: addForm.fund_name || '未知基金',
        fund_type: '混合型',
        holding_shares: parseFloat(addForm.holding_shares),
        cost_nav: parseFloat(addForm.cost_nav),
        current_nav: parseFloat(addForm.cost_nav) * 1.05,
        market_value: parseFloat(addForm.holding_shares) * parseFloat(addForm.cost_nav) * 1.05,
        total_return: parseFloat(addForm.holding_shares) * parseFloat(addForm.cost_nav) * 0.05,
        return_rate: 5.0,
        daily_return: 0.5,
        buy_date: addForm.buy_date || new Date().toISOString().slice(0, 10),
        portfolio_tag: 'satellite',
        weight_pct: 0,
      });
      load();
      setShowAddForm(false);
      setAddForm({ fund_code: '', fund_name: '', holding_shares: '', cost_nav: '', buy_date: '' });
    } catch {
      // Mock: 本地添加
      const shares = parseFloat(addForm.holding_shares);
      const cost = parseFloat(addForm.cost_nav);
      const current = cost * 1.05;
      const newItem: PortfolioItem = {
        id: Date.now(),
        fund_code: addForm.fund_code,
        fund_name: addForm.fund_name || '未知基金',
        fund_type: '混合型',
        holding_shares: shares,
        cost_nav: cost,
        current_nav: current,
        market_value: shares * current,
        total_return: shares * (current - cost),
        return_rate: ((current - cost) / cost) * 100,
        daily_return: 0.5,
        buy_date: addForm.buy_date || new Date().toISOString().slice(0, 10),
        portfolio_tag: 'satellite' as const,
        weight_pct: 0,
      };
      setItems((prev) => [...prev, newItem]);
      setShowAddForm(false);
      setAddForm({ fund_code: '', fund_name: '', holding_shares: '', cost_nav: '', buy_date: '' });
    } finally {
      setAdding(false);
    }
  };

  const handleDelete = async (id: number) => {
    try {
      await deletePortfolioItem(id);
      setItems((prev) => prev.filter((i) => i.id !== id));
    } catch {
      setItems((prev) => prev.filter((i) => i.id !== id));
    } finally {
      setConfirmDelete(null);
    }
  };

  const heatmapData = mockHeatmapData(items);
  const fundNames = items.map((i) => (i.fund_name.length > 6 ? i.fund_name.slice(0, 6) + '...' : i.fund_name));
  const rebalanceData = mockRebalance(items);

  if (loading) return <LoadingSpinner text="加载持仓数据..." />;
  if (error) return <ErrorMessage message={error} onRetry={load} />;

  return (
    <div className="max-w-5xl mx-auto space-y-4 md:space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl md:text-2xl font-bold text-gray-800">我的持仓</h1>
          <p className="text-xs md:text-sm text-gray-400 mt-1">持仓分析、情绪监控与仓位优化</p>
        </div>
        <button
          onClick={() => setShowAddForm(!showAddForm)}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 text-white text-xs font-medium rounded-lg hover:bg-blue-700 transition-colors"
        >
          <Plus className="w-3.5 h-3.5" />
          添加持仓
        </button>
      </div>

      {/* ======== 添加持仓表单 ======== */}
      {showAddForm && (
        <div className="card p-4 animate-expand">
          <div className="flex items-center justify-between mb-3">
            <h3 className="text-sm font-bold text-gray-700">添加持仓</h3>
            <button onClick={() => setShowAddForm(false)} className="p-1 text-gray-400 hover:text-gray-600">
              <X className="w-4 h-4" />
            </button>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-3">
            <div>
              <label className="block text-xs text-gray-500 mb-1">基金代码 *</label>
              <input
                type="text"
                value={addForm.fund_code}
                onChange={(e) => setAddForm((f) => ({ ...f, fund_code: e.target.value }))}
                placeholder="如 000001"
                className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">基金名称</label>
              <input
                type="text"
                value={addForm.fund_name}
                onChange={(e) => setAddForm((f) => ({ ...f, fund_name: e.target.value }))}
                placeholder="自动获取或手动输入"
                className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">持有份额 *</label>
              <input
                type="number"
                value={addForm.holding_shares}
                onChange={(e) => setAddForm((f) => ({ ...f, holding_shares: e.target.value }))}
                placeholder="0"
                className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">成本净值 *</label>
              <input
                type="number"
                step="0.0001"
                value={addForm.cost_nav}
                onChange={(e) => setAddForm((f) => ({ ...f, cost_nav: e.target.value }))}
                placeholder="0.0000"
                className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
            <div>
              <label className="block text-xs text-gray-500 mb-1">买入日期</label>
              <input
                type="date"
                value={addForm.buy_date}
                onChange={(e) => setAddForm((f) => ({ ...f, buy_date: e.target.value }))}
                className="w-full px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
              />
            </div>
          </div>
          {addError && <p className="text-xs text-red-500 mt-2">{addError}</p>}
          <div className="flex justify-end gap-2 mt-3">
            <button
              onClick={() => setShowAddForm(false)}
              className="px-4 py-1.5 text-xs text-gray-600 bg-gray-100 rounded-lg hover:bg-gray-200"
            >
              取消
            </button>
            <button
              onClick={handleAdd}
              disabled={adding}
              className="px-4 py-1.5 text-xs text-white bg-blue-600 rounded-lg hover:bg-blue-700 disabled:opacity-50"
            >
              {adding ? '添加中...' : '确认添加'}
            </button>
          </div>
        </div>
      )}

      {/* ======== 持仓概览 ======== */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-5 gap-3">
          <div className="card p-4">
            <span className="text-xs text-gray-400">总市值</span>
            <p className="text-lg font-bold text-gray-800">¥{summary.total_value.toLocaleString()}</p>
          </div>
          <div className="card p-4">
            <span className="text-xs text-gray-400">累计收益</span>
            <p className={clsx('text-lg font-bold', summary.total_return >= 0 ? 'text-red-500' : 'text-green-500')}>
              {summary.total_return >= 0 ? '+' : ''}¥{Math.abs(summary.total_return).toLocaleString()}
            </p>
          </div>
          <div className="card p-4">
            <span className="text-xs text-gray-400">收益率</span>
            <p className={clsx('text-lg font-bold', summary.total_return_rate >= 0 ? 'text-red-500' : 'text-green-500')}>
              {summary.total_return_rate >= 0 ? '+' : ''}{summary.total_return_rate.toFixed(2)}%
            </p>
          </div>
          <div className="card p-4">
            <span className="text-xs text-gray-400">今日收益</span>
            <p className={clsx('text-lg font-bold', summary.daily_return >= 0 ? 'text-red-500' : 'text-green-500')}>
              {summary.daily_return >= 0 ? '+' : ''}¥{Math.abs(summary.daily_return).toFixed(2)}
            </p>
          </div>
          <div className="card p-4 md:col-span-2 lg:col-span-1">
            <span className="text-xs text-gray-400">核心/卫星比</span>
            <div className="flex items-center gap-2 mt-1">
              <div className="flex-1 h-3 bg-gray-100 rounded-full overflow-hidden flex">
                <div
                  className="h-full bg-blue-400 rounded-l-full"
                  style={{ width: `${summary.core_ratio}%` }}
                />
                <div
                  className="h-full bg-orange-400 rounded-r-full"
                  style={{ width: `${summary.satellite_ratio}%` }}
                />
              </div>
              <span className="text-xs text-gray-400">
                {summary.core_ratio.toFixed(0)}/{summary.satellite_ratio.toFixed(0)}
              </span>
            </div>
          </div>
        </div>
      )}

      {/* ======== 持仓列表 ======== */}
      <div className="card overflow-hidden">
        <div className="px-4 py-3 border-b border-gray-100 flex items-center justify-between">
          <h2 className="text-sm font-bold text-gray-700">
            持仓明细 ({summary?.fund_count || items.length}只)
          </h2>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="text-left px-4 py-2.5 text-xs text-gray-500 font-medium">代码/名称</th>
                <th className="text-right px-4 py-2.5 text-xs text-gray-500 font-medium">份额</th>
                <th className="text-right px-4 py-2.5 text-xs text-gray-500 font-medium">成本</th>
                <th className="text-right px-4 py-2.5 text-xs text-gray-500 font-medium">现价</th>
                <th className="text-right px-4 py-2.5 text-xs text-gray-500 font-medium">市值</th>
                <th className="text-right px-4 py-2.5 text-xs text-gray-500 font-medium">盈亏</th>
                <th className="text-right px-4 py-2.5 text-xs text-gray-500 font-medium">比例</th>
                <th className="text-center px-4 py-2.5 text-xs text-gray-500 font-medium">情绪</th>
                <th className="text-center px-4 py-2.5 text-xs text-gray-500 font-medium">信号</th>
                <th className="w-10" />
              </tr>
            </thead>
            <tbody>
              {items.map((item) => {
                const s = mockSentiment(item.fund_code);
                const pnl = (item.current_nav - item.cost_nav) * item.holding_shares;
                const pnlPct = ((item.current_nav - item.cost_nav) / item.cost_nav) * 100;
                return (
                  <tr key={item.id} className="border-t border-gray-50 hover:bg-gray-50 transition-colors">
                    <td className="px-4 py-2.5">
                      <span className="text-xs text-gray-400 font-mono mr-1.5">{item.fund_code}</span>
                      <span className="font-medium text-gray-800 text-xs">{item.fund_name}</span>
                      <span className={clsx(
                        'ml-1.5 text-[10px] px-1 py-0.5 rounded',
                        item.portfolio_tag === 'core' ? 'bg-blue-100 text-blue-600' : 'bg-orange-100 text-orange-600'
                      )}>
                        {item.portfolio_tag === 'core' ? '核心' : '卫星'}
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-right font-mono text-xs text-gray-600">
                      {item.holding_shares.toLocaleString()}
                    </td>
                    <td className="px-4 py-2.5 text-right font-mono text-xs text-gray-500">
                      ¥{item.cost_nav.toFixed(4)}
                    </td>
                    <td className="px-4 py-2.5 text-right font-mono text-xs text-gray-700">
                      ¥{item.current_nav.toFixed(4)}
                    </td>
                    <td className="px-4 py-2.5 text-right font-mono text-xs text-gray-700">
                      ¥{item.market_value.toLocaleString()}
                    </td>
                    <td className="px-4 py-2.5 text-right text-xs">
                      <span className={clsx('font-mono', pnl >= 0 ? 'text-red-500' : 'text-green-500')}>
                        {pnl >= 0 ? '+' : ''}¥{Math.abs(pnl).toFixed(0)}
                      </span>
                      <span className={clsx('font-mono ml-1', pnlPct >= 0 ? 'text-red-400' : 'text-green-400')}>
                        ({pnlPct >= 0 ? '+' : ''}{pnlPct.toFixed(2)}%)
                      </span>
                    </td>
                    <td className="px-4 py-2.5 text-right text-xs text-gray-500">
                      {item.weight_pct.toFixed(1)}%
                    </td>
                    <td className="px-4 py-2.5 text-center">
                      <SentimentBadge sentiment={s.label} size="sm" />
                    </td>
                    <td className="px-4 py-2.5 text-center">
                      <div className="flex justify-center">
                        <SignalLights
                          shortTerm={s.shortTerm}
                          midTerm={s.midTerm}
                          longTerm={s.longTerm}
                          size="sm"
                        />
                      </div>
                    </td>
                    <td className="px-2 py-2.5">
                      {confirmDelete === item.id ? (
                        <div className="flex items-center gap-0.5">
                          <button
                            onClick={() => handleDelete(item.id)}
                            className="px-1.5 py-0.5 text-[10px] bg-red-500 text-white rounded"
                          >
                            确认
                          </button>
                          <button
                            onClick={() => setConfirmDelete(null)}
                            className="px-1.5 py-0.5 text-[10px] bg-gray-200 text-gray-600 rounded"
                          >
                            取消
                          </button>
                        </div>
                      ) : (
                        <button
                          onClick={() => setConfirmDelete(item.id)}
                          className="p-1 text-gray-400 hover:text-red-500 transition-colors"
                        >
                          <Trash2 className="w-3.5 h-3.5" />
                        </button>
                      )}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </div>

      {/* ======== 板块重叠度热力图 ======== */}
      {items.length > 1 && (
        <div className="card p-4">
          <div className="flex items-center gap-2 mb-3">
            <PieChart className="w-4 h-4 text-purple-500" />
            <h3 className="text-sm font-bold text-gray-700">板块重叠度热力图</h3>
          </div>
          <p className="text-xs text-gray-400 mb-3">
            色阶: 绿色(低重叠) → 黄色(中等) → 红色(高重叠)
          </p>
          <OverlapHeatmap data={heatmapData} sectors={HEATMAP_SECTORS} funds={fundNames} />
          <div className="flex items-center gap-2 mt-3 text-[10px] text-gray-400">
            <span className="inline-block w-3 h-3 rounded" style={{ background: '#F0FDF4' }} />
            <span>0%</span>
            <span className="inline-block w-3 h-3 rounded" style={{ background: '#FEF3C7' }} />
            <span>50%</span>
            <span className="inline-block w-3 h-3 rounded" style={{ background: '#FEE2E2' }} />
            <span>100%</span>
          </div>
        </div>
      )}

      {/* ======== 持仓重叠分析 ======== */}
      {overlap && (
        <div className="card p-4">
          <div className="flex items-center gap-2 mb-3">
            <AlertCircle className="w-4 h-4 text-orange-400" />
            <h3 className="text-sm font-bold text-gray-700">持仓重叠分析</h3>
            <span
              className={clsx(
                'text-xs px-2 py-0.5 rounded font-medium',
                overlap.overlap_level === 'low'
                  ? 'bg-green-100 text-green-600'
                  : overlap.overlap_level === 'medium'
                  ? 'bg-yellow-100 text-yellow-600'
                  : 'bg-red-100 text-red-600'
              )}
            >
              重叠度: {overlap.overall_overlap_score.toFixed(0)}%
            </span>
          </div>

          <div className="space-y-2">
            {overlap.details.map((d, i) => (
              <div key={i} className="p-2.5 bg-gray-50 rounded-lg text-xs">
                <p className="text-gray-600">
                  <span className="font-medium">{d.pair[0]}</span>
                  {' ↔ '}
                  <span className="font-medium">{d.pair[1]}</span>
                  {' 重叠 '}
                  <span className="font-bold text-gray-700">{d.overlap_score.toFixed(0)}%</span>
                </p>
                <p className="text-gray-400 mt-0.5">共同板块: {d.overlap_sectors.join(', ')}</p>
                <p className="text-gray-400">{d.suggestion}</p>
              </div>
            ))}
          </div>

          <p className="mt-3 text-xs text-gray-500 bg-blue-50 p-3 rounded-lg">{overlap.suggestion}</p>
        </div>
      )}

      {/* ======== 仓位调整建议 ======== */}
      <div className="card p-4">
        <div className="flex items-center gap-2 mb-3">
          {rebalanceData.some((r) => r.action === '减仓') ? (
            <TrendingDown className="w-4 h-4 text-orange-500" />
          ) : (
            <TrendingUp className="w-4 h-4 text-blue-500" />
          )}
          <h3 className="text-sm font-bold text-gray-700">仓位调整建议</h3>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead className="bg-gray-50">
              <tr>
                <th className="text-left px-4 py-2 text-xs text-gray-500 font-medium">基金</th>
                <th className="text-center px-4 py-2 text-xs text-gray-500 font-medium">操作</th>
                <th className="text-right px-4 py-2 text-xs text-gray-500 font-medium">当前权重</th>
                <th className="text-right px-4 py-2 text-xs text-gray-500 font-medium">目标权重</th>
                <th className="text-left px-4 py-2 text-xs text-gray-500 font-medium">理由</th>
              </tr>
            </thead>
            <tbody>
              {rebalanceData.map((r, i) => (
                <tr key={i} className="border-t border-gray-50">
                  <td className="px-4 py-2 text-xs text-gray-700">{r.fund}</td>
                  <td className="px-4 py-2 text-center">
                    <span
                      className={clsx(
                        'text-[10px] px-2 py-0.5 rounded-full font-medium',
                        r.action === '加仓'
                          ? 'bg-green-100 text-green-600'
                          : r.action === '减仓'
                          ? 'bg-red-100 text-red-600'
                          : 'bg-gray-100 text-gray-500'
                      )}
                    >
                      {r.action}
                    </span>
                  </td>
                  <td className="px-4 py-2 text-right text-xs font-mono text-gray-500">{r.currentWeight}%</td>
                  <td className="px-4 py-2 text-right text-xs font-mono font-bold text-gray-700">{r.targetWeight}%</td>
                  <td className="px-4 py-2 text-xs text-gray-400">{r.reason}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

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
