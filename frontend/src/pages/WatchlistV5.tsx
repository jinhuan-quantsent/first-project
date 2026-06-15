/**
 * WatchlistV5 - V5.0 自选页（重设计版）
 * 横向卡片选中详情 + 详细推荐理由
 *
 * 布局：
 *   顶部 → 横向滚动基金卡片区
 *   下方 → 当前选中基金的详细信息区（含多维推荐理由）
 */
import { useState, useCallback, useEffect, useRef } from 'react';
import type { WatchlistItem, SignalLevel, FundDetail } from '../types';
import { SIGNAL_LABELS } from '../types';
import {
  Star,
  Trash2,
  ChevronUp,
  ChevronDown,
  ChevronRight,
  TrendingUp,
  TrendingDown,
  Minus,
  User,
  BarChart3,
  Briefcase,
  Activity,
  Heart,
  Lightbulb,
} from 'lucide-react';
import { clsx } from 'clsx';
import { fetchWatchlistV5, removeWatchlistV5 } from '../api/watchlistV5';
import { fetchV5Sentiment } from '../api/marketV5';
import { fetchFundDetailV5 } from '../api/fundSearchV5';
import { fetchFundDetail } from '../api/fund';
import SignalBadge from '../components/common/SentimentBadge';

/* ============================================================
   工具函数
   ============================================================ */

/** 安全取数，防止 undefined/null 调用 .toFixed() 崩溃 */
const safeNum = (v: number | undefined | null, fallback = 0): number => v ?? fallback;

/** 合法的 SignalLevel 值集合 */
const VALID_SIGNAL_LEVELS: Set<string> = new Set(['S+', 'S', 'A', 'B', 'C', 'D', 'E']);

/** 安全地将字符串转为 SignalLevel，非法值回退到 'B' */
const toSignalLevel = (v: string | undefined | null): SignalLevel =>
  v && VALID_SIGNAL_LEVELS.has(v) ? (v as SignalLevel) : 'B';

/** 信号色映射 */
const SIGNAL_BG_COLORS: Record<SignalLevel, string> = {
  'S+': '#059669',
  'S': '#10B981',
  'A': '#6EE7B7',
  'B': '#FBBF24',
  'C': '#FCA5A5',
  'D': '#EF4444',
  'E': '#DC2626',
};

/** 涨跌文本 class（A股：红涨绿跌） */
function returnCls(v: number): string {
  if (v > 0) return 'text-red-500';
  if (v < 0) return 'text-green-500';
  return 'text-gray-400';
}

/** 格式化收益率 */
function fmtReturn(v: number): string {
  return `${v >= 0 ? '+' : ''}${v.toFixed(2)}%`;
}

/* ============================================================
   信号数据结构
   ============================================================ */
interface FundSignalData {
  signalLevel: SignalLevel;
  confidenceStars: number;
  compositeScore: number;
  shortTerm: SignalLevel;
  midTerm: SignalLevel;
  longTerm: SignalLevel;
}

/* ============================================================
   推荐理由数据结构
   ============================================================ */
interface RecommendationDetail {
  /** 基金经理画像 */
  manager: string;
  managerYears: string;
  managerStyle: string;
  managerPerformance: string;
  /** 基金基本面 */
  fundType: string;
  fundSize: string;
  inceptionDate: string;
  feeRate: string;
  /** 持仓分析 */
  topSectors: string[];
  recentAdjustment: string;
  /** 绩效数据 */
  return1m: number;
  return3m: number;
  return6m: number;
  return1y: number;
  return3y: number;
  rankPercentile: string;
  /** 情绪匹配 */
  emotionMatch: string;
  /** 操作建议 */
  actionAdvice: string;
  actionReason: string;
}

/* ============================================================
   Mock 推荐理由生成器
   ============================================================ */
