import { useState, useEffect, useRef } from 'react';
import { fetchIndexDetail } from '../../api/market';
import type { IndexDetail } from '../../types';
import SentimentBadge from '../common/SentimentBadge';
import SignalLights from '../common/SignalLights';
import MicroTrendBar from '../common/MicroTrendBar';
import LoadingSpinner from '../common/LoadingSpinner';
import ErrorMessage from '../common/ErrorMessage';
import { clsx } from 'clsx';
import { TrendingUp, TrendingDown, Minus, AlertTriangle } from 'lucide-react';

interface IndexDetailPanelProps {
  indexCode: string;
}

export default function IndexDetailPanel({ indexCode }: IndexDetailPanelProps) {
  const [data, setData] = useState<IndexDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const prevDataRef = useRef<IndexDetail | null>(null);
  const [animating, setAnimating] = useState(false);

  useEffect(() => {
    let cancelled = false;
    setLoading(true);
    setError(null);

    fetchIndexDetail(indexCode)
      .then((result) => {
        if (cancelled) return;
        prevDataRef.current = data;
        setData(result);
        setAnimating(true);
        setTimeout(() => setAnimating(false), 300);
        setLoading(false);
      })
      .catch((err) => {
        if (cancelled) return;
        setError('加载指数详情失败');
        setLoading(false);
      });

    return () => { cancelled = true; };
  }, [indexCode]);

  if (loading) return <LoadingSpinner text="加载指数详情..." />;
  if (error) return <ErrorMessage message={error} />;
  if (!data) return null;

  const trendIcon = data.trend_direction === 'up'
    ? <TrendingUp className="w-4 h-4 text-red-500" />
    : data.trend_direction === 'down'
    ? <TrendingDown className="w-4 h-4 text-green-500" />
    : <Minus className="w-4 h-4 text-gray-400" />;

  return (
    <div className={clsx('card p-5', animating && 'cross-fade-enter cross-fade-enter-active')}>
      {/* 标题栏 */}
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-3">
          <h2 className="text-base font-bold text-gray-800">{data.index_name}</h2>
          <SentimentBadge sentiment={data.sentiment_label} size="md" variant="table" />
        </div>
        <div className="flex items-center gap-2">
          {data.is_extreme && (
            <span className="flex items-center gap-1 text-xs text-orange-500 font-medium">
              <AlertTriangle className="w-3 h-3" />
              极端信号
            </span>
          )}
          <div className="flex items-center gap-1 text-xs text-gray-500">
            {trendIcon}
            <span>趋势强度: {data.trend_strength.toFixed(0)}</span>
          </div>
        </div>
      </div>

      {/* 核心数据行 */}
      <div className="flex items-baseline gap-4 mb-4">
        <div>
          <span className="text-2xl font-bold text-gray-800 font-mono">
            {data.composite_score.toFixed(0)}
          </span>
          <span className="text-sm text-gray-400 ml-1">/100</span>
        </div>
        <div className="text-xs text-gray-400">
          点位: <span className="font-mono text-gray-600">{data.close.toFixed(2)}</span>
          <span className={clsx('ml-1', data.change_pct >= 0 ? 'text-market-up' : 'text-market-down')}>
            {data.change_pct >= 0 ? '+' : ''}{data.change_pct.toFixed(2)}%
          </span>
        </div>
      </div>

      {/* 三周期信号灯 + 微趋势 */}
      <div className="flex items-center gap-4 mb-4 p-3 bg-gray-50 rounded-lg">
        <div className="flex items-center gap-2">
          <span className="text-xs text-gray-500">信号:</span>
          <SignalLights
            shortTerm={data.sentiment_label}
            midTerm={data.sentiment_label}
            longTerm={data.sentiment_label}
            hasDivergence={data.is_extreme}
            divergenceType={data.composite_score < 40 ? 'bullish' : 'bearish'}
          />
        </div>
        <div className="flex-1 max-w-[200px]">
          <MicroTrendBar data={data.history?.slice(-5) || []} />
        </div>
      </div>

      {/* 7因子评分条 */}
      <div className="space-y-2">
        <h3 className="text-xs font-medium text-gray-500 uppercase tracking-wide">七因子评分</h3>
        {Object.entries(data.factor_scores).map(([name, factor]) => {
          const barColor = factor.score < 35
            ? 'bg-sentiment-extreme_fear'
            : factor.score < 45
            ? 'bg-sentiment-fear'
            : factor.score < 55
            ? 'bg-sentiment-neutral'
            : factor.score < 70
            ? 'bg-sentiment-greed'
            : 'bg-sentiment-extreme_greed';

          return (
            <div key={name} className="flex items-center gap-3">
              <span className="w-16 text-xs text-gray-500 shrink-0">{name}</span>
              <div className="flex-1 h-2 bg-gray-100 rounded-full overflow-hidden">
                <div
                  className={clsx('h-full rounded-full transition-all duration-500', barColor)}
                  style={{ width: `${factor.score}%` }}
                />
              </div>
              <span className="w-10 text-xs text-right font-mono text-gray-600">
                {factor.score.toFixed(0)}
              </span>
              {factor.is_extreme && (
                <span className="text-[10px] text-orange-500 font-medium shrink-0">
                  {factor.extreme_type === 'oversold' ? '超卖' : '超买'}
                </span>
              )}
            </div>
          );
        })}
      </div>

      {/* 仓位建议 */}
      {data.position_advice && (
        <div className="mt-4 p-3 bg-blue-50 rounded-lg">
          <div className="flex items-center justify-between mb-1">
            <span className="text-xs font-medium text-blue-700">仓位建议</span>
            <span className="text-xs text-blue-500">
              建议仓位: <strong>{data.position_advice.suggested_position}%</strong>
              {' / '}现金: {data.position_advice.cash_reserve}%
            </span>
          </div>
          <p className="text-xs text-blue-600">{data.position_advice.reason}</p>
        </div>
      )}

      {/* 操作建议 */}
      <div className="mt-3 p-3 bg-gray-50 rounded-lg">
        <p className="text-xs text-gray-600">{data.operation_advice}</p>
      </div>

      {/* 结论 */}
      <p className="mt-3 text-sm text-gray-700 font-medium">{data.conclusion}</p>
    </div>
  );
}
