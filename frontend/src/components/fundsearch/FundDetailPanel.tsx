/**
 * FundDetailPanel - 右侧详情面板
 * 显示基金基本信息 + 信号徽章 + 置信度 + 因子雷达 + 仓位建议
 */
import type { FundSearchItem, FundDetail, SignalLevel } from '../../types';
import SentimentBadge from '../common/SentimentBadge';
import { Star, TrendingUp, Shield, X, ArrowLeft } from 'lucide-react';
import { clsx } from 'clsx';

/** 安全取数，防止 undefined/null 调用 .toFixed() 崩溃 */
const safeNum = (v: number | undefined | null, fallback = 0): number => v ?? fallback;

interface FundDetailPanelProps {
  fund: FundSearchItem;
  detail: FundDetail | null;
  sentiment: {
    score: number;
    signalLevel: SignalLevel;
    confidenceStars: number;
    advice: { action: string; level: string; reason: string; targetPositionPct: number };
  } | null;
  loading: boolean;
  onClose: () => void;
}

const SIGNAL_COLORS: Record<string, string> = {
  'S+': '#059669',
  'S':  '#10B981',
  'A':  '#6EE7B7',
  'B':  '#FBBF24',
  'C':  '#FCA5A5',
  'D':  '#EF4444',
  'E':  '#DC2626',
};

export default function FundDetailPanel({
  fund,
  detail,
  sentiment,
  loading,
  onClose,
}: FundDetailPanelProps) {
  if (loading) {
    return (
      <div className="card p-6 space-y-4 animate-pulse">
        <div className="h-6 w-32 bg-gray-200 rounded" />
        <div className="h-20 w-full bg-gray-100 rounded-xl" />
        <div className="h-24 w-full bg-gray-100 rounded-xl" />
      </div>
    );
  }

  return (
    <div className="card overflow-hidden animate-fadeIn">
      {/* 顶部：关闭按钮 + 基金名 */}
      <div className="flex items-center gap-2 px-4 py-3 border-b border-gray-100">
        <button
          onClick={onClose}
          className="p-1 rounded hover:bg-gray-100 transition-colors"
        >
          <ArrowLeft className="w-4 h-4 text-gray-400" />
        </button>
        <div className="min-w-0">
          <h3 className="text-sm font-bold text-gray-800 truncate">
            {fund.fund_name}
          </h3>
          <p className="text-xs text-gray-400 font-mono">
            {fund.fund_code} · {fund.fund_type}
          </p>
        </div>
        <button
          onClick={onClose}
          className="ml-auto p-1 rounded hover:bg-gray-100 transition-colors"
        >
          <X className="w-4 h-4 text-gray-400" />
        </button>
      </div>

      <div className="p-4 space-y-4">
        {/* 情绪评分卡片 */}
        {sentiment && (
          <div className="bg-gray-50 rounded-xl p-4 flex items-center gap-4">
            <div
              className="w-16 h-16 rounded-full flex items-center justify-center text-white text-xl font-bold shrink-0"
              style={{ background: SIGNAL_COLORS[sentiment.signalLevel] || '#94A3B8' }}
            >
              {sentiment.score}
            </div>
            <div className="min-w-0">
              <div className="flex items-center gap-2 flex-wrap">
                <SentimentBadge level={sentiment.signalLevel} size="md" />
                <div className="flex gap-0.5">
                  {[1, 2, 3, 4].map((star) => (
                    <Star
                      key={star}
                      className={clsx(
                        'w-3.5 h-3.5',
                        star <= sentiment.confidenceStars
                          ? 'text-yellow-400 fill-yellow-400'
                          : 'text-gray-300',
                      )}
                    />
                  ))}
                </div>
              </div>
              <p className="text-xs text-gray-400 mt-0.5">V5.0 综合情绪评分</p>
              <p className="text-xs text-gray-500 mt-1">
                净值 {safeNum(fund.nav).toFixed(4)} · 日收益{' '}
                <span className={safeNum(fund.daily_return) >= 0 ? 'text-red-500' : 'text-green-500'}>
                  {safeNum(fund.daily_return) >= 0 ? '+' : ''}{safeNum(fund.daily_return).toFixed(2)}%
                </span>
              </p>
            </div>
          </div>
        )}

        {/* 操作建议 */}
        {sentiment && (
          <div className={clsx(
            'rounded-xl p-4 flex items-start gap-3',
            sentiment.advice.level === '积极' ? 'bg-green-50 border border-green-200' :
            sentiment.advice.level === '谨慎' ? 'bg-red-50 border border-red-200' :
            'bg-blue-50 border border-blue-200',
          )}>
            <div className={clsx(
              'w-10 h-10 rounded-full flex items-center justify-center shrink-0',
              sentiment.advice.level === '积极' ? 'bg-green-500' :
              sentiment.advice.level === '谨慎' ? 'bg-red-500' : 'bg-blue-500',
            )}>
              {sentiment.advice.level === '积极' ? (
                <TrendingUp className="w-5 h-5 text-white" />
              ) : sentiment.advice.level === '谨慎' ? (
                <svg className="w-5 h-5 text-white" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2}>
                  <path d="M12 9v2m0 4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
                </svg>
              ) : (
                <Shield className="w-5 h-5 text-white" />
              )}
            </div>
            <div>
              <p className="text-sm font-bold text-gray-800">{sentiment.advice.action}</p>
              <p className="text-xs text-gray-500 mt-0.5">{sentiment.advice.reason}</p>
              <p className="text-xs text-gray-400 mt-1">
                建议仓位：{Math.round(sentiment.advice.targetPositionPct * 100)}%
              </p>
            </div>
          </div>
        )}

        {/* 基金详情信息 */}
        {detail && (
          <div className="bg-gray-50 rounded-xl p-4 space-y-2">
            <h4 className="text-xs font-bold text-gray-400 uppercase">基金信息</h4>
            <div className="grid grid-cols-2 gap-x-4 gap-y-1.5 text-xs">
              <div>
                <span className="text-gray-400">基金经理</span>
                <p className="font-medium text-gray-700">{detail.manager}</p>
              </div>
              <div>
                <span className="text-gray-400">基金公司</span>
                <p className="font-medium text-gray-700 truncate">{detail.company}</p>
              </div>
              <div>
                <span className="text-gray-400">成立日期</span>
                <p className="font-medium text-gray-700">{detail.inception_date}</p>
              </div>
              <div>
                <span className="text-gray-400">累计净值</span>
                <p className="font-medium text-gray-700 font-mono">{safeNum(detail.accumulated_nav).toFixed(4)}</p>
              </div>
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
