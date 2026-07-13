/**
 * AIAnalysisPanel -- AI 分析面板
 *
 * 展示系统建议 vs DeepSeek AI 建议的双列对比，以及 T+1 回验结果。
 * 数据来源: GET /api/v5/validation-today/{fund_code}
 *
 * 展示逻辑:
 * 1. 14:45 后系统建议写入 → 左列展示
 * 2. 14:47 后 DeepSeek 建议写入 → 右列展示
 * 3. 一致性横条: consistent(绿) / partial(黄) / conflict(红)
 * 4. T+1 回验: 展示最近3天有回验结果的记录
 * 5. 无数据时显示"等待14:45系统建议生成"占位
 */
import { useState, useEffect, useCallback } from 'react';
import { Bot, Cpu, CheckCircle2, AlertTriangle, XCircle, Loader2, TrendingUp, TrendingDown, Minus, Clock } from 'lucide-react';
import client from '../../api/client';
import { useAutoRefresh } from '../../hooks/useAutoRefresh';
import { clsx } from 'clsx';

interface ValidationRecord {
  trade_date: string;
  fund_code: string;
  fund_name: string | null;
  sector_name: string | null;
  // 基线
  yesterday_signal: string | null;
  yesterday_confidence: number | null;
  yesterday_score: number | null;
  yesterday_position: number | null;
  yesterday_nav: number | null;
  yesterday_track_type: string | null;
  // 预演
  preview_score: number | null;
  preview_signal: string | null;
  preview_confidence: number | null;
  gszzl: number | null;
  gszzl_source: string | null;
  elasticity: number | null;
  score_delta: number | null;
  effective_stars: number | null;
  intraday_high_gszzl: number | null;
  intraday_low_gszzl: number | null;
  preview_summary: string | null;
  anomaly_flags: string[] | null;
  // 市场上下文
  market_index_chg_pct: number | null;
  sector_chg_pct: number | null;
  // 当日决策
  actual_action: string | null;
  actual_target_position: number | null;
  actual_nav: number | null;
  actual_signal: string | null;
  // 持仓盈亏
  cost_basis: number | null;
  unrealized_pnl_pct: number | null;
  holding_shares: number | null;
  holding_market_value: number | null;
  // Gate
  gate_1_triggered: number | null;
  gate_2_triggered: number | null;
  gate_e_triggered: number | null;
  gate_1_distance_pct: number | null;
  gate_2_distance_pct: number | null;
  gate_e_distance_pct: number | null;
  overall_status: string | null;
  frequency_block_direction: string | null;
  // 建议
  system_advice_text: string | null;
  advice_reason: string | null;
  deepseek_advice: string | null;
  deepseek_advice_action: string | null;
  // 阶段1 元金额字段（后端实时算，零DDL）
  total_assets: number | null;
  current_position_pct: number | null;
  target_position_pct: number | null;
  suggested_amount: number | null;
  system_action: string | null;
  // T+1回验
  validation_score: number | null;
  signal_accuracy: number | null;
  advice_accuracy: number | null;
  gate_accuracy: number | null;
  deepseek_advice_correct: number | null;
  actual_trend: string | null;
  actual_nav_change_pct: number | null;
  actual_score: number | null;
  actual_signal_level: string | null;
  ext_text1: string | null;
}

interface ApiResponse {
  today: ValidationRecord | null;
  consistency: 'consistent' | 'partial' | 'conflict' | null;
  has_system_advice: boolean;
  has_deepseek_advice: boolean;
  backfill_history: ValidationRecord[];
}

const ACTION_MAP: Record<string, { label: string; icon: typeof TrendingUp; color: string; bg: string }> = {
  increase: { label: '加仓', icon: TrendingUp, color: 'text-red-500', bg: 'bg-red-50' },
  hold: { label: '持有', icon: Minus, color: 'text-gray-500', bg: 'bg-gray-50' },
  decrease: { label: '减仓', icon: TrendingDown, color: 'text-green-500', bg: 'bg-green-50' },
};

const STATUS_MAP: Record<string, { label: string; color: string }> = {
  normal: { label: '正常', color: 'text-green-500' },
  warning: { label: '预警', color: 'text-amber-500' },
  stop_loss: { label: '止损', color: 'text-red-500' },
};