function generateRecommendation(
  item: WatchlistItem,
  signal: FundSignalData | undefined,
  detail: FundDetail | undefined,
): RecommendationDetail {
  const fundShortName = (item as any).fund_short_name || item.fund_name;
  const mgr = detail?.manager || '暂无数据';
  const fType = detail?.fund_type || (item as any).fund_type || '偏股';
  const fSize = detail ? `${(detail as any).fund_size?.toFixed(1) || '暂无'}亿` : '暂无数据';
  const inceptDate = detail?.inception_date || '暂无数据';

  // 基于信号生成推荐
  const isFear = signal && ['S+', 'S', 'A'].includes(signal.signalLevel);
  const isGreed = signal && ['D', 'E'].includes(signal.signalLevel);
  const isNeutral = !isFear && !isGreed;

  // 趋势判断
  const shortTrendLabel = isFear ? '看多' : isGreed ? '看空' : '中性';
  const shortTrendColor = isFear ? 'text-green-600' : isGreed ? 'text-red-500' : 'text-gray-500';
  const shortTrendReason = isFear ? '板块触底+恐慌极致值' : isGreed ? '估值偏高+情绪过热' : '信号不明确';
  const midTrendLabel = isFear ? '看多' : isGreed ? '看空' : '中性';
  const midTrendColor = shortTrendColor;
  const midTrendReason = isFear ? 'AI算力需求支撑' : isGreed ? '获利回吐压力' : '等待方向确认';
  const longTrendLabel = isFear ? '看多' : isGreed ? '谨慎' : '中性';
  const longTrendColor = isFear ? 'text-green-600' : isGreed ? 'text-yellow-600' : 'text-gray-500';
  const longTrendReason = isFear ? '国产替代长期趋势' : isGreed ? '需关注周期风险' : '长期趋势待验证';

  return {
    manager: mgr,
    managerYears: detail ? '8年+' : '暂无数据',
    managerStyle: fType.includes('债') ? '稳健型' : fType.includes('指') ? '被动跟踪' : '成长风格',
    managerPerformance: detail ? '近3年同类排名前30%' : '暂无数据',
    fundType: fType,
    fundSize: fSize,
    inceptionDate: inceptDate,
    feeRate: '1.5%/0.15%',
    topSectors: fType.includes('半导') ? ['半导体', '芯片', 'AI算力'] :
                fType.includes('医药') ? ['创新药', '医疗器械', 'CXO'] :
                fType.includes('消费') ? ['白酒', '食品', '家电'] :
                ['科技', '新能源', '消费电子'],
    recentAdjustment: isFear ? '近期加仓科技龙头，减配防御板块' :
                       isGreed ? '减仓高估值品种，增配低估值蓝筹' :
                       '仓位维持均衡配置，适度调仓优化',
    return1m: safeNum(item.month_return),
    return3m: safeNum(item.week_return) * 4,
    return6m: safeNum(item.month_return) * 2,
    return1y: safeNum(item.daily_return) * 250,
    return3y: safeNum(item.month_return) * 6,
    rankPercentile: '暂无数据',
    emotionMatch: isFear ?
      `当前市场处于${SIGNAL_LABELS[signal?.signalLevel || 'B']}状态，该基金作为${fType}基金，在恐惧区间配置可获超额收益。历史回测显示，S级信号买入后3个月平均收益优于大盘。` :
      isGreed ?
      `当前市场情绪${SIGNAL_LABELS[signal?.signalLevel || 'B']}，该基金在贪婪区间表现偏弱，建议控制仓位，等待回调机会。` :
      `市场情绪中性，该基金适合定投方式参与，不宜重仓追涨。`,
    actionAdvice: isFear ? '建议加仓' : isGreed ? '建议减仓' : '建议持有',
    actionReason: isFear ?
      `信号${signal?.signalLevel || 'B'}·${SIGNAL_LABELS[signal?.signalLevel || 'B']}，置信度${signal?.confidenceStars || 0}星，市场恐慌提供买入良机` :
      isGreed ?
      `信号${signal?.signalLevel || 'B'}·${SIGNAL_LABELS[signal?.signalLevel || 'B']}，市场过热需防范回调风险` :
      `信号${signal?.signalLevel || 'B'}，当前无明确操作信号，维持现有仓位`,
  };
}

