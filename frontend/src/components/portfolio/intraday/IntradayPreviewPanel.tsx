/**
 * IntradayPreviewPanel -- 盘中预演编排器
 * 
 * 顶层编排组件，负责：
 * 1. 定时轮询预演数据（每5分钟）
 * 2. 交易时段检查（9:30-15:00含午休）
 * 3. 组装子组件（ConfidenceBadge + PreviewAction + ThresholdBar + SentimentPreview）
 * 4. 视觉隔离规范：浅蓝背景+虚线边框+橙色角标
 * 5. 午休期间(11:30-13:00)显示上午预演结果并标注
 */
import React, { useState, useEffect, useCallback, useRef } from 'react';
import { IntradayPreviewData, AnomalyNote } from '../types';
import { fetchIntradayPreview } from '../../../api/portfolioV5';
import { useAutoRefresh } from '../../../hooks/useAutoRefresh';
import IntradayConfidenceBadge from './IntradayConfidenceBadge';
import IntradayPreviewAction from './IntradayPreviewAction';
import IntradayThresholdBar from './IntradayThresholdBar';
import IntradaySentimentPreview from './IntradaySentimentPreview';

interface Props {
  fundCode: string;
}

/** 检查是否在盘中显示窗口（9:30-15:00，含午休） */
function isIntradayWindow(): boolean {
  const now = new Date();
  const h = now.getHours();
  const m = now.getMinutes();
  const timeNum = h * 100 + m;
  // 9:30-15:00 全天盘中窗口（含午休，午休期间显示上午结果）
  return timeNum >= 930 && timeNum <= 1500;
}

/** 检查是否为活跃交易时段（有新数据产生的时段） */
function isActiveTrading(): boolean {
  const now = new Date();
  const h = now.getHours();
  const m = now.getMinutes();
  const timeNum = h * 100 + m;
  // 9:30-11:30 或 13:00-15:00
  return (timeNum >= 930 && timeNum <= 1130) || (timeNum >= 1300 && timeNum <= 1500);
}

/** 检查是否午休时段 */
function isLunchBreak(): boolean {
  const now = new Date();
  const h = now.getHours();
  const m = now.getMinutes();
  const timeNum = h * 100 + m;
  return timeNum > 1130 && timeNum < 1300;
}

