/**
 * 背离预警横幅 — Dashboard 顶部预警
 * 检测到底部背离 → 买入机会提示
 * 检测到顶部背离 → 风险提示
 */
import { useEffect, useState } from 'react';
import { fetchDivergenceAlerts, type DivergenceAlert } from '../../api/marketV5';
import { AlertTriangle, TrendingUp, TrendingDown, X, ShieldCheck } from 'lucide-react';

export default function DivergenceBanner() {
  const [alerts, setAlerts] = useState<DivergenceAlert[]>([]);
  const [allClear, setAllClear] = useState(true);
  const [loading, setLoading] = useState(true);
  const [dismissed, setDismissed] = useState(false);

  useEffect(() => {
    let cancelled = false;
    const load = async () => {
      try {
        const data = await fetchDivergenceAlerts();
        if (!cancelled) {
          setAlerts(data.alerts);
          setAllClear(data.all_clear);
        }
      } catch {
        // 静默失败
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    load();
    return () => { cancelled = true; };
  }, []);

  if (loading || dismissed) return null;

  // 无预警时显示绿色安全横幅
  if (allClear || alerts.length === 0) {
    return (
      <div className="bg-green-50 border border-green-200 rounded-lg px-4 py-2 flex items-center justify-between">
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-4 h-4 text-green-500" />
          <span className="text-xs text-green-700">未检测到背离信号，市场情绪与走势基本一致</span>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-2">
      {alerts.map((alert, i) => {
        const isBottom = alert.divergence_type.includes('底部') || alert.divergence_type.includes('bullish');
        const Icon = isBottom ? TrendingUp : TrendingDown;
        const bgColor = isBottom ? 'bg-green-50 border-green-200' : 'bg-red-50 border-red-200';
        const iconColor = isBottom ? 'text-green-600' : 'text-red-600';
        const textColor = isBottom ? 'text-green-800' : 'text-red-800';
        const subTextColor = isBottom ? 'text-green-600' : 'text-red-600';
        const tagText = isBottom ? '买入机会' : '风险提示';
        const tagBg = isBottom ? 'bg-green-100 text-green-700' : 'bg-red-100 text-red-700';

        return (
          <div key={i} className={`${bgColor} border rounded-lg px-4 py-3 flex items-start gap-3`}>
            <Icon className={`w-5 h-5 ${iconColor} shrink-0 mt-0.5`} />
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className={`text-xs font-bold ${textColor}`}>
                  {alert.index_name || alert.index_code}
                </span>
                <span className={`text-[10px] px-1.5 py-0.5 rounded font-medium ${tagBg}`}>
                  {tagText}
                </span>
                <span className="text-[10px] text-gray-400">
                  强度 {alert.strength.toFixed(1)}
                </span>
              </div>
              <p className={`text-xs ${subTextColor} mt-1`}>
                {alert.description || `${alert.divergence_type}：价格${alert.price_trend} vs 情绪${alert.sentiment_trend}`}
              </p>
            </div>
            <button
              onClick={() => setDismissed(true)}
              className="text-gray-300 hover:text-gray-500 shrink-0"
              aria-label="关闭预警"
            >
              <X className="w-3.5 h-3.5" />
            </button>
          </div>
        );
      })}
    </div>
  );
}
