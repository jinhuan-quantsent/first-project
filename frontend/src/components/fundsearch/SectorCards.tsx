/**
 * SectorCards - 板块情绪卡片网格
 * 从 /api/v5/market/sectors 获取真实板块数据
 * 按"有利度"排序（恐惧=买入机会=排前），悬停上浮，点击查看详情
 */
import { useState, useEffect } from 'react';
import type { SignalLevel } from '../../types';
import { ChevronRight, RefreshCw } from 'lucide-react';
import { clsx } from 'clsx';
import client from '../../api/client';

/** 信号等级有利度排序权重：恐惧=买入机会=有利→排前，贪婪=风险→排后 */
const SIGNAL_FAVOR_ORDER: Record<SignalLevel, number> = {
  'S+': 0, 'S': 1, 'A': 2, 'B': 3, 'C': 4, 'D': 5, 'E': 6,
};

interface SectorCardData {
  sector_code: string;
  sector_name: string;
  signal_level: SignalLevel;
  sentiment_score: number;
  momentum_5d: number;
  strength_index: number;
  change_pct?: number;
  main_net_inflow?: number;
}

const SIGNAL_BG: Record<SignalLevel, string> = {
  'S+': 'bg-signal-sp/10 border-signal-sp/30',
  'S':  'bg-signal-s/10  border-signal-s/30',
  'A':  'bg-signal-s/10  border-signal-s/20',
  'B':  'bg-signal-b/10  border-signal-b/30',
  'C':  'bg-signal-c/10  border-signal-c/30',
  'D':  'bg-signal-d/10  border-signal-d/30',
  'E':  'bg-signal-e/10  border-signal-e/30',
};

const SIGNAL_DOT: Record<SignalLevel, string> = {
  'S+': 'bg-signal-sp', 'S': 'bg-signal-s', 'A': 'bg-signal-a',
  'B': 'bg-signal-b', 'C': 'bg-signal-c', 'D': 'bg-signal-d', 'E': 'bg-signal-e',
};

/** 将涨跌幅映射为情绪信号等级 */
function changeToSignal(changePct: number): SignalLevel {
  if (changePct <= -3) return 'S+';
  if (changePct <= -2) return 'S';
  if (changePct <= -1) return 'A';
  if (changePct <= 1) return 'B';
  if (changePct <= 2) return 'C';
  if (changePct <= 3) return 'D';
  return 'E';
}

/** 将涨跌幅映射为情绪分数(0-100) */
function changeToScore(changePct: number): number {
  return Math.round(Math.max(0, Math.min(100, 50 + changePct * 10)));
}

interface SectorCardsProps {
  onSelect?: (sector: SectorCardData) => void;
}

export default function SectorCards({ onSelect }: SectorCardsProps) {
  const [sectors, setSectors] = useState<SectorCardData[]>([]);
  const [loading, setLoading] = useState(true);
  const [sectorType, setSectorType] = useState<'concept' | 'industry'>('concept');

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      try {
        const res = await client.get('/api/v5/market/sectors', {
          params: { sector_type: sectorType, page_size: 8, sort_by: 'change_pct', sort_order: 'asc' },
        });
        if (cancelled) return;
        const items = res.data?.data?.items || res.data?.data || [];
        // 将API数据映射为SectorCardData
        const mapped: SectorCardData[] = items.slice(0, 8).map((item: any) => {
          const changePct = item.change_pct ?? 0;
          return {
            sector_code: item.code || item.sector_code || '',
            sector_name: item.name || item.sector_name || '',
            signal_level: changeToSignal(changePct),
            sentiment_score: changeToScore(changePct),
            momentum_5d: changePct,
            strength_index: Math.round(Math.max(0, Math.min(100, 50 + (item.main_pct || 0) * 5))),
            change_pct: changePct,
            main_net_inflow: item.main_net_inflow,
          };
        });
        setSectors(mapped);
      } catch {
        // 降级：保留空数组
        setSectors([]);
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [sectorType]);

  if (loading) {
    return (
      <div>
        <h3 className="text-sm font-bold text-gray-700 mb-2">板块情绪</h3>
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2 animate-pulse">
          {Array.from({ length: 8 }, (_, i) => (
            <div key={i} className="h-20 bg-gray-200 rounded-lg" />
          ))}
        </div>
      </div>
    );
  }

  /** 按"有利度"排序 */
  const sortedSectors = [...sectors].sort((a, b) => {
    const favDiff = SIGNAL_FAVOR_ORDER[a.signal_level] - SIGNAL_FAVOR_ORDER[b.signal_level];
    if (favDiff !== 0) return favDiff;
    return a.sentiment_score - b.sentiment_score;
  });

  return (
    <div>
      <div className="flex items-center justify-between mb-2">
        <h3 className="text-sm font-bold text-gray-700">
          板块情绪 <span className="text-[10px] font-normal text-gray-400">按有利度排序</span>
        </h3>
        <div className="flex items-center gap-2">
          <select
            value={sectorType}
            onChange={(e) => setSectorType(e.target.value as any)}
            className="text-xs border rounded px-2 py-1 bg-white text-gray-600"
          >
            <option value="concept">概念板块</option>
            <option value="industry">行业板块</option>
          </select>
        </div>
      </div>
      {sortedSectors.length === 0 ? (
        <div className="text-xs text-gray-400 py-4 text-center">暂无板块数据</div>
      ) : (
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2">
          {sortedSectors.map((s) => (
            <button
              key={s.sector_code}
              onClick={() => onSelect?.(s)}
              className={clsx(
                'text-left p-3 rounded-lg border transition-all duration-200',
                'hover:-translate-y-0.5 hover:shadow-md',
                SIGNAL_BG[s.signal_level] || SIGNAL_BG['B'],
              )}
            >
              <div className="flex items-center justify-between mb-1.5">
                <span className="text-xs font-medium text-gray-700 truncate">{s.sector_name}</span>
                <div className={clsx('w-2 h-2 rounded-full shrink-0', SIGNAL_DOT[s.signal_level])} />
              </div>
              <div className="flex items-center gap-1.5 text-[10px] text-gray-400">
                <span>情绪 {s.sentiment_score}</span>
                <span>·</span>
                <span className={s.momentum_5d >= 0 ? 'text-red-500' : 'text-green-500'}>
                  {s.momentum_5d >= 0 ? '+' : ''}{s.momentum_5d.toFixed(1)}%
                </span>
              </div>
              <div className="flex items-center gap-1 mt-1.5 text-[10px] text-gray-400">
                <span>强度 {s.strength_index}</span>
                <ChevronRight className="w-3 h-3 ml-auto" />
              </div>
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