export default function IntradayPreviewPanel({ fundCode }: Props) {
  const [previewData, setPreviewData] = useState<IntradayPreviewData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [inWindow, setInWindow] = useState(isIntradayWindow());
  const [lunchBreak, setLunchBreak] = useState(isLunchBreak());

  // ref 镜像：refresh 闭包内读取最新 previewData，避免 stale closure
  const previewDataRef = useRef(previewData);
  previewDataRef.current = previewData;

  // 定时轮询（仅依赖 fundCode，不依赖 previewData，避免无限循环）
  const refresh = useCallback(async () => {
    // 不在盘中窗口则退出
    if (!isIntradayWindow()) {
      setInWindow(false);
      return;
    }
    setInWindow(true);
    setLunchBreak(isLunchBreak());

    // 午休期间不主动刷新（保留上午结果）
    if (isLunchBreak() && previewDataRef.current) {
      return;
    }

    setLoading(true);
    setError(null);
    try {
      const data = await fetchIntradayPreview(fundCode);
      if (data && data.is_preview && data.status !== 'pending') {
        setPreviewData(data);
      } else if (data?.status === 'pending') {
        // 数据未就绪
        setPreviewData(null);
        setError('预演数据未就绪，请稍后刷新');
      } else {
        setPreviewData(null);
        setError('盘中预演功能暂不可用');
      }
    } catch (e: any) {
      setError(e.message || '获取预演数据失败');
    } finally {
      setLoading(false);
    }
  }, [fundCode]);

  // 展开时立即刷新 + 每分钟检查时段状态
  useEffect(() => {
    refresh();
    // 每分钟检查时段状态
    const checkInterval = setInterval(() => {
      setInWindow(isIntradayWindow());
      setLunchBreak(isLunchBreak());
    }, 60000);
    return () => {
      clearInterval(checkInterval);
    };
  }, [refresh]);

  useAutoRefresh(['signal_board'], () => refresh());

  // 盘中窗口外不显示（15:00后隐藏）
  if (!inWindow) {
    return null;
  }

  // 加载中
  if (loading && !previewData) {
    return (
      <div className="rounded-lg border border-dashed border-blue-200 bg-[#EFF6FF] p-3 text-center">
        <span className="text-xs text-blue-500 animate-pulse">加载预演数据中...</span>
      </div>
    );
  }

  // 错误 / 数据未就绪
  if (error || !previewData) {
    return (
      <div className="rounded-lg border border-dashed border-blue-200 bg-[#EFF6FF] p-3">
        <div className="flex items-center gap-2">
          <IntradayConfidenceBadge confidence={1} />
          <span className="text-xs text-gray-500">{error || '预演数据暂不可用'}</span>
        </div>
        <p className="text-xs text-gray-400 mt-1 italic">盘中预演为估算结果，需收盘确认后生效</p>
      </div>
    );
  }

  // 场景状态配置
  const status = previewData.overall_status || 'normal';
  const STATUS_STYLE: Record<string, { border: string; bg: string; badge: string; badgeText: string }> = {
    normal:    { border: 'border-blue-200',   bg: '',                    badge: 'bg-blue-500',   badgeText: '预演' },
    warning:   { border: 'border-amber-300',  bg: 'bg-amber-50/40',     badge: 'bg-amber-500',  badgeText: '预警' },
    stop_loss: { border: 'border-red-400',    bg: 'bg-red-50/30',       badge: 'bg-red-600',    badgeText: '风控触发' },
  };
  const style = STATUS_STYLE[status] || STATUS_STYLE.normal;

  // stop_loss 场景：异常提示按严重度排序（danger 优先）
  const sortedNotes = status === 'stop_loss' && previewData.anomaly_notes
    ? [...previewData.anomaly_notes].sort((a, b) => {
        const order = { danger: 0, warning: 1, info: 2 };
        return (order[a.level as keyof typeof order] ?? 3) - (order[b.level as keyof typeof order] ?? 3);
      })
    : previewData.anomaly_notes;

  // 正常显示
  return (
    <div className={`space-y-2 rounded-lg border border-dashed ${style.border} ${style.bg} p-2`}>
      {/* 状态标签（非 normal 时显示） */}
      {status !== 'normal' && (
        <div className="flex items-center gap-1.5">
          <span className={`px-1.5 py-0.5 rounded text-[10px] font-medium text-white ${style.badge}`}>
            {style.badgeText}
          </span>
          {status === 'stop_loss' && (
            <span className="text-[10px] text-red-600">建议优先关注风控提示</span>
          )}
        </div>
      )}

      {/* 午休提示 */}
      {lunchBreak && (
        <div className="flex items-center gap-1.5 px-2 py-1 rounded bg-orange-50 border border-orange-200">
          <span className="text-[10px] text-orange-600 font-medium">午休中</span>
          <span className="text-[10px] text-orange-500">显示上午预演结果，13:00后更新午盘数据</span>
        </div>
      )}

      {/* 综合解读 */}
      {previewData.preview_summary && (
        <div className={`px-2.5 py-1.5 rounded border ${
          status === 'stop_loss' ? 'bg-red-50/50 border-red-100' :
          status === 'warning' ? 'bg-amber-50/50 border-amber-100' :
          'bg-blue-50/60 border-blue-100'
        }`}>
          <p className="text-[11px] text-gray-600 leading-relaxed">{previewData.preview_summary}</p>
        </div>
      )}

      {/* 异常场景提示 */}
      {sortedNotes && sortedNotes.length > 0 && (
        <div className="space-y-1">
          {sortedNotes.map((note, idx) => (
            <AnomalyNoteBadge key={idx} note={note} />
          ))}
        </div>
      )}

      {/* stop_loss 场景：阈值进度条优先展示 */}
      {status === 'stop_loss' && previewData.thresholds && (
        <IntradayThresholdBar
          thresholds={previewData.thresholds}
          previewScore={previewData.preview_score}
          yesterdayScore={previewData.yesterday_score}
        />
      )}

      {/* 操作预通知 */}
      <IntradayPreviewAction data={previewData} />

      {/* 情绪分预览 */}
      <IntradaySentimentPreview data={previewData} />

      {/* 阈值进度条（非 stop_loss 场景或 stop_loss 的 fallback） */}
      {status !== 'stop_loss' && previewData.thresholds && (
        <IntradayThresholdBar
          thresholds={previewData.thresholds}
          previewScore={previewData.preview_score}
          yesterdayScore={previewData.yesterday_score}
        />
      )}

      {/* 刷新按钮 */}
      <div className="flex items-center justify-between text-xs text-gray-400">
        <span>更新于 {previewData.calc_time?.slice(11, 19) ?? '-'}</span>
        <button
          onClick={refresh}
          className="px-2 py-1 rounded text-blue-500 hover:text-blue-700 hover:bg-blue-100 disabled:opacity-50"
          disabled={loading || lunchBreak}
        >
          {loading ? '刷新中...' : lunchBreak ? '午休暂停' : '↻ 刷新'}
        </button>
      </div>
    </div>
  );
}

/** 异常提示徽章 */
function AnomalyNoteBadge({ note }: { note: AnomalyNote }) {
  const config: Record<string, { bg: string; border: string; text: string; icon: string }> = {
    danger:  { bg: 'bg-red-50',    border: 'border-red-200',    text: 'text-red-600',    icon: '⚠' },
    warning: { bg: 'bg-amber-50',  border: 'border-amber-200',  text: 'text-amber-600',  icon: '注意' },
    info:    { bg: 'bg-gray-50',   border: 'border-gray-200',   text: 'text-gray-500',   icon: 'ℹ' },
  };
  const c = config[note.level] || config.info;
  return (
    <div className={`flex items-start gap-1 px-2 py-1 rounded ${c.bg} border ${c.border}`}>
      <span className={`text-[10px] ${c.text} font-medium shrink-0`}>{c.icon}</span>
      <span className={`text-[10px] ${c.text} leading-relaxed`}>{note.message}</span>
    </div>
  );
}
