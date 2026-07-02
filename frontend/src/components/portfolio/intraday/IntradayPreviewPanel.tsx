/**
 * IntradayPreviewPanel -- 盘中预演编排器
 * 
 * 顶层编排组件，负责：
 * 1. 定时轮询预演数据（每5分钟）
 * 2. 交易时段检查
 * 3. 组装子组件（ConfidenceBadge + PreviewAction + ThresholdBar + SentimentPreview）
 * 4. 视觉隔离规范：浅蓝背景+虚线边框+橙色角标
 */
import React, { useState, useEffect, useCallback } from 'react';
import { IntradayPreviewData } from '../types';
import { fetchIntradayPreview } from '../../../api/portfolioV5';
import IntradayConfidenceBadge from './IntradayConfidenceBadge';
import IntradayPreviewAction from './IntradayPreviewAction';
import IntradayThresholdBar from './IntradayThresholdBar';
import IntradaySentimentPreview from './IntradaySentimentPreview';

interface Props {
  fundCode: string;
}

/** 检查是否交易时段 */
function isTradingTime(): boolean {
  const now = new Date();
  const h = now.getHours();
  const m = now.getMinutes();
  const timeNum = h * 100 + m;
  // 9:30-11:30 或 13:00-15:00
  return (timeNum >= 930 && timeNum <= 1130) || (timeNum >= 1300 && timeNum <= 1500);
}

export default function IntradayPreviewPanel({ fundCode }: Props) {
  const [previewData, setPreviewData] = useState<IntradayPreviewData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [isTrading, setIsTrading] = useState(isTradingTime());

  // 定时轮询
  const refresh = useCallback(async () => {
    if (!isTradingTime()) {
      setIsTrading(false);
      return;
    }
    setIsTrading(true);
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

  // 每5分钟轮询 + 展开时立即刷新
  useEffect(() => {
    refresh();
    const timer = setInterval(refresh, 300000); // 5分钟
    // 同时每分钟检查交易时段
    const tradingCheck = setInterval(() => setIsTrading(isTradingTime()), 60000);
    return () => {
      clearInterval(timer);
      clearInterval(tradingCheck);
    };
  }, [refresh]);

  // 非交易时段
  if (!isTrading) {
    return null;  // 交易时段外不显示
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

  // 正常显示
  return (
    <div className="space-y-2">
      {/* 操作预通知 */}
      <IntradayPreviewAction data={previewData} />

      {/* 情绪分预览 */}
      <IntradaySentimentPreview data={previewData} />

      {/* 阈值进度条 */}
      {previewData.thresholds && (
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
          disabled={loading}
        >
          {loading ? '刷新中...' : '↻ 刷新'}
        </button>
      </div>
    </div>
  );
}
