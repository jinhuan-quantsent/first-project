import { useEffect, useState } from 'react';
import { useAppStore } from '../store';
import SentimentBadge from '../components/common/SentimentBadge';
import SignalLights from '../components/common/SignalLights';
import LoadingSpinner from '../components/common/LoadingSpinner';
import ErrorMessage from '../components/common/ErrorMessage';
import { Star, AlertTriangle, TrendingUp, TrendingDown, Minus } from 'lucide-react';
import { clsx } from 'clsx';
import type { SignalLevel } from '../types';
import { fetchV5Sentiment, fetchV5FactorHeatmap, type V5FactorDetail } from '../api/marketV5';

const SIGNAL_COLORS: Record<string, string> = {
  'S+': '#059669', 'S': '#10B981', 'A': '#6EE7B7', 'B': '#FBBF24',
  'C': '#FCA5A5', 'D': '#EF4444', 'E': '#DC2626',
};

const SIGNAL_LABELS: Record<string, string> = {
  'S+': '极度恐惧', 'S': '恐惧', 'A': '偏恐惧', 'B': '中性',
  'C': '偏贪婪', 'D': '贪婪', 'E': '极度贪婪',
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
        <p className="text-xs md:text-sm text-gray-400 mt-1">11因子流水线 | 7级信号 | 4星置信度</p>
      </div>

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
            <div className="grid grid-cols-3 gap-4 mb-4">
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
            <div className={clsx(
              'rounded-lg p-4',
              selected.signal_level === 'S+' || selected.signal_level === 'S'
                ? 'bg-green-50 border border-green-200'
                : selected.signal_level === 'D' || selected.signal_level === 'E'
                ? 'bg-red-50 border border-red-200'
                : 'bg-gray-50 border border-gray-200'
            )}>
              <div className="flex items-center gap-2 mb-2">
                {selected.signal_level === 'S+' || selected.signal_level === 'S' ? (
                  <TrendingUp className="w-5 h-5 text-green-500" />
                ) : selected.signal_level === 'D' || selected.signal_level === 'E' ? (
                  <TrendingDown className="w-5 h-5 text-red-500" />
                ) : (
                  <Minus className="w-5 h-5 text-gray-400" />
                )}
                <span className="font-bold text-gray-800">
                  {selected.composite_score < 38 ? '逢低关注' :
                   selected.composite_score < 52 ? '持有观望' :
                   selected.composite_score < 65 ? '适度参与' : '注意风险'}
                </span>
              </div>
              <p className="text-xs text-gray-500">
                建议仓位:{' '}
                {selected.composite_score < 38 ? '25%' :
                 selected.composite_score < 52 ? '50%' :
                 selected.composite_score < 65 ? '75%' : '25%'}
              </p>
              <p className="text-xs text-gray-400 mt-1">
                基于信号 {SIGNAL_LABELS[selected.signal_level]}，置信度 {selected.confidence_stars} 星
              </p>
            </div>
          </div>
        </div>
      )}

      {/* 11因子概览 */}
      <div className="card p-5">
        <h3 className="text-sm font-bold text-gray-700 mb-3">
          11因子引擎概览
          {factorsLoading && <span className="ml-2 text-xs text-gray-400 font-normal">加载中...</span>}
        </h3>
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-6 gap-2">
          {FACTOR_DEFS.map(renderFactorCard)}
        </div>
      </div>
    </div>
  );
}
