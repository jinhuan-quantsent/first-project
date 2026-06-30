import { useState, useCallback, useRef, useEffect } from 'react';
import { searchFunds, fetchFundDetail } from '../api/fund';
import type {
  FundSearchItem,
  FundDetail,
  SentimentLabel,
  TrendDirection,
} from '../types';
import SentimentBadge from '../components/common/SentimentBadge';
import SignalLights from '../components/common/SignalLights';
import MicroTrendBar from '../components/common/MicroTrendBar';
import LoadingSpinner from '../components/common/LoadingSpinner';
import ErrorMessage from '../components/common/ErrorMessage';
import { Search, ChevronDown, ChevronUp, AlertTriangle, TrendingUp, Shield } from 'lucide-react';
import { clsx } from 'clsx';

/* ================================================================
   Mock 数据
   ================================================================ */
function generateMockResults(keyword: string): FundSearchItem[] {
  const base: FundSearchItem[] = [
    { fund_code: '000001', fund_name: '华夏成长混合', fund_short_name: '华夏成长', fund_type: '混合型', nav: 1.2345, daily_return: 0.85, week_return: 1.23, month_return: -2.15, year_return: 12.8, fund_size: 89.5, risk_level: '中高风险' },
    { fund_code: '000002', fund_name: '易方达消费行业股票', fund_short_name: '易方达消费', fund_type: '股票型', nav: 3.8762, daily_return: -0.42, week_return: -1.05, month_return: 3.78, year_return: 22.3, fund_size: 156.2, risk_level: '高风险' },
    { fund_code: '000003', fund_name: '天弘沪深300ETF联接A', fund_short_name: '天弘沪深300', fund_type: '指数型', nav: 1.1056, daily_return: 0.23, week_return: 0.56, month_return: 1.34, year_return: 8.92, fund_size: 320.7, risk_level: '中风险' },
    { fund_code: '000004', fund_name: '招商中证白酒指数(LOF)A', fund_short_name: '招商白酒', fund_type: '指数型', nav: 1.5678, daily_return: 1.52, week_return: 3.21, month_return: -5.67, year_return: -3.45, fund_size: 245.3, risk_level: '高风险' },
    { fund_code: '000005', fund_name: '广发稳健增长混合A', fund_short_name: '广发稳健', fund_type: '混合型', nav: 1.8932, daily_return: 0.12, week_return: 0.34, month_return: 1.89, year_return: 15.6, fund_size: 67.8, risk_level: '中风险' },
    { fund_code: '000006', fund_name: '南方中证500ETF联接A', fund_short_name: '南方中证500', fund_type: '指数型', nav: 1.4521, daily_return: -0.67, week_return: -2.34, month_return: 0.56, year_return: 5.43, fund_size: 198.4, risk_level: '中风险' },
    { fund_code: '000007', fund_name: '富国天惠成长混合(LOF)A', fund_short_name: '富国天惠', fund_type: '混合型', nav: 2.3410, daily_return: 0.56, week_return: 1.78, month_return: 4.56, year_return: 18.9, fund_size: 112.6, risk_level: '中高风险' },
    { fund_code: '000008', fund_name: '工银瑞信双利债券A', fund_short_name: '工银双利', fund_type: '债券型', nav: 1.0823, daily_return: 0.02, week_return: 0.08, month_return: 0.45, year_return: 3.21, fund_size: 45.9, risk_level: '低风险' },
  ];

  if (!keyword || !keyword.trim()) return base;
  const kw = keyword.toLowerCase().trim();
  return base.filter(
    (f) =>
      f.fund_code.includes(kw) ||
      f.fund_name.toLowerCase().includes(kw) ||
      f.fund_short_name.toLowerCase().includes(kw)
  );
}

