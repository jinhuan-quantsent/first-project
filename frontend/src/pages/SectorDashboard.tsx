/**
 * SectorDashboard — 板块情绪 + 机会雷达页面
 *
 * Tab 切换:
 *  - 板块情绪: 31个板块V5评分列表
 *  - 机会雷达: 双轨制推荐引擎
 */
import { useState } from 'react';
import SectorSentimentPanel from '../components/sector/SectorSentimentPanel';
import SectorRadarPanel from '../components/sector/SectorRadarPanel';
import { clsx } from 'clsx';
import { Layers, Radar } from 'lucide-react';

type Tab = 'sentiment' | 'radar';

const TABS: { value: Tab; label: string; icon: typeof Layers }[] = [
  { value: 'sentiment', label: '板块情绪', icon: Layers },
  { value: 'radar',     label: '机会雷达', icon: Radar },
];

export default function SectorDashboard() {
  const [tab, setTab] = useState<Tab>('sentiment');

  return (
    <div className="max-w-7xl mx-auto space-y-3 md:space-y-6 px-1">
      {/* 标题 */}
      <div>
        <h1 className="text-xl md:text-2xl font-bold text-gray-800">板块情绪 V5.0</h1>
        <p className="text-xs md:text-sm text-gray-400 mt-1">
          5因子三层流水线 | 双轨制推荐 | 31个申万一级行业
        </p>
      </div>

      {/* Tab 切换 */}
      <div className="flex items-center gap-2 border-b border-gray-100">
        {TABS.map((t) => (
          <button
            key={t.value}
            onClick={() => setTab(t.value)}
            className={clsx(
              'flex items-center gap-1.5 px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px',
              tab === t.value
                ? 'text-brand-600 border-brand-500'
                : 'text-gray-400 border-transparent hover:text-gray-600',
            )}
          >
            <t.icon className="w-4 h-4" />
            {t.label}
          </button>
        ))}
      </div>

      {/* Tab 内容 */}
      {tab === 'sentiment' ? <SectorSentimentPanel /> : <SectorRadarPanel />}
    </div>
  );
}
