/**
 * SectorCards - 板块情绪卡片网格
 * 8板块自适应网格，按"有利度"排序（恐惧=买入机会=排前），悬停上浮，点击查看详情
 */
import type { SignalLevel } from '../../types';
import { ChevronRight } from 'lucide-react';
import { clsx } from 'clsx';

/** 信号等级有利度排序权重：恐惧=买入机会=有利→排前，贪婪=风险→排后 */
const SIGNAL_FAVOR_ORDER: Record<SignalLevel, number> = {
  'S+': 0,  // 极度恐惧 → 最有利
  'S':  1,  // 恐惧
  'A':  2,  // 偏恐惧
  'B':  3,  // 中性
  'C':  4,  // 偏贪婪
  'D':  5,  // 贪婪
  'E':  6,  // 极度贪婪 → 最不利
};

interface SectorCardData {
  sector_code: string;
  sector_name: string;
  signal_level: SignalLevel;
  sentiment_score: number;
  momentum_5d: number;
  strength_index: number;
}

const DUMMY_SECTORS: SectorCardData[] = [
  { sector_code: 'BK001', sector_name: '大消费',   signal_level: 'S',  sentiment_score: 22, momentum_5d: 1.2,  strength_index: 65 },
  { sector_code: 'BK002', sector_name: '科技TMT',  signal_level: 'A',  sentiment_score: 35, momentum_5d: 2.5,  strength_index: 58 },
  { sector_code: 'BK003', sector_name: '新能源',   signal_level: 'C',  sentiment_score: 42, momentum_5d: -0.8, strength_index: 45 },
  { sector_code: 'BK004', sector_name: '医药生物',  signal_level: 'B',  sentiment_score: 48, momentum_5d: 0.5,  strength_index: 52 },
  { sector_code: 'BK005', sector_name: '军工国防',  signal_level: 'D',  sentiment_score: 68, momentum_5d: 3.1,  strength_index: 72 },
  { sector_code: 'BK006', sector_name: '金融地产',  signal_level: 'A',  sentiment_score: 28, momentum_5d: -1.2, strength_index: 42 },
  { sector_code: 'BK007', sector_name: '周期材料',  signal_level: 'B',  sentiment_score: 50, momentum_5d: 0.3,  strength_index: 50 },
  { sector_code: 'BK008', sector_name: '港股通',   signal_level: 'S+', sentiment_score: 15, momentum_5d: -2.1, strength_index: 35 },
];

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
  'S+': 'bg-signal-sp',
  'S':  'bg-signal-s',
  'A':  'bg-signal-a',
  'B':  'bg-signal-b',
  'C':  'bg-signal-c',
  'D':  'bg-signal-d',
  'E':  'bg-signal-e',
};

interface SectorCardsProps {
  sectors?: SectorCardData[];
  loading?: boolean;
  onSelect?: (sector: SectorCardData) => void;
}

export default function SectorCards({
  sectors = DUMMY_SECTORS,
  loading = false,
  onSelect,
}: SectorCardsProps) {
  if (loading) {
    return (
      <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-2 animate-pulse">
        {Array.from({ length: 8 }, (_, i) => (
          <div key={i} className="h-20 bg-gray-200 rounded-lg" />
        ))}
      </div>
    );
  }

  /** 按"有利度"排序：恐惧信号（买入机会）排前，贪婪信号（风险）排后；同等级内按 sentiment_score 降序 */
  const sortedSectors = [...sectors].sort((a, b) => {
    const favDiff = SIGNAL_FAVOR_ORDER[a.signal_level] - SIGNAL_FAVOR_ORDER[b.signal_level];
    if (favDiff !== 0) return favDiff;
    return b.sentiment_score - a.sentiment_score;
  });

  return (
    <div>
      <h3 className="text-sm font-bold text-gray-700 mb-2">板块情绪 <span className="text-[10px] font-normal text-gray-400">按有利度排序</span></h3>
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
              <span className="text-xs font-medium text-gray-700 truncate">
                {s.sector_name}
              </span>
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
    </div>
  );
}
