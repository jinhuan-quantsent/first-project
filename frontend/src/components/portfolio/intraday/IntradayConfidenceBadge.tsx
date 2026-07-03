/**
 * IntradayConfidenceBadge -- 置信度时段标识
 * 显示早盘/午盘/尾盘标签 + 时段文案
 */
import React from 'react';
import { CONFIDENCE_CONFIG } from '../types';

interface Props {
  confidence: number;  // 1=早盘, 2=午盘, 3=尾盘
  className?: string;
}

export default function IntradayConfidenceBadge({ confidence, className = '' }: Props) {
  const config = CONFIDENCE_CONFIG[confidence] || CONFIDENCE_CONFIG[1];

  return (
    <span
      className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs font-medium border ${config.bg} ${config.color} ${config.border} ${className}`}
    >
      {config.label}
    </span>
  );
}
