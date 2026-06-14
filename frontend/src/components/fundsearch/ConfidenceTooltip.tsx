/**
 * ConfidenceTooltip - 置信度明细悬浮提示
 * 点击置信度星级弹出，展示5维度评分明细
 */
import type { ConfidenceDetail } from '../../types';
import { X, Info } from 'lucide-react';
import { useState } from 'react';
import { clsx } from 'clsx';

interface ConfidenceTooltipProps {
  detail: ConfidenceDetail | null;
  stars: number;
  position?: 'top' | 'bottom' | 'left' | 'right';
}

function scoreBarColor(score: number): string {
  if (score >= 80) return 'bg-green-500';
  if (score >= 60) return 'bg-brand-500';
  if (score >= 40) return 'bg-yellow-400';
  return 'bg-red-400';
}

export default function ConfidenceTooltip({
  detail,
  stars,
  position = 'top',
}: ConfidenceTooltipProps) {
  const [open, setOpen] = useState(false);

  if (!detail) return null;

  const items = [
    { label: '因子一致性',   value: detail.factor_consistency, desc: '11因子得分标准差反向映射' },
    { label: '信号强度',     value: detail.signal_strength,   desc: '|得分-50| 映射至0~100' },
    { label: '体制匹配',     value: detail.regime_match,      desc: '当前市场体制与信号匹配度' },
    { label: '持续性',       value: detail.persistence,        desc: '情感MACD同向天数' },
    { label: '数据质量',     value: detail.data_quality,      desc: '有效因子数/11 × 数据完整度' },
  ];

  const POSITION_CLASSES: Record<string, string> = {
    top:    'bottom-full left-1/2 -translate-x-1/2 mb-2',
    bottom: 'top-full left-1/2 -translate-x-1/2 mt-2',
    left:   'right-full top-1/2 -translate-y-1/2 mr-2',
    right:  'left-full top-1/2 -translate-y-1/2 ml-2',
  };

  return (
    <div className="relative inline-block">
      {/* 触发按钮 */}
      <button
        onClick={() => setOpen(!open)}
        className="flex items-center gap-0.5 text-xs text-gray-400 hover:text-gray-600 transition-colors"
      >
        <Info className="w-3 h-3" />
        <span>{stars}星置信度</span>
      </button>

      {/* 悬浮面板 */}
      {open && (
        <>
          {/* 遮罩层（点击关闭） */}
          <div className="fixed inset-0 z-40" onClick={() => setOpen(false)} />

          <div
            className={clsx(
              'absolute z-50 w-64 bg-white rounded-xl border border-gray-200 shadow-lg p-4 space-y-3',
              POSITION_CLASSES[position],
            )}
          >
            {/* 标题 */}
            <div className="flex items-center justify-between">
              <h4 className="text-xs font-bold text-gray-700">置信度详情</h4>
              <button onClick={() => setOpen(false)} className="p-0.5 rounded hover:bg-gray-100">
                <X className="w-3 h-3 text-gray-400" />
              </button>
            </div>

            {/* 5维度明细 */}
            <div className="space-y-2">
              {items.map((it) => (
                <div key={it.label}>
                  <div className="flex justify-between text-[10px] mb-0.5">
                    <span className="text-gray-500">{it.label}</span>
                    <span className="font-mono font-medium text-gray-700">{it.value.toFixed(0)}</span>
                  </div>
                  <div className="w-full h-1.5 bg-gray-100 rounded-full overflow-hidden">
                    <div
                      className={`h-full rounded-full transition-all duration-500 ${scoreBarColor(it.value)}`}
                      style={{ width: `${Math.min(100, Math.max(0, it.value))}%` }}
                    />
                  </div>
                  <p className="text-[9px] text-gray-300 mt-0.5">{it.desc}</p>
                </div>
              ))}
            </div>

            {/* 触发的防线 */}
            {detail.triggered_defenses && detail.triggered_defenses.length > 0 && (
              <div className="pt-2 border-t border-gray-100">
                <p className="text-[10px] text-yellow-600 font-medium mb-1">⚠ 触发防线：</p>
                {detail.triggered_defenses.map((d) => (
                  <p key={d} className="text-[10px] text-yellow-700">{d}</p>
                ))}
              </div>
            )}
          </div>
        </>
      )}
    </div>
  );
}
