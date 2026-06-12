import { useState, useEffect } from 'react';
import { fetchIndexDetail } from '../../api/market';
import type { FactorScoreData } from '../../types';
import LoadingSpinner from '../common/LoadingSpinner';
import { clsx } from 'clsx';
import { AlertTriangle, TrendingUp, TrendingDown } from 'lucide-react';

interface Top3FactorsProps {
  indexCode: string;
}

export default function Top3Factors({ indexCode }: Top3FactorsProps) {
  const [factors, setFactors] = useState<FactorScoreData[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    setLoading(true);
    fetchIndexDetail(indexCode)
      .then((data) => {
        setFactors(data.top3_factors || []);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, [indexCode]);

  if (loading) {
    return (
      <div className="card p-4">
        <LoadingSpinner size="sm" text="加载因子..." />
      </div>
    );
  }

  if (factors.length === 0) {
    return (
      <div className="card p-4">
        <p className="text-xs text-gray-400 text-center">暂无因子数据</p>
      </div>
    );
  }

  return (
    <div className="card p-4">
      <h3 className="text-sm font-bold text-gray-700 mb-3">Top3 关键因子</h3>

      <div className="space-y-3">
        {factors.map((factor, i) => {
          const isWarning = factor.is_extreme;
          const deviation = factor.score - 50;
          const isLow = factor.score < 50;

          return (
            <div
              key={factor.factor_name}
              className={clsx(
                'p-3 rounded-lg border transition-all',
                isWarning
                  ? 'border-orange-200 bg-orange-50'
                  : 'border-gray-100 bg-gray-50'
              )}
            >
              {/* 排名 + 因子名 */}
              <div className="flex items-center justify-between mb-2">
                <div className="flex items-center gap-2">
                  <span className={clsx(
                    'w-5 h-5 rounded-full flex items-center justify-center text-xs font-bold',
                    i === 0 ? 'bg-yellow-400 text-white' :
                    i === 1 ? 'bg-gray-300 text-white' :
                    'bg-orange-200 text-orange-700'
                  )}>
                    {i + 1}
                  </span>
                  <span className="text-sm font-medium text-gray-700">{factor.factor_name}</span>
                </div>
                {isWarning && (
                  <AlertTriangle className="w-4 h-4 text-orange-500" />
                )}
              </div>

              {/* 评分条 */}
              <div className="flex items-center gap-2 mb-1">
                <div className="flex-1 h-2 bg-gray-200 rounded-full overflow-hidden">
                  <div
                    className={clsx(
                      'h-full rounded-full transition-all',
                      factor.score < 35 ? 'bg-sentiment-extreme_fear' :
                      factor.score < 45 ? 'bg-sentiment-fear' :
                      factor.score < 55 ? 'bg-sentiment-neutral' :
                      factor.score < 70 ? 'bg-sentiment-greed' :
                      'bg-sentiment-extreme_greed'
                    )}
                    style={{ width: `${factor.score}%` }}
                  />
                </div>
                <span className="text-sm font-bold text-gray-700 font-mono">
                  {factor.score.toFixed(0)}
                </span>
              </div>

              {/* 偏离信息 */}
              <div className="flex items-center gap-2 text-xs">
                <span className={clsx(
                  'font-medium',
                  isLow ? 'text-green-600' : 'text-red-500'
                )}>
                  偏离中性 {Math.abs(deviation).toFixed(0)}分
                  {isLow ? ' ↓ 偏恐慌' : ' ↑ 偏乐观'}
                </span>
                {factor.extreme_type && (
                  <span className="text-orange-500 font-medium">
                    {factor.extreme_type === 'oversold' ? '[超卖信号]' : '[超买信号]'}
                  </span>
                )}
              </div>
            </div>
          );
        })}
      </div>

      {/* 风险提示 */}
      {factors.some(f => f.is_extreme) && (
        <div className="mt-3 p-2 bg-orange-50 border border-orange-200 rounded text-xs text-orange-600">
          检测到极端因子信号，请关注市场风险
        </div>
      )}
    </div>
  );
}
