import { useEffect, useState } from 'react';
import { useAppStore } from '../store';
import SentimentBadge from '../components/common/SentimentBadge';
import SignalLights from '../components/common/SignalLights';
import LoadingSpinner from '../components/common/LoadingSpinner';
import ErrorMessage from '../components/common/ErrorMessage';
import FactorRadarChart from '../components/dashboard/FactorRadarChart';
import DivergenceBanner from '../components/dashboard/DivergenceBanner';
import SignalVerifyBoard from '../components/dashboard/SignalVerifyBoard';
import { Star, AlertTriangle, TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { clsx } from 'clsx';
import { SIGNAL_COLORS_HEX as SIGNAL_COLORS, SIGNAL_LABELS, type SignalLevel } from '../types';
import { fetchV5Sentiment, fetchV5FactorHeatmap, type V5FactorDetail } from '../api/marketV5';

/** 信号等级 → 仓位建议映射（V5.0 5×7矩阵简化版） */
const POSITION_ADVICE: Record<string, { action: string; position: string; risk: string }> = {
  'S+': { action: '大幅加仓', position: '70%-80%', risk: '极度恐惧区域，市场可能处于底部' },
  'S':  { action: '逢低加仓', position: '60%-70%', risk: '恐惧情绪明显，分批布局' },
  'A':  { action: '适度加仓', position: '50%-60%', risk: '偏恐惧，关注超跌机会' },
  'B':  { action: '持有观望', position: '45%-50%', risk: '中性，保持均衡配置' },
  'C':  { action: '小幅减仓', position: '35%-45%', risk: '偏乐观，可锁定部分利润' },
  'D':  { action: '逐步减仓', position: '25%-35%', risk: '市场乐观，落袋为安' },
  'E':  { action: '减仓避险', position: '10%-20%', risk: '极度贪婪，市场可能见顶' },
};

interface V5IndexData {
  index_code: string;
  index_name: string;
  composite_score: number;
  signal_level: string;
  confidence_stars: number;
  regime: string;
}

/** 因子显示定义 */
const FACTOR_DEFS = [
  { name: 'VOL', label: '波动率', dir: 'fear' },
  { name: 'ADR', label: '涨跌比', dir: 'greed' },
  { name: 'ERP', label: '股债比', dir: 'fear' },
  { name: 'FLOW', label: '资金流', dir: 'greed' },
  { name: 'ETF', label: 'ETF变动', dir: 'greed' },
  { name: 'NHNL', label: '新高占比', dir: 'greed' },
  { name: 'TURN', label: '换手率', dir: 'fear' },
  { name: 'POS', label: '基金仓位', dir: 'greed' },
  { name: 'NBF', label: '北向资金', dir: 'greed' },
  { name: 'PCR', label: '认沽认购比', dir: 'fear' },
  { name: 'NEWF', label: '新发热度', dir: 'greed' },
  { name: 'MARGIN', label: '融资融券', dir: 'greed' },
  { name: 'RSI', label: 'RSI指标', dir: 'fear' },
  { name: 'INDUSTRY_DIVERGENCE', label: '行业分歧', dir: 'fear' },
  { name: 'DIVERGENCE', label: 'MACD背离', dir: 'fear' },
] as const;

export default function DashboardV5() {
  const { marketLoading, marketError, loadMultiIndex, selectedIndex, setSelectedIndex, multiIndexData } = useAppStore();
  const [indexes, setIndexes] = useState<V5IndexData[]>([]);
  const [factorDetails, setFactorDetails] = useState<V5FactorDetail[]>([]);
  const [factorsLoading, setFactorsLoading] = useState(false);

  useEffect(() => {
    loadMultiIndex();
  }, [loadMultiIndex]);

  /** 当multiIndexData更新时，映射到页面格式 */
  useEffect(() => {
    if (multiIndexData && multiIndexData.length > 0) {
      const mapped: V5IndexData[] = multiIndexData.map((idx: any) => ({
        index_code: idx.index_code,
        index_name: idx.index_name,
        composite_score: idx.composite_score ?? 0,
        signal_level: idx.signal_level ?? 'B',
        confidence_stars: idx.confidence_stars ?? 2,
        regime: idx.trend_direction === 'up' ? 'bull' : idx.trend_direction === 'down' ? 'bear' : 'sideways',
      }));
      setIndexes(mapped);
    }
  }, [multiIndexData]);

  /** 选中指数变化时，获取因子热力图 */
  useEffect(() => {
    if (!selectedIndex) return;
    let cancelled = false;
    const loadFactors = async () => {
      setFactorsLoading(true);
      try {
        const heatmap = await fetchV5FactorHeatmap(selectedIndex);
        if (!cancelled) {
          setFactorDetails(heatmap.factors || []);
        }
      } catch {
        // 因子数据获取失败不阻塞页面
        if (!cancelled) setFactorDetails([]);
      } finally {
        if (!cancelled) setFactorsLoading(false);
      }
    };
    loadFactors();
    return () => { cancelled = true; };
  }, [selectedIndex]);

  if (marketLoading && indexes.length === 0) {
    return <LoadingSpinner size="lg" text="加载市场数据..." />;
  }

  if (marketError && indexes.length === 0) {
    return <ErrorMessage message={marketError} onRetry={() => loadMultiIndex()} />;
  }

  const selected = indexes.find((i) => i.index_code === selectedIndex) || indexes[0];

  /** 渲染因子概览卡片 - 优先用真实数据，无数据时显示方向标签 */
  const renderFactorCard = (def: typeof FACTOR_DEFS[number]) => {
    const realFactor = factorDetails.find((f) =>
      f.factor_name === def.name || f.factor_name.toUpperCase() === def.name
    );
    if (realFactor) {
      const scoreColor = realFactor.sigmoid_score >= 60 ? 'text-red-500' :
                         realFactor.sigmoid_score <= 40 ? 'text-green-500' : 'text-gray-600';
      return (
        <div key={def.name} className="bg-gray-50 rounded-lg p-2 text-center">
          <p className="text-xs text-gray-400">{def.label}</p>
          <p className="text-xs font-mono text-gray-600">{def.name}</p>
          <p className={`text-xs font-bold ${scoreColor}`}>
            {realFactor.sigmoid_score.toFixed(1)}
          </p>
          <span className={clsx(
            'text-[10px] px-1 py-0.5 rounded',
            realFactor.direction === 'fear' ? 'bg-red-100 text-red-500' : 'bg-green-100 text-green-500'
          )}>
            {realFactor.direction === 'fear' ? '恐惧' : '贪婪'}
          </span>
        </div>
      );
    }
    // 无真实数据时显示默认方向
    return (
      <div key={def.name} className="bg-gray-50 rounded-lg p-2 text-center opacity-60">
        <p className="text-xs text-gray-400">{def.label}</p>
        <p className="text-xs font-mono text-gray-600">{def.name}</p>
        <span className={clsx(
          'text-[10px] px-1 py-0.5 rounded',
          def.dir === 'fear' ? 'bg-red-100 text-red-500' : 'bg-green-100 text-green-500'
        )}>
          {def.dir === 'fear' ? '恐惧' : '贪婪'}
        </span>
      </div>
    );
  };

  return (
    <div className="max-w-7xl mx-auto space-y-4 md:space-y-6">
      <div>
        <h1 className="text-xl md:text-2xl font-bold text-gray-800">大盘情绪仪表盘 V5.0</h1>
        <p className="text-xs md:text-sm text-gray-400 mt-1">14因子流水线 | 7级信号 | 4星置信度</p>
      </div>

      {/* 背离预警横幅 */}
      <DivergenceBanner />

      {/* 多指数卡片 */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-3">
        {indexes.map((idx) => (
          <div
            key={idx.index_code}
            onClick={() => setSelectedIndex(idx.index_code)}
            className={clsx(
              'card p-4 cursor-pointer transition-all hover:shadow-md',
              selectedIndex === idx.index_code && 'ring-2 ring-brand-500'
            )}
          >
            <div className="flex items-center justify-between mb-2">
              <span className="text-xs text-gray-400">{idx.index_name}</span>
              <span className="text-xs font-mono text-gray-300">{idx.index_code}</span>
            </div>
            <div className="flex items-center gap-3">
              <div
                className="w-12 h-12 rounded-full flex items-center justify-center text-white text-lg font-bold"
                style={{ background: SIGNAL_COLORS[idx.signal_level] || '#94A3B8' }}
              >
                {Math.round(idx.composite_score)}
              </div>
              <div>
                <div className="flex items-center gap-1.5">
                  <SentimentBadge level={idx.signal_level as SignalLevel} size="sm" />
                  <div className="flex gap-0.5">
                    {[1, 2, 3, 4].map((s) => (
                      <Star
                        key={s}
                        className={clsx(
                          'w-3 h-3',
                          s <= idx.confidence_stars ? 'text-yellow-400 fill-yellow-400' : 'text-gray-200'
                        )}
                      />
                    ))}
                  </div>
                </div>
                <p className="text-xs text-gray-400 mt-0.5">
                  体制: {idx.regime === 'bull' ? '牛市' : idx.regime === 'bear' ? '熊市' : idx.regime === 'extreme_volatility' ? '极端波动' : '震荡'}
                </p>
              </div>
            </div>
          </div>
        ))}
      </div>

      {/* 指数详情 + 信号灯 */}
      {selected && (
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
          <div className="lg:col-span-2 card p-5">
            <h3 className="text-sm font-bold text-gray-700 mb-3">{selected.index_name} - V5.0 情绪详情</h3>
            <div className="grid grid-cols-3 gap-2 md:gap-4 mb-4">
              <div className="text-center">
                <p className="text-xs text-gray-400">综合分</p>
                <p className="text-2xl font-bold" style={{ color: SIGNAL_COLORS[selected.signal_level] }}>
                  {selected.composite_score.toFixed(1)}
                </p>
              </div>
              <div className="text-center">
                <p className="text-xs text-gray-400">信号等级</p>
                <p className="text-lg font-bold" style={{ color: SIGNAL_COLORS[selected.signal_level] }}>
                  {selected.signal_level}
                </p>
                <p className="text-xs text-gray-500">{SIGNAL_LABELS[selected.signal_level]}</p>
              </div>
              <div className="text-center">
                <p className="text-xs text-gray-400">置信度</p>
                <div className="flex justify-center gap-0.5 mt-1">
                  {[1, 2, 3, 4].map((s) => (
                    <Star
                      key={s}
                      className={clsx(
                        'w-5 h-5',
                        s <= selected.confidence_stars ? 'text-yellow-400 fill-yellow-400' : 'text-gray-200'
                      )}
                    />
                  ))}
                </div>
              </div>
            </div>

            {/* 信号灯 */}
            <div className="bg-gray-50 rounded-lg p-3">
              <p className="text-xs text-gray-400 mb-2">多周期信号灯</p>
              <SignalLights
                shortTerm={selected.signal_level as SignalLevel}
                midTerm={(selected.signal_level === 'B' ? 'C' : 'B') as SignalLevel}
                longTerm={(selected.signal_level === 'B' ? 'A' : 'B') as SignalLevel}
                size="md"
              />
            </div>
          </div>

          <div className="card p-5">
            <h3 className="text-sm font-bold text-gray-700 mb-3">操作建议</h3>
            {(() => {
              const advice = POSITION_ADVICE[selected.signal_level] || POSITION_ADVICE['B'];
              const isBuy = ['S+', 'S', 'A'].includes(selected.signal_level);
              const isSell = ['D', 'E'].includes(selected.signal_level);
              return (
                <div className={clsx(
                  'rounded-lg p-4',
                  isBuy ? 'bg-green-50 border border-green-200'
                  : isSell ? 'bg-red-50 border border-red-200'
                  : 'bg-gray-50 border border-gray-200'
                )}>
                  <div className="flex items-center gap-2 mb-2">
                    {isBuy ? (
                      <TrendingUp className="w-5 h-5 text-green-500" />
                    ) : isSell ? (
                      <TrendingDown className="w-5 h-5 text-red-500" />
                    ) : (
                      <Minus className="w-5 h-5 text-gray-400" />
                    )}
                    <span className="font-bold text-gray-800">{advice.action}</span>
                  </div>
                  <p className="text-xs text-gray-500">
                    建议仓位: {advice.position}
                  </p>
                  <p className="text-xs text-gray-400 mt-1">
                    {advice.risk} · 信号 {selected.signal_level} · 置信度 {selected.confidence_stars} 星
                  </p>
                </div>
              );
            })()}
          </div>
        </div>
      )}

      {/* 14因子概览 */}
      <div className="card p-5">
        <h3 className="text-sm font-bold text-gray-700 mb-3">
          14因子引擎概览
          {factorsLoading && <span className="ml-2 text-xs text-gray-400 font-normal">加载中...</span>}
        </h3>
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-1.5 sm:gap-2">
          {FACTOR_DEFS.map(renderFactorCard)}
        </div>
      </div>

      {/* Phase D: 因子雷达图 + 信号验证看板 */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <div className="card p-5">
          <h3 className="text-sm font-bold text-gray-700 mb-3">因子雷达图</h3>
          <FactorRadarChart indexCode={selectedIndex || 'SH000300'} />
        </div>
        <div className="card p-5">
          <h3 className="text-sm font-bold text-gray-700 mb-3">信号验证看板</h3>
          <SignalVerifyBoard indexCode={selectedIndex || 'SH000300'} />
        </div>
      </div>
    </div>
  );
}