function mockSentiment(fundCode: string): {
  score: number;
  label: SentimentLabel;
  shortTerm: SentimentLabel;
  midTerm: SentimentLabel;
  longTerm: SentimentLabel;
  hasDivergence: boolean;
  divergenceType: 'bullish' | 'bearish' | undefined;
  sectorCheck: { sector: string; fund_sentiment: number; sector_sentiment: number; consistent: boolean }[];
  microTrend: { date: string; score: number; label: SentimentLabel }[];
  advice: { action: string; level: string; reason: string };
} {
  const hash = fundCode.split('').reduce((a, c) => a + c.charCodeAt(0), 0);
  const score = 20 + (hash % 65);
  const labels: SentimentLabel[] = ['extreme_fear', 'fear', 'neutral', 'greed', 'extreme_greed'];
  const labelIdx = Math.min(4, Math.floor(score / 20));

  const microLabels: SentimentLabel[] = ['fear', 'neutral', 'neutral', 'greed', 'greed'];
  const days = ['04-07', '04-08', '04-09', '04-10', '04-11'];

  return {
    score,
    label: labels[labelIdx],
    shortTerm: labels[Math.min(4, labelIdx)],
    midTerm: labels[Math.min(4, (labelIdx + 1) % 5)],
    longTerm: labels[Math.min(4, Math.max(0, labelIdx - 1))],
    hasDivergence: hash % 3 === 0,
    divergenceType: hash % 2 === 0 ? 'bullish' : 'bearish',
    sectorCheck: [
      { sector: '大消费', fund_sentiment: 55 + (hash % 20), sector_sentiment: 48 + ((hash * 3) % 25), consistent: hash % 2 === 0 },
      { sector: '科技TMT', fund_sentiment: 62 + (hash % 15), sector_sentiment: 70 + ((hash * 2) % 15), consistent: hash % 3 !== 0 },
      { sector: '新能源', fund_sentiment: 35 + (hash % 25), sector_sentiment: 40 + ((hash * 5) % 20), consistent: true },
    ],
    microTrend: days.map((d, i) => ({
      date: `2025-${d}`,
      score: score + (i - 2) * 5 + (hash % 7) - 3,
      label: microLabels[i],
    })),
    advice: score < 30
      ? { action: '逢低关注', level: '积极', reason: '情绪极度悲观，可能过度反应，可小仓位试探' }
      : score < 50
      ? { action: '持有观望', level: '中性', reason: '情绪偏低，短期不确定性较高，建议持有为主' }
      : score < 70
      ? { action: '适度参与', level: '中性偏多', reason: '情绪回暖，可适度增加配置比例' }
      : { action: '注意风险', level: '谨慎', reason: '情绪过热，建议控制仓位，逢高减仓' },
  };
}

function mockFundDetail(code: string): FundDetail {
  const base = generateMockResults(code).find((f) => f.fund_code === code) || generateMockResults('')[0];
  return {
    ...base,
    manager: '张经理',
    company: '某大型基金公司',
    inception_date: '2018-03-15',
    accumulated_nav: base.nav * 1.8,
    benchmark: '沪深300指数收益率×80%+中证综合债指数收益率×20%',
    tracking_index: code === '000003' ? '沪深300' : code === '000006' ? '中证500' : '',
    description: '本基金通过定量与定性相结合的方法，精选具有持续成长潜力的上市公司股票，力争实现基金资产的长期稳健增值。',
    nav_history: Array.from({ length: 20 }, (_, i) => ({
      date: `2025-03-${String(20 - i).padStart(2, '0')}`,
      nav: base.nav + (Math.random() - 0.5) * 0.1,
      daily_return: (Math.random() - 0.5) * 2,
    })),
  };
}

const FUND_TYPES = ['', '股票型', '混合型', '指数型', '债券型', '货币型'];

/* ================================================================
   组件
   ================================================================ */
