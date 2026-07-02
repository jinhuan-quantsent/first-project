/**
 * IntradaySentimentPreview -- 情绪分预览卡片
 * 昨日收盘 vs 盘中预演对比
 * 信号变化方向标识
 */
import React from 'react';
import { IntradayPreviewData, SIGNAL_CHANGE_CONFIG } from '../types';

interface Props {
  data: IntradayPreviewData;
}

export default function IntradaySentimentPreview({ data }: Props) {
  const changeConf = SIGNAL_CHANGE_CONFIG[data.signal_change || 'unknown'] || SIGNAL_CHANGE_CONFIG['unknown'];

  return (
    <div className="rounded-lg border border-dashed border-blue-200 bg-[#EFF6FF] p-3">
      <span className="text-xs font-semibold text-blue-700 mb-2 block">情绪分预览</span>

      {/* 昨今对比 */}
      <div className="flex items-center gap-4">
        {/* 昨日 */}
        <div className="text-center">
          <span className="text-xs text-gray-500 block">昨日收盘</span>
          <span className="text-lg font-bold text-gray-700">{data.yesterday_score?.toFixed(1) ?? '-'}</span>
          <span className="text-xs text-gray-400 block">{data.yesterday_signal ?? '-'}</span>
        </div>

        {/* 变化方向 */}
        <div className="flex flex-col items-center">
          <span className={`text-lg ${changeConf.color}`}>{changeConf.icon}</span>
          <span className={`text-xs ${changeConf.color}`}>{changeConf.label}</span>
          {data.score_delta !== null && (
            <span className={`text-xs font-medium ${data.score_delta > 0 ? 'text-emerald-600' : data.score_delta < 0 ? 'text-red-600' : 'text-gray-400'}`}>
              Δ {data.score_delta > 0 ? '+' : ''}{data.score_delta.toFixed(1)}
            </span>
          )}
        </div>

        {/* 盘中预演 */}
        <div className="text-center">
          <span className="text-xs text-blue-500 block">盘中预演</span>
          <span className="text-lg font-bold text-blue-700">{data.preview_score?.toFixed(1) ?? '-'}</span>
          <span className="text-xs text-blue-500 block">{data.signal_level ?? '-'}</span>
        </div>
      </div>

      {/* gszzl & elasticity */}
      {data.gszzl !== null && (
        <div className="mt-2 flex gap-3 text-xs text-gray-500">
          <span>
            涨跌幅: <span className={data.gszzl > 0 ? 'text-emerald-600' : data.gszzl < 0 ? 'text-red-600' : 'text-gray-400'}>
              {data.gszzl > 0 ? '+' : ''}{data.gszzl.toFixed(2)}%
            </span>
          </span>
          {data.elasticity !== null && (
            <span>弹性系数: {data.elasticity.toFixed(2)}</span>
          )}
        </div>
      )}
    </div>
  );
}
