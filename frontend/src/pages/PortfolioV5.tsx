/**
 * PortfolioV5 - 持仓页重设计 V5
 * 总览头部 + 列表行 + 详情展开面板
 * 对齐设计稿 Image4 + Image5
 */
import { useState, useCallback, useEffect } from 'react';
import type { PortfolioItem, PortfolioSummary, SignalLevel } from '../types';
import { SIGNAL_LABELS } from '../types';
import PositionDetailPanel, { type PositionDetailData } from '../components/portfolio/PositionDetailPanel';
import { Briefcase, Pencil, ChevronDown, ChevronUp } from 'lucide-react';
import { clsx } from 'clsx';
import {
  fetchPortfolioV5,
  executePositionV5,
} from '../api/portfolioV5';
import { fetchV5Sentiment } from '../api/marketV5';
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
function generateMockDetailData(
  item: PortfolioItem,
  signal: { signalLevel: SignalLevel; confidenceStars: number } | undefined,
  navHistory: number[] | undefined,
  topStocks: { name: string; pct: number; change: number }[] | undefined,
  evaluation: any | undefined,
): PositionDetailData {
  const signalLevel = signal?.signalLevel ?? 'B';
  const signalLabel = SIGNAL_LABELS[signalLevel] ?? '中性';
  const operationTag: PositionDetailData['operationTag'] =
    signalLevel === 'S+' || signalLevel === 'S' ? '加仓' :
    signalLevel === 'D' || signalLevel === 'E' ? '减仓' :
    signalLevel === 'A' ? '买入' : '持有';

  return {
    fundCode: item.fund_code,
    fundName: (item as any).fund_short_name || item.fund_name,
    marketValue: item.market_value,
    dailyReturn: item.daily_return,
    holdingReturn: item.total_return,
    holdingReturnRate: item.return_rate,
    signalLevel,
    confidenceStars: signal?.confidenceStars ?? 3,
    signalReason: `${signalLevel}·${signalLabel}，近期波动较大`,

    complianceStars: 4.5,
    complianceDirection: 'new',
    operationTag,
    recommendationReason: `基于${signalLabel}信号分析，当前市场情绪处于${signalLabel}区间，建议${operationTag}。该基金近期表现${item.return_rate >= 0 ? '优于' : '弱于'}基准，仓位调整需谨慎。`,
    updateNote: `更新市值${formatMoney(item.market_value)}（${item.return_rate >= 0 ? '涨' : '跌'}${Math.abs(item.return_rate).toFixed(1)}%）`,

    winRate: 72 + Math.floor(Math.random() * 16),
    winRateDetail: `近1年${8 + Math.floor(Math.random() * 8)}场博弈`,
    performanceRecords: [
      { date: '2024-06-18', signal: 'S+', operation: '减仓', correctUp: true, correctDown: false, returnPct: -9.17, reason: '触发预警，51周新高分警惕!' },
      { date: '2024-06-12', signal: '✓', operation: '减仓', correctUp: true, correctDown: false, returnPct: -47.3, reason: '剧烈波动分散降低风险+2%' },
      { date: '2024-06-05', signal: '⚠', operation: '持有', correctUp: false, correctDown: true, returnPct: 8.3, reason: '新能源行情，小幅减仓锁定收益' },
      { date: '2024-05-28', signal: 'S', operation: '加仓', correctUp: true, correctDown: false, returnPct: 3.2, reason: '底部信号确认，分批加仓' },
      { date: '2024-05-20', signal: '△', operation: '持有', correctUp: false, correctDown: true, returnPct: -1.5, reason: '市场观望期，维持仓位' },
    ],

    tradeRecords: [
      { date: '2024-06-18', type: '买入', amount: 15000, nav: 1.7140, fee: 127.88 },
      { date: '2024-05-15', type: '买入', amount: 20000, nav: 1.1170, fee: 148.21 },
      { date: '2024-04-02', type: '卖出', amount: 16600, nav: 1.1740, fee: 79.23 },
      { date: '2024-03-13', type: '持有', amount: 122, nav: 0, fee: 0 },
    ],

    navHistory: navHistory?.map((nav, i) => ({
      date: new Date(Date.now() - (navHistory.length - i) * 86400000).toISOString().slice(0, 10),
      nav,
    })) ?? [],

    topHoldings: topStocks?.map(s => ({
      name: s.name,
      pct: s.pct * 100,
      description: s.name.includes('半导体') ? '半导体设备龙头，国产替代核心标的' :
        s.name.includes('金山') ? '办公软件龙头，AI赋能收入增速预期' :
        s.name.includes('中兴') ? '通信设备主业，产研投研能力领先' :
        `${s.name}核心标的`,
    })) ?? [
      { name: '中微公司', pct: 9.82, description: '半导体设备龙头，国产替代核心标的' },
      { name: '金山办公', pct: 8.45, description: '办公软件龙头，AI赋能收入增速预期' },
      { name: '中兴通讯', pct: 7.43, description: '通信设备主业，产研投研能力领先' },
      { name: '兆易创新', pct: 6.21, description: '存储芯片龙头，受益AI算力需求' },
    ],

    morningStarRating: 4,
    ratingDetails: [
      '近1年夏普比率排名靠前',
      'T2指数排名处于前30%',
      '波动率低于同类平均',
    ],

    todayEvaluation: `净值估${item.daily_return >= 0 ? '增' : '减'}${Math.abs(item.daily_return).toFixed(1)}%，半导体板块全线回暖`,
    shortTerm: { label: '看多', reason: '板块轮动' },
    midTerm: { label: '看多', reason: 'AI算力' },
    longTerm: { label: '看多', reason: '半导体' },
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
   持仓列表行组件
   ============================================================ */
function PositionRow({
  item,
  expanded,
  onToggle,
  signal,
}: {
  item: PortfolioItem;
  expanded: boolean;
  onToggle: () => void;
  signal: { signalLevel: SignalLevel; confidenceStars: number } | undefined;
}) {
  const fundShortName = (item as any).fund_short_name || item.fund_name;
  const daily = formatChangeValue(item.daily_return);
  const holding = formatChangeValue(item.total_return);
  const holdingRate = formatChangeRate(item.return_rate);
  const signalLevel = signal?.signalLevel;
  const signalLabel = signalLevel ? SIGNAL_LABELS[signalLevel] : '';

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
        <div className="shrink-0 flex items-center gap-1 min-w-[100px]">
          <span className="text-sm font-bold text-gray-800 font-mono">{formatMoney(item.market_value)}</span>
          <button
            onClick={(e) => { e.stopPropagation(); }}
            className="text-gray-300 hover:text-[var(--brand-cyan)] transition-colors"
            title="编辑持仓"
          >
            <Pencil className="w-3 h-3" />
          </button>
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
  const [signals, setSignals] = useState<Record<string, { signalLevel: SignalLevel; confidenceStars: number }>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // 增强数据
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
                }] as [string, { signalLevel: SignalLevel; confidenceStars: number }];
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

        const signalMap: Record<string, { signalLevel: SignalLevel; confidenceStars: number }> = {};
        signalEntries.forEach((entry) => {
          if (entry) signalMap[entry[0]] = entry[1];
        });
        setSignals(signalMap);

        // 从详情API提取增强数据
        const realNavHistories: Record<string, number[]> = {};
        const realTopStocks: Record<string, { name: string; pct: number; change: number }[]> = {};
        const realEvaluations: Record<string, any> = {};

        detailEntries.forEach((entry) => {
          if (!entry) return;
          const [code, detail] = entry;

          const navH = detail.nav_history || [];
          if (navH.length > 1) {
            realNavHistories[code] = navH.map((p: any) => p.nav || p.adj_nav || 0).filter((v: number) => v > 0);
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
        });

        setNavHistories(realNavHistories);
        setTopStocksMap(realTopStocks);
        setEvaluationsMap(realEvaluations);
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
            const detailData = generateMockDetailData(
              item,
              signals[item.fund_code],
              navHistories[item.fund_code],
              topStocksMap[item.fund_code],
              evaluationsMap[item.fund_code],
            );

            return (
              <div key={item.id}>
                {/* 列表行 */}
                <PositionRow
                  item={item}
                  expanded={isExpanded}
                  onToggle={() => toggleExpand(item.id)}
                  signal={signals[item.fund_code]}
                />

                {/* 展开详情面板 */}
                {isExpanded && (
                  <PositionDetailPanel
                    data={detailData}
                    onCollapse={() => setExpandedId(null)}
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