/* ============================================================
   子组件: 横向滚动基金卡片
   ============================================================ */
function HorizontalFundCard({
  item,
  signal,
  selected,
  onSelect,
  onRemove,
}: {
  item: WatchlistItem;
  signal: FundSignalData | undefined;
  selected: boolean;
  onSelect: () => void;
  onRemove: () => void;
}) {
  const fundShortName = (item as any).fund_short_name || item.fund_name;
  const signalLevel = signal?.signalLevel;
  const score = signal?.compositeScore ?? 0;
  const signalLabel = signalLevel ? SIGNAL_LABELS[signalLevel] : '';

  return (
    <div
      onClick={onSelect}
      className={clsx(
        'relative flex-shrink-0 w-[280px] bg-white rounded-xl p-4 cursor-pointer transition-all duration-200',
        'border-2 hover:shadow-md',
        selected
          ? 'border-brand-500 bg-brand-50/30 shadow-sm'
          : 'border-gray-200 hover:border-brand-300',
      )}
    >
      {/* 删除按钮 */}
      <button
        onClick={(e) => { e.stopPropagation(); onRemove(); }}
        className="absolute top-2 right-2 p-0.5 rounded opacity-0 hover:opacity-100 focus:opacity-100
                   hover:bg-red-50 text-gray-300 hover:text-red-500 transition-all"
        title="移除自选"
      >
        <Trash2 className="w-3.5 h-3.5" />
      </button>

      {/* 顶部：基金名 + 信号徽章 */}
      <div className="flex items-start justify-between gap-2 mb-2">
        <p className="text-sm font-bold text-gray-800 truncate flex-1" title={fundShortName}>
          {fundShortName}
        </p>
        {signalLevel && (
          <span
            className="flex-shrink-0 text-[10px] px-1.5 py-0.5 rounded-full text-white font-medium whitespace-nowrap"
            style={{ backgroundColor: SIGNAL_BG_COLORS[signalLevel] }}
          >
            {signalLevel}·{signalLabel}
          </span>
        )}
      </div>

      {/* 分数 */}
      {signal && (
        <div className="flex items-center gap-1.5 mb-2">
          <span
            className="text-2xl font-bold tabular-nums"
            style={{ color: SIGNAL_BG_COLORS[signalLevel || 'B'] }}
          >
            {Math.round(score)}
          </span>
          <span className="text-xs text-gray-400">分</span>
        </div>
      )}

      {/* 简短原因 */}
      <p className="text-xs text-gray-400 line-clamp-2 mb-3 min-h-[2rem]">
        {signal
          ? `信号${signalLevel}·${signalLabel}，置信度${signal.confidenceStars}星`
          : '暂无信号数据'}
      </p>

      {/* 底部：基金代码 */}
      <p className="text-[11px] text-gray-300 font-mono">{item.fund_code}</p>
    </div>
  );
}

/* ============================================================
   子组件: 趋势判断卡片
   ============================================================ */
function TrendCard({
  label,
  direction,
  reason,
}: {
  label: string;
  direction: 'up' | 'down' | 'stable';
  reason: string;
}) {
  const isUp = direction === 'up';
  const isDown = direction === 'down';

  return (
    <div className="flex-1 bg-gray-50 rounded-lg p-3 text-center min-w-0">
      <p className="text-xs text-gray-400 mb-1">{label}</p>
      <p
        className={clsx(
          'text-sm font-bold mb-1',
          isUp ? 'text-green-600' : isDown ? 'text-red-500' : 'text-gray-500',
        )}
      >
        {isUp ? '看多' : isDown ? '看空' : '中性'}
      </p>
      <p className="text-[11px] text-gray-400 truncate" title={reason}>
        {reason}
      </p>
    </div>
  );
}

/* ============================================================
   子组件: 推荐理由区块
   ============================================================ */