const CONSISTENCY_MAP = {
  consistent: { label: '一致', icon: CheckCircle2, color: 'text-green-500', bg: 'bg-green-50', bar: 'bg-green-400' },
  partial: { label: '部分一致', icon: AlertTriangle, color: 'text-amber-500', bg: 'bg-amber-50', bar: 'bg-amber-400' },
  conflict: { label: '分歧', icon: XCircle, color: 'text-red-500', bg: 'bg-red-50', bar: 'bg-red-400' },
};

const TRACK_MAP: Record<string, string> = {
  trend_follow: '趋势轨道',
  contrarian: '逆向轨道',
  excluded: '排除轨道',
};

interface Props {
  fundCode: string;
}

export default function AIAnalysisPanel({ fundCode }: Props) {
  const [data, setData] = useState<ApiResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(true);

  const fetchData = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const resp = await client.get(`/api/v5/validation-today/${fundCode}`);
      if (resp.data?.code === 0) {
        setData(resp.data.data);
      } else {
        setError(resp.data?.message || '获取失败');
      }
    } catch (err: any) {
      setError(err?.response?.data?.detail || err?.response?.data?.message || '网络错误');
    } finally {
      setLoading(false);
    }
  }, [fundCode]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  useAutoRefresh(['ai_analysis'], () => fetchData());

  // 无数据时不渲染
  if (!loading && !error && (!data || (!data.has_system_advice && !data.has_deepseek_advice && data.backfill_history.length === 0))) {
    return null;
  }

  const today = data?.today;
  const consistency = data?.consistency;
  const backfill = data?.backfill_history || [];

  const sysAction = today?.actual_action;
  const aiAction = today?.deepseek_advice_action;
  const sysActionInfo = sysAction ? ACTION_MAP[sysAction] : null;
  const aiActionInfo = aiAction ? ACTION_MAP[aiAction] : null;
  const consistencyInfo = consistency ? CONSISTENCY_MAP[consistency] : null;

  // 阶段1：从 DeepSeek 首行正则提取建议金额（优先于自由文本，避免 DDL）
  const _deepseekFirstLine = today?.deepseek_advice ? today.deepseek_advice.split('\n')[0] : '';
  const _deepseekAmountMatch = _deepseekFirstLine.match(/建议金额[^¥]*¥\s*([\d,]+)/);
  const deepseekSuggestedAmount = _deepseekAmountMatch ? _deepseekAmountMatch[1] : null;

  return (
    <div className="bg-gradient-to-br from-indigo-50/40 to-purple-50/40 rounded-lg border border-indigo-100/50 overflow-hidden">
      {/* ====== 标题栏 ====== */}
      <div
        className="flex items-center gap-2 px-3 py-2 cursor-pointer hover:bg-indigo-50/30 transition-colors"
        onClick={() => setExpanded(!expanded)}
      >
        <Bot className="w-4 h-4 text-indigo-500" />
        <span className="text-xs font-bold text-gray-700">AI 分析面板</span>
        {consistencyInfo && (
          <span className={clsx('flex items-center gap-0.5 px-1.5 py-0.5 rounded text-[9px] font-medium', consistencyInfo.bg, consistencyInfo.color)}>
            <consistencyInfo.icon className="w-2.5 h-2.5" />
            {consistencyInfo.label}
          </span>
        )}
        {today?.overall_status && STATUS_MAP[today.overall_status] && (
          <span className={clsx('text-[9px] px-1.5 py-0.5 rounded bg-gray-50', STATUS_MAP[today.overall_status].color)}>
            {STATUS_MAP[today.overall_status].label}
          </span>
        )}
        <span className="text-[9px] text-gray-400 ml-auto">
          {today?.trade_date || ''}
        </span>
        <svg className={clsx('w-3 h-3 text-gray-400 transition-transform', expanded && 'rotate-180')} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
          <polyline points="6 9 12 15 18 9" />
        </svg>
      </div>

      {expanded && (
        <div className="px-3 pb-3 space-y-3">
          {loading && (
            <div className="flex items-center justify-center py-4">
              <Loader2 className="w-4 h-4 text-indigo-300 animate-spin" />
              <span className="text-[10px] text-gray-400 ml-1">加载中...</span>
            </div>
          )}

          {error && (
            <div className="text-[10px] text-red-400 bg-red-50 rounded p-2">{error}</div>
          )}

          {!loading && !error && today && (
            <>
              {/* ====== 操作建议对比 ====== */}
              {(sysActionInfo || aiActionInfo) && (
                <div className="grid grid-cols-2 gap-2">
                  {/* 系统建议 */}
                  <div className={clsx('rounded-md p-2 border', sysActionInfo ? `${sysActionInfo.bg} border-red-100` : 'bg-gray-50 border-gray-100')}>
                    <div className="flex items-center gap-1 mb-1">
                      <Cpu className="w-3 h-3 text-gray-400" />
                      <span className="text-[9px] text-gray-500 font-medium">系统建议</span>
                    </div>
                    {sysActionInfo ? (
                      <div className="flex items-center gap-1">
                        <sysActionInfo.icon className={clsx('w-4 h-4', sysActionInfo.color)} />
                        <span className={clsx('text-sm font-bold', sysActionInfo.color)}>{sysActionInfo.label}</span>
                        {today.actual_target_position != null && (
                          <span className="text-[9px] text-gray-400 ml-1">→{(today.actual_target_position * 100).toFixed(1)}%</span>
                        )}
                        {today.total_assets != null && today.target_position_pct != null && (
                          <span className="text-[9px] text-gray-500 ml-1">目标¥{(today.total_assets * today.target_position_pct).toFixed(0)}</span>
                        )}
                      </div>
                    ) : (
                      <span className="text-[10px] text-gray-400">等待生成...</span>
                    )}
                  </div>

                  {/* DeepSeek 建议 */}
                  <div className={clsx('rounded-md p-2 border', aiActionInfo ? `${aiActionInfo.bg} border-indigo-100` : 'bg-gray-50 border-gray-100')}>
                    <div className="flex items-center gap-1 mb-1">
                      <Bot className="w-3 h-3 text-indigo-400" />
                      <span className="text-[9px] text-gray-500 font-medium">DeepSeek AI</span>
                    </div>
                    {aiActionInfo ? (
                      <div className="space-y-0.5">
                        <div className="flex items-center gap-1">
                          <aiActionInfo.icon className={clsx('w-4 h-4', aiActionInfo.color)} />
                          <span className={clsx('text-sm font-bold', aiActionInfo.color)}>{aiActionInfo.label}</span>
                        </div>
                        {deepseekSuggestedAmount && (
                          <div className="text-[10px] text-indigo-600">建议¥{deepseekSuggestedAmount}</div>
                        )}
                      </div>
                    ) : (
                      <span className="text-[10px] text-gray-400">等待14:47生成...</span>
                    )}
                  </div>
                </div>
              )}

              {/* ====== 一致性横条 ====== */}
              {consistencyInfo && (
                <div className="flex items-center gap-2">
                  <div className="flex-1 h-1 rounded-full bg-gray-100 overflow-hidden">
                    <div className={clsx('h-full rounded-full transition-all', consistencyInfo.bar, consistency === 'consistent' ? 'w-full' : consistency === 'partial' ? 'w-2/3' : 'w-1/3')} />
                  </div>
                  <span className={clsx('text-[9px] font-medium', consistencyInfo.color)}>
                    {consistencyInfo.label}
                  </span>
                </div>
              )}

              {/* ====== 系统建议详情 ====== */}
              {today.system_advice_text && (
                <div className="bg-white/60 rounded-md p-2.5 border border-gray-100">
                  <div className="flex items-center gap-1 mb-1.5">
                    <Cpu className="w-3 h-3 text-gray-400" />
                    <span className="text-[10px] font-medium text-gray-600">系统建议详情</span>
                  </div>
                  <div className="text-[11px] text-gray-700 leading-relaxed whitespace-pre-wrap max-h-48 overflow-y-auto">
                    {today.system_advice_text}
                  </div>
                </div>
              )}

              {/* ====== DeepSeek AI 建议详情 ====== */}
              {today.deepseek_advice && (
                <div className="bg-white/60 rounded-md p-2.5 border border-indigo-100">
                  <div className="flex items-center gap-1 mb-1.5">
                    <Bot className="w-3 h-3 text-indigo-400" />
                    <span className="text-[10px] font-medium text-indigo-600">DeepSeek AI 分析</span>
                  </div>
                  <div className="text-[11px] text-gray-700 leading-relaxed whitespace-pre-wrap max-h-48 overflow-y-auto">
                    {today.deepseek_advice}
                  </div>
                </div>
              )}

              {/* ====== 预演摘要 ====== */}
              {today.preview_summary && (
                <div className="bg-blue-50/40 rounded-md p-2 border border-blue-50">
                  <div className="flex items-center gap-1 mb-0.5">
                    <span className="text-[9px] text-gray-400">预演摘要</span>
                  </div>
                  <p className="text-[10px] text-gray-600 leading-relaxed">{today.preview_summary}</p>
                </div>
              )}

              {/* ====== 关键数据摘要 ====== */}
              <div className="grid grid-cols-4 gap-1.5">
                {today.gszzl != null && (
                  <DataChip label="盘中估值" value={`${today.gszzl >= 0 ? '+' : ''}${today.gszzl.toFixed(2)}%`} className={today.gszzl >= 0 ? 'text-red-500' : 'text-green-500'} />
                )}
                {today.preview_score != null && (
                  <DataChip label="情绪分" value={today.preview_score.toFixed(1)} />
                )}
                {today.score_delta != null && (
                  <DataChip label="分变化" value={`${today.score_delta >= 0 ? '+' : ''}${today.score_delta.toFixed(1)}`} className={today.score_delta >= 0 ? 'text-red-400' : 'text-green-400'} />
                )}
                {today.elasticity != null && (
                  <DataChip label="弹性" value={today.elasticity.toFixed(2)} />
                )}
                {today.market_index_chg_pct != null && (
                  <DataChip label="大盘" value={`${today.market_index_chg_pct >= 0 ? '+' : ''}${today.market_index_chg_pct.toFixed(2)}%`} className={today.market_index_chg_pct >= 0 ? 'text-red-400' : 'text-green-400'} />
                )}
                {today.sector_chg_pct != null && (
                  <DataChip label="板块" value={`${today.sector_chg_pct >= 0 ? '+' : ''}${today.sector_chg_pct.toFixed(2)}%`} className={today.sector_chg_pct >= 0 ? 'text-red-400' : 'text-green-400'} />
                )}
                {today.unrealized_pnl_pct != null && (
                  <DataChip label="浮盈亏" value={`${today.unrealized_pnl_pct >= 0 ? '+' : ''}${today.unrealized_pnl_pct.toFixed(2)}%`} className={today.unrealized_pnl_pct >= 0 ? 'text-red-400' : 'text-green-400'} />
                )}
                {today.effective_stars != null && (
                  <DataChip label="有效星级" value={`${'★'.repeat(today.effective_stars)}${'☆'.repeat(3 - today.effective_stars)}`} />
                )}
              </div>

              {/* ====== Gate 状态 ====== */}
              {(today.gate_1_triggered || today.gate_2_triggered || today.gate_e_triggered) ? (
                <div className="flex items-center gap-2 bg-amber-50/50 rounded-md p-1.5">
                  <AlertTriangle className="w-3 h-3 text-amber-500 shrink-0" />
                  <span className="text-[10px] text-amber-700">
                    {[
                      today.gate_1_triggered ? 'Gate1' : '',
                      today.gate_2_triggered ? 'Gate2' : '',
                      today.gate_e_triggered ? 'Gate-E' : '',
                    ].filter(Boolean).join(' + ')} 已触发
                  </span>
                </div>
              ) : (today.gate_1_distance_pct != null || today.gate_2_distance_pct != null) && (
                <div className="flex items-center gap-2 text-[9px] text-gray-400">
                  <span>Gate安全:</span>
                  {today.gate_1_distance_pct != null && <span className={today.gate_1_distance_pct > 0 ? 'text-green-400' : 'text-red-400'}>G1 {today.gate_1_distance_pct.toFixed(1)}%</span>}
                  {today.gate_2_distance_pct != null && <span className={today.gate_2_distance_pct > 0 ? 'text-green-400' : 'text-red-400'}>G2 {today.gate_2_distance_pct.toFixed(1)}%</span>}
                </div>
              )}
            </>
          )}

          {/* ====== T+1 回验历史 ====== */}
          {!loading && !error && backfill.length > 0 && (
            <div className="border-t border-gray-100 pt-2">
              <div className="flex items-center gap-1 mb-1.5">
                <Clock className="w-3 h-3 text-gray-400" />
                <span className="text-[10px] font-medium text-gray-500">T+1 回验记录</span>
              </div>
              <div className="space-y-1.5">
                {backfill.map((rec, i) => (
                  <BackfillRecord key={i} record={rec} />
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

// ── 子组件: 数据芯片 ──
function DataChip({ label, value, className }: { label: string; value: string; className?: string }) {
  return (
    <div className="bg-gray-50/60 rounded p-1 text-center">
      <p className="text-[8px] text-gray-400">{label}</p>
      <p className={clsx('text-[10px] font-mono font-medium', className || 'text-gray-600')}>{value}</p>
    </div>
  );
}

// ── 子组件: T+1 回验记录 ──
function BackfillRecord({ record }: { record: ValidationRecord }) {
  const trendLabel = record.actual_trend === 'up' ? '上涨' : record.actual_trend === 'down' ? '下跌' : '横盘';
  const trendColor = record.actual_trend === 'up' ? 'text-red-400' : record.actual_trend === 'down' ? 'text-green-400' : 'text-gray-400';

  const scoreColor = record.validation_score != null
    ? record.validation_score >= 70 ? 'text-green-500' : record.validation_score >= 50 ? 'text-amber-500' : 'text-red-500'
    : 'text-gray-400';

  const sysActionInfo = record.actual_action ? ACTION_MAP[record.actual_action] : null;
  const aiActionInfo = record.deepseek_advice_action ? ACTION_MAP[record.deepseek_advice_action] : null;
  const aiCorrect = record.deepseek_advice_correct;

  return (
    <div className="bg-white/50 rounded-md p-1.5 border border-gray-50">
      <div className="flex items-center justify-between mb-1">
        <span className="text-[9px] text-gray-500 font-mono">{record.trade_date}</span>
        {record.validation_score != null && (
          <span className={clsx('text-[10px] font-bold', scoreColor)}>{record.validation_score.toFixed(0)}分</span>
        )}
      </div>
      <div className="flex items-center gap-2 text-[9px]">
        {/* 系统建议 vs 实际 */}
        {sysActionInfo && (
          <span className={clsx('px-1 py-0.5 rounded', sysActionInfo.bg, sysActionInfo.color)}>
            系统{sysActionInfo.label}
          </span>
        )}
        {/* AI建议 vs 实际 */}
        {aiActionInfo && (() => {
          // 解析 ext_text1 检测是否被 Gate 覆盖
          let isOverridden = false;
          let rawActionLabel = '';
          if (record.ext_text1) {
            try {
              const ext = JSON.parse(record.ext_text1);
              if (ext.raw_action && ext.raw_action !== record.deepseek_advice_action) {
                isOverridden = true;
                rawActionLabel = ext.raw_action === 'increase' ? '加仓' : ext.raw_action === 'decrease' ? '减仓' : '持有';
              }
            } catch {}
          }
          return (
            <span className={clsx('px-1 py-0.5 rounded', aiActionInfo.bg, aiActionInfo.color)}>
              AI{rawActionLabel ? `${rawActionLabel}→` : ''}{aiActionInfo.label}
            </span>
          );
        })()}
        {(() => {
          // 被覆盖标记
          if (!record.ext_text1) return null;
          try {
            const ext = JSON.parse(record.ext_text1);
            if (ext.raw_action && ext.raw_action !== record.deepseek_advice_action) {
              return (
                <span className="px-1 py-0.5 rounded bg-amber-50 text-amber-500 font-medium">
                  被覆盖
                </span>
              );
            }
          } catch {}
          return null;
        })()}
        {/* AI正确性 */}
        {aiCorrect != null && (
          <span className={clsx('px-1 py-0.5 rounded', aiCorrect === 1 ? 'bg-green-50 text-green-500' : 'bg-red-50 text-red-400')}>
            AI {aiCorrect === 1 ? '✓' : '✗'}
          </span>
        )}
        {/* 实际趋势 */}
        <span className="text-gray-400 ml-auto">
          实际: <span className={trendColor}>{trendLabel}</span>
          {record.actual_nav_change_pct != null && (
            <span className={trendColor}> {record.actual_nav_change_pct >= 0 ? '+' : ''}{record.actual_nav_change_pct.toFixed(2)}%</span>
          )}
        </span>
      </div>
      {/* 准确度指标 */}
      {(record.signal_accuracy != null || record.advice_accuracy != null || record.gate_accuracy != null) && (
        <div className="flex items-center gap-3 mt-1 text-[8px] text-gray-400">
          {record.signal_accuracy != null && <span>信号 {((record.signal_accuracy) * 100).toFixed(0)}%</span>}
          {record.advice_accuracy != null && <span>建议 {((record.advice_accuracy) * 100).toFixed(0)}%</span>}
          {record.gate_accuracy != null && <span>Gate {((record.gate_accuracy) * 100).toFixed(0)}%</span>}
        </div>
      )}
    </div>
  );
}