export default function FundSearch() {
  const [keyword, setKeyword] = useState('');
  const [fundType, setFundType] = useState('');
  const [results, setResults] = useState<FundSearchItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [selectedFund, setSelectedFund] = useState<FundSearchItem | null>(null);
  const [detailData, setDetailData] = useState<FundDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const detailRef = useRef<HTMLDivElement>(null);

  const handleSearch = useCallback(
    async (p: number = 1) => {
      if (!keyword.trim()) return;
      setLoading(true);
      setPage(p);
      setSelectedFund(null);
      setDetailData(null);
      try {
        const data = await searchFunds({ keyword, fund_type: fundType || undefined, page: p });
        setResults(data.items);
        setTotal(data.total);
      } catch {
        // API 失败，使用 Mock
        const mock = generateMockResults(keyword);
        setResults(mock);
        setTotal(mock.length);
      } finally {
        setLoading(false);
      }
    },
    [keyword, fundType]
  );

  const handleSelect = useCallback(async (fund: FundSearchItem) => {
    if (selectedFund?.fund_code === fund.fund_code) {
      // 收起
      setSelectedFund(null);
      setDetailData(null);
      return;
    }
    setSelectedFund(fund);
    setDetailLoading(true);
    setDetailError(null);
    try {
      const detail = await fetchFundDetail(fund.fund_code);
      setDetailData(detail);
    } catch {
      // API 失败，使用 Mock
      setDetailData(mockFundDetail(fund.fund_code));
    } finally {
      setDetailLoading(false);
    }
  }, [selectedFund]);

  // 展开时自动滚动到详情面板
  useEffect(() => {
    if (selectedFund && detailRef.current) {
      setTimeout(() => {
        detailRef.current?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      }, 100);
    }
  }, [selectedFund, detailData]);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') handleSearch(1);
  };

  const sentimentData = selectedFund ? mockSentiment(selectedFund.fund_code) : null;

  return (
    <div className="max-w-4xl mx-auto space-y-4">
      <div>
        <h1 className="text-xl md:text-2xl font-bold text-gray-800">基金查询</h1>
        <p className="text-xs md:text-sm text-gray-400 mt-1">搜索基金，查看情绪分析和操作建议</p>
      </div>

      {/* ======== 搜索栏 ======== */}
      <div className="card p-4">
        <div className="flex flex-col sm:flex-row gap-3">
          <div className="flex-1 relative">
            <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400" />
            <input
              type="text"
              value={keyword}
              onChange={(e) => setKeyword(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="搜索基金名称、代码、经理..."
              className="w-full pl-9 pr-4 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent"
            />
          </div>
          <select
            value={fundType}
            onChange={(e) => setFundType(e.target.value)}
            className="px-3 py-2 text-sm border border-gray-200 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500"
          >
            {FUND_TYPES.map((t) => (
              <option key={t} value={t}>
                {t || '全部类型'}
              </option>
            ))}
          </select>
          <button
            onClick={() => handleSearch(1)}
            className="px-6 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition-colors"
          >
            搜索
          </button>
        </div>
      </div>

      {/* ======== 结果区域 ======== */}
      {loading ? (
        <LoadingSpinner text="搜索中..." />
      ) : results.length > 0 ? (
        <div className="space-y-2">
          <p className="text-xs text-gray-400">共 {total} 个结果</p>

          {/* 结果表格 */}
          <div className="bg-white rounded-lg border border-gray-200 overflow-hidden">
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="bg-gray-50">
                  <tr>
                    <th className="text-left px-4 py-2.5 text-xs text-gray-500 font-medium">代码</th>
                    <th className="text-left px-4 py-2.5 text-xs text-gray-500 font-medium">名称</th>
                    <th className="text-left px-4 py-2.5 text-xs text-gray-500 font-medium">类型</th>
                    <th className="text-center px-4 py-2.5 text-xs text-gray-500 font-medium">情绪</th>
                    <th className="text-center px-4 py-2.5 text-xs text-gray-500 font-medium">多周期信号</th>
                    <th className="text-right px-4 py-2.5 text-xs text-gray-500 font-medium">净值</th>
                    <th className="text-right px-4 py-2.5 text-xs text-gray-500 font-medium">日收益</th>
                    <th className="text-right px-4 py-2.5 text-xs text-gray-500 font-medium">月收益</th>
                    <th className="text-right px-4 py-2.5 text-xs text-gray-500 font-medium">年收益</th>
                    <th className="w-8" />
                  </tr>
                </thead>
                <tbody>
                  {results.map((fund) => {
                    const s = mockSentiment(fund.fund_code);
                    const isSelected = selectedFund?.fund_code === fund.fund_code;
                    return (
                      <tr
                        key={fund.fund_code}
                        onClick={() => handleSelect(fund)}
                        className={clsx(
                          'border-t border-gray-100 hover:bg-gray-50 cursor-pointer transition-colors',
                          isSelected && 'bg-blue-50/50'
                        )}
                      >
                        <td className="px-4 py-2.5 font-mono text-xs text-gray-500">{fund.fund_code}</td>
                        <td className="px-4 py-2.5 font-medium text-gray-800">
                          {fund.fund_short_name || fund.fund_name}
                        </td>
                        <td className="px-4 py-2.5">
                          <span className="text-xs px-1.5 py-0.5 bg-gray-100 rounded">{fund.fund_type}</span>
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
                              hasDivergence={s.hasDivergence}
                              divergenceType={s.divergenceType}
                              size="sm"
                            />
                          </div>
                        </td>
                        <td className="px-4 py-2.5 text-right font-mono text-xs">{fund.nav.toFixed(4)}</td>
                        <td
                          className={clsx(
                            'px-4 py-2.5 text-right text-xs',
                            fund.daily_return >= 0 ? 'text-red-500' : 'text-green-500'
                          )}
                        >
                          {fund.daily_return >= 0 ? '+' : ''}
                          {fund.daily_return.toFixed(2)}%
                        </td>
                        <td
                          className={clsx(
                            'px-4 py-2.5 text-right text-xs',
                            fund.month_return >= 0 ? 'text-red-500' : 'text-green-500'
                          )}
                        >
                          {fund.month_return >= 0 ? '+' : ''}
                          {fund.month_return.toFixed(2)}%
                        </td>
                        <td
                          className={clsx(
                            'px-4 py-2.5 text-right text-xs',
                            fund.year_return >= 0 ? 'text-red-500' : 'text-green-500'
                          )}
                        >
                          {fund.year_return >= 0 ? '+' : ''}
                          {fund.year_return.toFixed(2)}%
                        </td>
                        <td className="px-2 py-2.5 text-gray-400">
                          {isSelected ? <ChevronUp className="w-4 h-4" /> : <ChevronDown className="w-4 h-4" />}
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          </div>

          {/* ======== 详情面板（动画展开） ======== */}
          {selectedFund && (
            <div
              ref={detailRef}
              className="card overflow-hidden animate-expand"
              style={{
                animation: 'expandDetail 200ms ease-out',
              }}
            >
              {detailLoading ? (
                <div className="p-8">
                  <LoadingSpinner text="加载基金详情..." />
                </div>
              ) : detailError ? (
                <div className="p-8">
                  <ErrorMessage message={detailError} onRetry={() => handleSelect(selectedFund)} />
                </div>
              ) : (
                <div className="p-4 md:p-6 space-y-5">
                  {/* 标题行 */}
                  <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-2">
                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-xs font-mono text-gray-400">{selectedFund.fund_code}</span>
                        <h3 className="text-lg font-bold text-gray-800">{selectedFund.fund_name}</h3>
                      </div>
                      <p className="text-xs text-gray-400 mt-0.5">
                        {selectedFund.fund_type} | 规模 {selectedFund.fund_size}亿 | 风险 {selectedFund.risk_level}
                      </p>
                    </div>
                    {detailData && (
                      <div className="text-xs text-gray-400">
                        基金经理: {detailData.manager} | 成立: {detailData.inception_date}
                      </div>
                    )}
                  </div>

                  <div className="border-t border-gray-100" />

                  {/* 操作建议（前置，与情绪分同一视觉层级） */}
                  {sentimentData && (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      {/* 情绪分 */}
                      <div className="bg-gray-50 rounded-xl p-4 flex items-center gap-4">
                        <div
                          className="w-16 h-16 rounded-full flex items-center justify-center text-white text-xl font-bold shrink-0"
                          style={{
                            background:
                              sentimentData.score < 30
                                ? 'var(--sentiment-extreme-fear)'
                                : sentimentData.score < 50
                                ? 'var(--sentiment-fear)'
                                : sentimentData.score < 70
                                ? 'var(--sentiment-neutral)'
                                : sentimentData.score < 85
                                ? 'var(--sentiment-greed)'
                                : 'var(--sentiment-extreme-greed)',
                          }}
                        >
                          {sentimentData.score}
                        </div>
                        <div>
                          <div className="flex items-center gap-2 mb-1">
                            <SentimentBadge sentiment={sentimentData.label} size="md" />
                          </div>
                          <p className="text-xs text-gray-400">综合情绪评分</p>
                          <p className="text-xs text-gray-500 mt-1">
                            净值 {selectedFund.nav.toFixed(4)} | 日收益{' '}
                            <span className={selectedFund.daily_return >= 0 ? 'text-red-500' : 'text-green-500'}>
                              {selectedFund.daily_return >= 0 ? '+' : ''}
                              {selectedFund.daily_return.toFixed(2)}%
                            </span>
                          </p>
                        </div>
                      </div>

                      {/* 操作建议 */}
                      <div
                        className={clsx(
                          'rounded-xl p-4 flex items-start gap-3',
                          sentimentData.advice.level === '积极'
                            ? 'bg-green-50 border border-green-200'
                            : sentimentData.advice.level === '谨慎'
                            ? 'bg-red-50 border border-red-200'
                            : 'bg-blue-50 border border-blue-200'
                        )}
                      >
                        <div
                          className={clsx(
                            'w-10 h-10 rounded-full flex items-center justify-center shrink-0',
                            sentimentData.advice.level === '积极'
                              ? 'bg-green-500'
                              : sentimentData.advice.level === '谨慎'
                              ? 'bg-red-500'
                              : 'bg-blue-500'
                          )}
                        >
                          {sentimentData.advice.level === '积极' ? (
                            <TrendingUp className="w-5 h-5 text-white" />
                          ) : sentimentData.advice.level === '谨慎' ? (
                            <AlertTriangle className="w-5 h-5 text-white" />
                          ) : (
                            <Shield className="w-5 h-5 text-white" />
                          )}
                        </div>
                        <div>
                          <p className="font-bold text-gray-800">{sentimentData.advice.action}</p>
                          <p className="text-xs text-gray-500 mt-0.5">{sentimentData.advice.reason}</p>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* 多周期信号灯 */}
                  {sentimentData && (
                    <div className="bg-gray-50 rounded-xl p-4">
                      <h4 className="text-xs font-bold text-gray-500 uppercase mb-3">多周期信号灯</h4>
                      <div className="flex items-center gap-6">
                        <div className="flex flex-col items-center gap-1">
                          <span className="text-[10px] text-gray-400">短期</span>
                          <div
                            className="w-6 h-6 rounded-full"
                            style={{
                              background:
                                sentimentData.shortTerm === 'extreme_fear'
                                  ? 'var(--sentiment-extreme-fear)'
                                  : sentimentData.shortTerm === 'fear'
                                  ? 'var(--sentiment-fear)'
                                  : sentimentData.shortTerm === 'neutral'
                                  ? 'var(--sentiment-neutral)'
                                  : sentimentData.shortTerm === 'greed'
                                  ? 'var(--sentiment-greed)'
                                  : 'var(--sentiment-extreme-greed)',
                            }}
                          />
                        </div>
                        <div className="flex flex-col items-center gap-1">
                          <span className="text-[10px] text-gray-400">中期</span>
                          <div
                            className="w-6 h-6 rounded-full"
                            style={{
                              background:
                                sentimentData.midTerm === 'extreme_fear'
                                  ? 'var(--sentiment-extreme-fear)'
                                  : sentimentData.midTerm === 'fear'
                                  ? 'var(--sentiment-fear)'
                                  : sentimentData.midTerm === 'neutral'
                                  ? 'var(--sentiment-neutral)'
                                  : sentimentData.midTerm === 'greed'
                                  ? 'var(--sentiment-greed)'
                                  : 'var(--sentiment-extreme-greed)',
                            }}
                          />
                        </div>
                        <div className="flex flex-col items-center gap-1">
                          <span className="text-[10px] text-gray-400">长期</span>
                          <div
                            className="w-6 h-6 rounded-full"
                            style={{
                              background:
                                sentimentData.longTerm === 'extreme_fear'
                                  ? 'var(--sentiment-extreme-fear)'
                                  : sentimentData.longTerm === 'fear'
                                  ? 'var(--sentiment-fear)'
                                  : sentimentData.longTerm === 'neutral'
                                  ? 'var(--sentiment-neutral)'
                                  : sentimentData.longTerm === 'greed'
                                  ? 'var(--sentiment-greed)'
                                  : 'var(--sentiment-extreme-greed)',
                            }}
                          />
                        </div>
                        {sentimentData.hasDivergence && (
                          <div className="flex items-center gap-1.5 ml-2 px-3 py-1.5 rounded-full bg-yellow-100">
                            <AlertTriangle className="w-3.5 h-3.5 text-yellow-600" />
                            <span className="text-xs font-medium text-yellow-700">
                              {sentimentData.divergenceType === 'bullish' ? '底背离' : '顶背离'}
                            </span>
                          </div>
                        )}
                      </div>
                    </div>
                  )}

                  {/* 板块情绪一致性检查 */}
                  {sentimentData && (
                    <div className="bg-gray-50 rounded-xl p-4">
                      <h4 className="text-xs font-bold text-gray-500 uppercase mb-3">板块情绪一致性</h4>
                      <div className="space-y-2">
                        {sentimentData.sectorCheck.map((sc, i) => (
                          <div key={i} className="flex items-center justify-between py-1.5">
                            <div className="flex items-center gap-3">
                              <span className="text-sm text-gray-700 font-medium w-16">{sc.sector}</span>
                              <div className="flex items-center gap-2">
                                <span className="text-xs text-gray-400">基金:</span>
                                <div className="w-20 h-1.5 bg-gray-200 rounded-full overflow-hidden">
                                  <div
                                    className="h-full rounded-full"
                                    style={{
                                      width: `${sc.fund_sentiment}%`,
                                      background: `var(--sentiment-${
                                        sc.fund_sentiment < 30
                                          ? 'extreme_fear'
                                          : sc.fund_sentiment < 50
                                          ? 'fear'
                                          : sc.fund_sentiment < 70
                                          ? 'neutral'
                                          : sc.fund_sentiment < 85
                                          ? 'greed'
                                          : 'extreme_greed'
                                      })`,
                                    }}
                                  />
                                </div>
                              </div>
                              <div className="flex items-center gap-2">
                                <span className="text-xs text-gray-400">板块:</span>
                                <div className="w-20 h-1.5 bg-gray-200 rounded-full overflow-hidden">
                                  <div
                                    className="h-full rounded-full"
                                    style={{
                                      width: `${sc.sector_sentiment}%`,
                                      background: `var(--sentiment-${
                                        sc.sector_sentiment < 30
                                          ? 'extreme_fear'
                                          : sc.sector_sentiment < 50
                                          ? 'fear'
                                          : sc.sector_sentiment < 70
                                          ? 'neutral'
                                          : sc.sector_sentiment < 85
                                          ? 'greed'
                                          : 'extreme_greed'
                                      })`,
                                    }}
                                  />
                                </div>
                              </div>
                            </div>
                            <span
                              className={clsx(
                                'text-xs font-medium px-2 py-0.5 rounded',
                                sc.consistent
                                  ? 'bg-green-100 text-green-600'
                                  : 'bg-orange-100 text-orange-600'
                              )}
                            >
                              {sc.consistent ? '一致' : '背离'}
                            </span>
                          </div>
                        ))}
                      </div>
                    </div>
                  )}

                  {/* 小板块趋势明细 + 5日微趋势条 */}
                  {sentimentData && (
                    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                      <div className="bg-gray-50 rounded-xl p-4">
                        <h4 className="text-xs font-bold text-gray-500 uppercase mb-3">小板块趋势明细</h4>
                        <div className="space-y-2">
                          {[
                            { name: '白酒', momentum: 2.3, trend: 'up' as TrendDirection },
                            { name: '医药', momentum: -1.2, trend: 'down' as TrendDirection },
                            { name: '半导体', momentum: 3.8, trend: 'up' as TrendDirection },
                            { name: '银行', momentum: 0.5, trend: 'stable' as TrendDirection },
                            { name: '军工', momentum: -0.8, trend: 'down' as TrendDirection },
                          ].map((sector) => (
                            <div key={sector.name} className="flex items-center justify-between text-xs">
                              <span className="text-gray-600 w-12">{sector.name}</span>
                              <div className="flex-1 mx-3 h-1 bg-gray-200 rounded-full overflow-hidden">
                                <div
                                  className={clsx(
                                    'h-full rounded-full',
                                    sector.trend === 'up'
                                      ? 'bg-red-400'
                                      : sector.trend === 'down'
                                      ? 'bg-green-400'
                                      : 'bg-gray-400'
                                  )}
                                  style={{ width: `${Math.min(100, Math.abs(sector.momentum) * 15 + 20)}%` }}
                                />
                              </div>
                              <span
                                className={clsx(
                                  'font-mono w-14 text-right',
                                  sector.momentum > 0 ? 'text-red-500' : sector.momentum < 0 ? 'text-green-500' : 'text-gray-400'
                                )}
                              >
                                {sector.momentum > 0 ? '+' : ''}
                                {sector.momentum.toFixed(1)}%
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>

                      <div className="bg-gray-50 rounded-xl p-4">
                        <h4 className="text-xs font-bold text-gray-500 uppercase mb-3">5日微趋势</h4>
                        <MicroTrendBar data={sentimentData.microTrend} />
                        <div className="flex justify-between mt-1">
                          {sentimentData.microTrend.map((pt, i) => (
                            <span key={i} className="text-[10px] text-gray-400">
                              {pt.date.slice(5)}
                            </span>
                          ))}
                        </div>
                      </div>
                    </div>
                  )}

                  {/* 基金基本信息 */}
                  {detailData && (
                    <div className="bg-gray-50 rounded-xl p-4">
                      <h4 className="text-xs font-bold text-gray-500 uppercase mb-3">基金信息</h4>
                      <div className="grid grid-cols-2 md:grid-cols-4 gap-3 text-sm">
                        <div>
                          <span className="text-xs text-gray-400">基金公司</span>
                          <p className="font-medium text-gray-700">{detailData.company}</p>
                        </div>
                        <div>
                          <span className="text-xs text-gray-400">基金经理</span>
                          <p className="font-medium text-gray-700">{detailData.manager}</p>
                        </div>
                        <div>
                          <span className="text-xs text-gray-400">成立日期</span>
                          <p className="font-medium text-gray-700">{detailData.inception_date}</p>
                        </div>
                        <div>
                          <span className="text-xs text-gray-400">累计净值</span>
                          <p className="font-medium text-gray-700 font-mono">{detailData.accumulated_nav.toFixed(4)}</p>
                        </div>
                        <div className="md:col-span-2">
                          <span className="text-xs text-gray-400">业绩基准</span>
                          <p className="font-medium text-gray-700 text-xs">{detailData.benchmark}</p>
                        </div>
                        <div className="md:col-span-2">
                          <span className="text-xs text-gray-400">跟踪指数</span>
                          <p className="font-medium text-gray-700">
                            {detailData.tracking_index || '无（主动管理型）'}
                          </p>
                        </div>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          )}
        </div>
      ) : keyword ? (
        <div className="card p-8 text-center">
          <Search className="w-10 h-10 text-gray-300 mx-auto mb-3" />
          <p className="text-gray-400">未找到相关基金</p>
          <p className="text-xs text-gray-300 mt-1">请尝试其他关键词</p>
        </div>
      ) : (
        <div className="card p-8 text-center">
          <Search className="w-10 h-10 text-gray-300 mx-auto mb-3" />
          <p className="text-gray-400">请输入关键词搜索基金</p>
          <p className="text-xs text-gray-300 mt-1">支持按代码、名称模糊搜索</p>
        </div>
      )}

      {/* 内联动画 keyframes */}
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