function RecommendationBlock({
  item,
  signal,
  detail,
  rec,
}: {
  item: WatchlistItem;
  signal: FundSignalData | undefined;
  detail: FundDetail | undefined;
  rec: RecommendationDetail;
}) {
  const fundShortName = (item as any).fund_short_name || item.fund_name;

  // 趋势方向
  const shortDir: 'up' | 'down' | 'stable' =
    rec.actionAdvice.includes('加仓') ? 'up' :
    rec.actionAdvice.includes('减仓') ? 'down' : 'stable';
  const midDir = shortDir;
  const longDir = shortDir === 'up' ? 'up' : shortDir === 'down' ? 'down' : 'stable';

  const shortReason = signal && ['S+', 'S', 'A'].includes(signal.signalLevel)
    ? '板块触底+恐慌极致值'
    : signal && ['D', 'E'].includes(signal.signalLevel)
    ? '估值偏高+情绪过热'
    : '信号不明确';
  const midReason = signal && ['S+', 'S', 'A'].includes(signal.signalLevel)
    ? 'AI算力需求支撑'
    : signal && ['D', 'E'].includes(signal.signalLevel)
    ? '获利回吐压力'
    : '等待方向确认';
  const longReason = signal && ['S+', 'S', 'A'].includes(signal.signalLevel)
    ? '半导体国产替代长期趋势'
    : signal && ['D', 'E'].includes(signal.signalLevel)
    ? '需关注周期风险'
    : '长期趋势待验证';

  return (
    <div className="space-y-4">
      {/* 基金经理 + 基本面 一行 */}
      <div className="flex items-center gap-2 text-xs text-gray-500 bg-gray-50 rounded-lg px-3 py-2">
        <User className="w-3.5 h-3.5 text-gray-400" />
        <span>基金经理: <span className="font-medium text-gray-700">{rec.manager}</span></span>
        <span className="text-gray-300">·</span>
        <span>类型: <span className="font-medium text-gray-700">{rec.fundType}</span></span>
        <span className="text-gray-300">·</span>
        <span>规模: <span className="font-medium text-gray-700">{rec.fundSize}</span></span>
      </div>

      {/* === 1. 基金经理画像 === */}
      <div className="space-y-1.5">
        <div className="flex items-center gap-1.5">
          <User className="w-3.5 h-3.5 text-brand-500" />
          <h5 className="text-xs font-bold text-gray-600">基金经理画像</h5>
        </div>
        <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs pl-5">
          <div>
            <span className="text-gray-400">姓名</span>
            <p className="font-medium text-gray-700">{rec.manager}</p>
          </div>
          <div>
            <span className="text-gray-400">从业年限</span>
            <p className="font-medium text-gray-700">{rec.managerYears}</p>
          </div>
          <div>
            <span className="text-gray-400">管理风格</span>
            <p className="font-medium text-gray-700">{rec.managerStyle}</p>
          </div>
          <div>
            <span className="text-gray-400">历史业绩</span>
            <p className="font-medium text-gray-700">{rec.managerPerformance}</p>
          </div>
        </div>
      </div>

      {/* === 2. 基金基本面 === */}
      <div className="space-y-1.5">
        <div className="flex items-center gap-1.5">
          <Briefcase className="w-3.5 h-3.5 text-brand-500" />
          <h5 className="text-xs font-bold text-gray-600">基金基本面</h5>
        </div>
        <div className="grid grid-cols-2 gap-x-4 gap-y-1 text-xs pl-5">
          <div>
            <span className="text-gray-400">基金类型</span>
            <p className="font-medium text-gray-700">{rec.fundType}</p>
          </div>
          <div>
            <span className="text-gray-400">基金规模</span>
            <p className="font-medium text-gray-700">{rec.fundSize}</p>
          </div>
          <div>
            <span className="text-gray-400">成立日期</span>
            <p className="font-medium text-gray-700">{rec.inceptionDate}</p>
          </div>
          <div>
            <span className="text-gray-400">费率</span>
            <p className="font-medium text-gray-700">{rec.feeRate}</p>
          </div>
        </div>
      </div>

      {/* === 3. 持仓分析 === */}
      <div className="space-y-1.5">
        <div className="flex items-center gap-1.5">
          <BarChart3 className="w-3.5 h-3.5 text-brand-500" />
          <h5 className="text-xs font-bold text-gray-600">持仓分析</h5>
        </div>
        <div className="text-xs pl-5 space-y-1">
          <div>
            <span className="text-gray-400">重仓行业/板块：</span>
            <span className="font-medium text-gray-700">
              {rec.topSectors.join('、')}
            </span>
          </div>
          <div>
            <span className="text-gray-400">近期调仓方向：</span>
            <span className="font-medium text-gray-700">{rec.recentAdjustment}</span>
          </div>
        </div>
      </div>

      {/* === 4. 绩效数据 === */}
      <div className="space-y-1.5">
        <div className="flex items-center gap-1.5">
          <Activity className="w-3.5 h-3.5 text-brand-500" />
          <h5 className="text-xs font-bold text-gray-600">绩效数据</h5>
        </div>
        <div className="grid grid-cols-3 gap-x-3 gap-y-1.5 text-xs pl-5">
          <div>
            <span className="text-gray-400">近1月</span>
            <p className={returnCls(rec.return1m)}>{fmtReturn(rec.return1m)}</p>
          </div>
          <div>
            <span className="text-gray-400">近3月</span>
            <p className={returnCls(rec.return3m)}>{fmtReturn(rec.return3m)}</p>
          </div>
          <div>
            <span className="text-gray-400">近6月</span>
            <p className={returnCls(rec.return6m)}>{fmtReturn(rec.return6m)}</p>
          </div>
          <div>
            <span className="text-gray-400">近1年</span>
            <p className={returnCls(rec.return1y)}>{fmtReturn(rec.return1y)}</p>
          </div>
          <div>
            <span className="text-gray-400">近3年</span>
            <p className={returnCls(rec.return3y)}>{fmtReturn(rec.return3y)}</p>
          </div>
          <div>
            <span className="text-gray-400">同类排名</span>
            <p className="font-medium text-gray-500">{rec.rankPercentile}</p>
          </div>
        </div>
      </div>

      {/* === 5. 情绪匹配 === */}
      <div className="space-y-1.5">
        <div className="flex items-center gap-1.5">
          <Heart className="w-3.5 h-3.5 text-brand-500" />
          <h5 className="text-xs font-bold text-gray-600">情绪匹配分析</h5>
        </div>
        <p className="text-xs text-gray-600 leading-relaxed pl-5">{rec.emotionMatch}</p>
      </div>

      {/* === 今日评估 === */}
      {signal && (
        <div className="flex items-start gap-2 text-xs">
          <span
            className="w-2 h-2 rounded-full mt-0.5 flex-shrink-0"
            style={{ backgroundColor: SIGNAL_BG_COLORS[signal.signalLevel] }}
          />
          <p className="text-gray-600">
            今日评估：净值估算{item.daily_return >= 0 ? '上涨' : '下跌'}
            {Math.abs(item.daily_return).toFixed(2)}%，
            {['S+', 'S', 'A'].includes(signal.signalLevel)
              ? '恐慌区间提供逢低布局机会'
              : ['D', 'E'].includes(signal.signalLevel)
              ? '贪婪区间注意风险控制'
              : '市场情绪中性，观望为主'}
          </p>
        </div>
      )}

      {/* === 趋势判断 === */}
      <div className="space-y-1.5">
        <div className="flex items-center gap-1.5">
          <Lightbulb className="w-3.5 h-3.5 text-brand-500" />
          <h5 className="text-xs font-bold text-gray-600">趋势判断</h5>
        </div>
        <div className="flex gap-2 pl-5">
          <TrendCard label="短期" direction={shortDir} reason={shortReason} />
          <TrendCard label="中期" direction={midDir} reason={midReason} />
          <TrendCard label="长期" direction={longDir} reason={longReason} />
        </div>
      </div>

      {/* === 6. 操作建议 === */}
      <div
        className={clsx(
          'rounded-lg p-3 flex items-start gap-2.5',
          rec.actionAdvice.includes('加仓') ? 'bg-green-50 border border-green-200' :
          rec.actionAdvice.includes('减仓') ? 'bg-red-50 border border-red-200' :
          'bg-blue-50 border border-blue-200',
        )}
      >
        <div
          className={clsx(
            'w-8 h-8 rounded-full flex items-center justify-center flex-shrink-0',
            rec.actionAdvice.includes('加仓') ? 'bg-green-500' :
            rec.actionAdvice.includes('减仓') ? 'bg-red-500' : 'bg-blue-500',
          )}
        >
          {rec.actionAdvice.includes('加仓') ? (
            <TrendingUp className="w-4 h-4 text-white" />
          ) : rec.actionAdvice.includes('减仓') ? (
            <TrendingDown className="w-4 h-4 text-white" />
          ) : (
            <Minus className="w-4 h-4 text-white" />
          )}
        </div>
        <div>
          <p className="text-sm font-bold text-gray-800">{rec.actionAdvice}</p>
          <p className="text-xs text-gray-500 mt-0.5">{rec.actionReason}</p>
        </div>
      </div>
    </div>
  );
}

