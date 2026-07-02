/**
 * IntradayPreviewAction -- 操作预通知卡片
 * 显示预演操作建议(hold/increase/decrease) + 前缀文案
 * 视觉隔离：浅蓝背景 + 虚线边框 + "预演"角标
 */
import React from 'react';
import { IntradayPreviewData, CONFIDENCE_CONFIG } from '../types';
import IntradayConfidenceBadge from './IntradayConfidenceBadge';

interface Props {
  data: IntradayPreviewData;
}

const ACTION_CONFIG: Record<string, { label: string; icon: string; color: string; bg: string }> = {
  'hold':     { label: '持有观望', icon: '⏸', color: 'text-gray-600', bg: 'bg-gray-50' },
  'increase': { label: '加仓',     icon: '↗', color: 'text-emerald-700', bg: 'bg-emerald-50' },
  'decrease': { label: '减仓',     icon: '↘', color: 'text-red-700', bg: 'bg-red-50' },
};

export default function IntradayPreviewAction({ data }: Props) {
  const actionConf = ACTION_CONFIG[data.action] || ACTION_CONFIG['hold'];
  const confConfig = CONFIDENCE_CONFIG[data.preview_confidence] || CONFIDENCE_CONFIG[1];

  return (
    <div className="relative rounded-lg border border-dashed border-blue-200 bg-[#EFF6FF] p-3">
      {/* 预演角标 */}
      <span className="absolute -top-2 -right-2 px-2 py-0.5 rounded text-xs font-bold bg-orange-500 text-white shadow-sm">
        预演
      </span>

      {/* 置信度标签 */}
      <div className="flex items-center gap-2 mb-2">
        <IntradayConfidenceBadge confidence={data.preview_confidence} />
        <span className="text-xs text-blue-600">{confConfig.note}</span>
      </div>

      {/* 操作建议 */}
      <div className={`flex items-center gap-2 px-3 py-2 rounded ${actionConf.bg}`}>
        <span className="text-lg">{actionConf.icon}</span>
        <span className={`font-semibold ${actionConf.color}`}>{actionConf.label}</span>
        {data.target_position_pct !== undefined && data.action !== 'hold' && (
          <span className="text-xs text-gray-500">
            → 目标仓位 {Math.round(data.target_position_pct * 100)}%
          </span>
        )}
      </div>

      {/* 前缀文案 */}
      <p className="mt-2 text-xs text-gray-500 italic">
        {data.accuracy_warning}
      </p>

      {/* reason */}
      {data.reason && (
        <p className="mt-1 text-xs text-gray-600">
          {data.reason}
        </p>
      )}
    </div>
  );
}