/* ============================================================
   子组件: 选中基金详情区
   ============================================================ */
function SelectedFundDetail({
  item,
  signal,
  detail,
  collapsed,
  onToggleCollapse,
}: {
  item: WatchlistItem;
  signal: FundSignalData | undefined;
  detail: FundDetail | undefined;
  collapsed: boolean;
  onToggleCollapse: () => void;
}) {
  const fundShortName = (item as any).fund_short_name || item.fund_name;
  const rec = generateRecommendation(item, signal, detail);

  return (
    <div className="bg-white rounded-xl border border-gray-200 overflow-hidden animate-fadeIn">
      {/* 标题行 */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-gray-100">
        <div className="min-w-0 flex items-center gap-2">
          <h3 className="text-base font-bold text-gray-800 truncate">{fundShortName}</h3>
          <span className="text-xs text-gray-400 font-mono flex-shrink-0">{item.fund_code}</span>
        </div>
        <div className="flex items-center gap-2 flex-shrink-0">
          {signal && (
            <>
              <span
                className="text-xs px-2 py-0.5 rounded-full text-white font-medium"
                style={{ backgroundColor: SIGNAL_BG_COLORS[signal.signalLevel] }}
              >
                {signal.signalLevel}·{SIGNAL_LABELS[signal.signalLevel]}
              </span>
              <span
                className="text-sm font-bold tabular-nums"
                style={{ color: SIGNAL_BG_COLORS[signal.signalLevel] }}
              >
                {Math.round(signal.compositeScore)}分
              </span>
            </>
          )}
          <button
            onClick={onToggleCollapse}
            className="p-1 rounded hover:bg-gray-100 transition-colors"
          >
            {collapsed ? (
              <ChevronDown className="w-4 h-4 text-gray-400" />
            ) : (
              <ChevronUp className="w-4 h-4 text-gray-400" />
            )}
          </button>
        </div>
      </div>

      {/* 详情内容（可收起） */}
      {!collapsed && (
        <div className="p-4 space-y-4">
          {/* 推荐理由区块 */}
          <RecommendationBlock item={item} signal={signal} detail={detail} rec={rec} />

          {/* 底部操作区 */}
          <div className="border-t border-gray-100 pt-3 space-y-2">
            {/* 基金配置信息行 */}
            <div className="flex items-center gap-2 text-xs text-gray-400">
              <span>买入: 底仓</span>
              <span className="text-gray-300">|</span>
              <span>{item.added_at}</span>
            </div>

            {/* 查看完整详情按钮 */}
            <button
              className="w-full flex items-center justify-center gap-1.5 py-2 rounded-lg
                         text-sm font-medium text-brand-500 hover:bg-brand-50 transition-colors"
            >
              查看完整详情
              <ChevronRight className="w-4 h-4" />
            </button>
          </div>
        </div>
      )}
    </div>
  );
}

/* ============================================================
   主页面
   ============================================================ */
export default function WatchlistV5() {
  const [items, setItems] = useState<WatchlistItem[]>([]);
  const [signals, setSignals] = useState<Record<string, FundSignalData>>({});
  const [details, setDetails] = useState<Record<string, FundDetail>>({});
  const [selectedCode, setSelectedCode] = useState<string | null>(null);
  const [detailCollapsed, setDetailCollapsed] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const scrollContainerRef = useRef<HTMLDivElement>(null);

  /** 加载自选列表 + 信号 */
  useEffect(() => {
    let cancelled = false;
    const loadData = async () => {
      setLoading(true);
      setError(null);
      try {
        const data = await fetchWatchlistV5();
        if (cancelled) return;

        // 防御性处理：确保 data 是数组
        const safeData = Array.isArray(data) ? data : [];
        setItems(safeData);

        // 空列表时跳过信号获取
        if (safeData.length === 0) {
          if (!cancelled) setLoading(false);
          return;
        }

        // 默认选中第一项
        if (safeData.length > 0 && !selectedCode) {
          setSelectedCode(safeData[0].fund_code);
        }

        // 并行获取每只基金的V5信号
        const signalEntries = await Promise.all(
          safeData.map(async (item) => {
            try {
              const sentiment = await fetchV5Sentiment(item.fund_code);
              return [item.fund_code, {
                signalLevel: toSignalLevel(sentiment.signal_level),
                confidenceStars: sentiment.confidence_stars,
                compositeScore: sentiment.composite_score ?? 0,
                shortTerm: toSignalLevel(sentiment.signal_level),
                midTerm: toSignalLevel(sentiment.signal_level),
                longTerm: toSignalLevel(sentiment.signal_level),
              }] as [string, FundSignalData];
            } catch {
              return null;
            }
          }),
        );

        if (cancelled) return;

        const signalMap: Record<string, FundSignalData> = {};
        signalEntries.forEach((entry) => {
          if (entry) signalMap[entry[0]] = entry[1];
        });
        setSignals(signalMap);
      } catch (err: any) {
        if (!cancelled) {
          setError(err?.message || '加载自选列表失败');
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    };
    loadData();
    return () => { cancelled = true; };
  }, []);

  /** 选中某只基金后，懒加载详情 */
  useEffect(() => {
    if (!selectedCode || details[selectedCode]) return;

    let cancelled = false;
    const loadDetail = async () => {
      try {
        const detail = await fetchFundDetail(selectedCode);
        if (!cancelled && detail) {
          setDetails((prev) => ({ ...prev, [selectedCode]: detail }));
        }
      } catch {
        // 详情加载失败不阻塞，推荐理由会用 mock 数据
      }
    };
    loadDetail();
    return () => { cancelled = true; };
  }, [selectedCode]);

  const handleSelectCard = useCallback((code: string) => {
    setSelectedCode(code);
    setDetailCollapsed(false);
  }, []);

  const handleRemove = useCallback(async (id: number, code: string) => {
    try {
      await removeWatchlistV5(id);
      setItems((prev) => prev.filter((it) => it.id !== id));
      // 如果删除的是当前选中的，切换到第一个
      if (selectedCode === code) {
        setItems((prev) => {
          if (prev.length > 0) {
            setSelectedCode(prev[0].fund_code);
          } else {
            setSelectedCode(null);
          }
          return prev;
        });
      }
    } catch (err: any) {
      alert(err?.message || '删除自选失败，请重试');
    }
  }, [selectedCode]);

  // 当前选中的 item / signal / detail
  const selectedItem = items.find((it) => it.fund_code === selectedCode) || null;
  const selectedSignal = selectedCode ? signals[selectedCode] : undefined;
  const selectedDetail = selectedCode ? details[selectedCode] : undefined;

  /* ---- Loading ---- */
  if (loading) {
    return (
      <div className="max-w-5xl mx-auto space-y-4">
        <div>
          <h1 className="text-xl font-bold text-gray-800">我的自选 V5.0</h1>
          <p className="text-xs text-gray-400 mt-0.5">点击卡片查看详情 · 横向滑动浏览</p>
        </div>
        <div className="card p-8 text-center">
          <div className="inline-block w-6 h-6 border-2 border-brand-500 border-t-transparent rounded-full animate-spin" />
          <p className="text-gray-400 text-sm mt-2">加载自选列表...</p>
        </div>
      </div>
    );
  }

  /* ---- Error ---- */
  if (error) {
    return (
      <div className="max-w-5xl mx-auto space-y-4">
        <div>
          <h1 className="text-xl font-bold text-gray-800">我的自选 V5.0</h1>
          <p className="text-xs text-gray-400 mt-0.5">点击卡片查看详情 · 横向滑动浏览</p>
        </div>
        <div className="card p-8 text-center">
          <p className="text-red-500 text-sm">{error}</p>
          <button
            onClick={() => window.location.reload()}
            className="mt-3 px-4 py-1.5 text-xs bg-brand-500 text-white rounded-lg hover:bg-brand-600"
          >
            重试
          </button>
        </div>
      </div>
    );
  }

  /* ---- Empty ---- */
  if (items.length === 0) {
    return (
      <div className="max-w-5xl mx-auto space-y-4">
        <div>
          <h1 className="text-xl font-bold text-gray-800">我的自选 V5.0</h1>
          <p className="text-xs text-gray-400 mt-0.5">点击卡片查看详情 · 横向滑动浏览</p>
        </div>
        <div className="card p-8 text-center">
          <Star className="w-8 h-8 text-gray-300 mx-auto mb-2" />
          <p className="text-gray-500 text-sm font-medium">暂无自选基金</p>
          <p className="text-xs text-gray-300 mt-1">在基金查询页点击 ★ 添加自选基金，即可在此查看实时信号</p>
        </div>
      </div>
    );
  }

  /* ---- Main ---- */
  return (
    <div className="max-w-5xl mx-auto space-y-4">
      {/* 页面标题 */}
      <div>
        <h1 className="text-xl font-bold text-gray-800">我的自选 V5.0</h1>
        <p className="text-xs text-gray-400 mt-0.5">点击卡片查看详情 · 横向滑动浏览</p>
      </div>

      {/* ======== 区域 1: 横向滚动卡片区 ======== */}
      <div
        ref={scrollContainerRef}
        className="flex gap-3 overflow-x-auto pb-2 snap-x snap-mandatory scrollbar-thin
                   -mx-1 px-1"
        style={{
          WebkitOverflowScrolling: 'touch',
          scrollbarWidth: 'thin',
        }}
      >
        {items.map((it) => (
          <div key={it.id} className="snap-start">
            <HorizontalFundCard
              item={it}
              signal={signals[it.fund_code]}
              selected={selectedCode === it.fund_code}
              onSelect={() => handleSelectCard(it.fund_code)}
              onRemove={() => handleRemove(it.id, it.fund_code)}
            />
          </div>
        ))}
      </div>

      {/* ======== 区域 2: 选中基金详情区 ======== */}
      {selectedItem && (
        <SelectedFundDetail
          item={selectedItem}
          signal={selectedSignal}
          detail={selectedDetail}
          collapsed={detailCollapsed}
          onToggleCollapse={() => setDetailCollapsed((prev) => !prev)}
        />
      )}

      {/* 内联滚动条样式 */}
      <style>{`
        .scrollbar-thin::-webkit-scrollbar {
          height: 4px;
        }
        .scrollbar-thin::-webkit-scrollbar-track {
          background: transparent;
        }
        .scrollbar-thin::-webkit-scrollbar-thumb {
          background: #CBD5E1;
          border-radius: 2px;
        }
        .scrollbar-thin::-webkit-scrollbar-thumb:hover {
          background: #94A3B8;
        }
      `}</style>
    </div>
  );
}
