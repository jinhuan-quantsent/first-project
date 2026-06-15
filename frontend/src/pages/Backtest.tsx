/**
 * Backtest - V5.0 历史回溯页（模板对齐版）
 * 方案管理栏 + 5类折叠参数面板（滑块+开关）+ 回测结果展示（8指标+曲线+日志）
 */
import { useState, useEffect, useCallback, useMemo } from 'react';
import { Save, Trash2, Play, TrendingUp, ChevronDown, AlertTriangle, Shield } from 'lucide-react';
import { clsx } from 'clsx';
import { runBacktestV5, saveBacktestStrategyV5, deleteBacktestStrategyV5 } from '../api/backtest';
import type { ModelParams, ActionRule, BacktestResultV5, DailyLogEntry, RiskStats } from '../api/backtest';
import client from '../api/client';

/* ============================================================
   常量
   ============================================================ */
const FACTOR_LABELS: Record<string, string> = {
  VOL: '波动率', ADR: '涨跌比', ERP: '股债比', FLOW: '北向资金',
  ETF: 'ETF资金', NHNL: '新高新低', TURN: '换手率', POS: '持仓结构',
  NBF: '融资余额', PCR: '看跌看涨比', NEWF: '新发基金',
};
const FACTOR_NAMES = Object.keys(FACTOR_LABELS);
const SIGNAL_LEVELS = ['S+', 'S', 'A', 'B', 'C', 'D', 'E'] as const;

const SIGNAL_COLORS: Record<string, string> = {
  'S+': '#7C3AED', S: '#2563EB', A: '#0891B2', B: '#65A30D',
  C: '#CA8A04', D: '#EA580C', E: '#DC2626',
};
const SIGNAL_BG: Record<string, string> = {
  'S+': 'bg-purple-100 text-purple-700', S: 'bg-blue-100 text-blue-700',
  A: 'bg-cyan-100 text-cyan-700', B: 'bg-lime-100 text-lime-700',
  C: 'bg-yellow-100 text-yellow-700', D: 'bg-orange-100 text-orange-700',
  E: 'bg-red-100 text-red-700',
};
const SIGNAL_LABELS: Record<string, string> = {
  'S+': '极度恐惧', S: '恐惧', A: '偏恐惧', B: '中性',
  C: '偏贪婪', D: '贪婪', E: '极度贪婪',
};
const ACTION_TYPE_OPTIONS = [
  { value: 'buy', label: '加仓' },
  { value: 'sell_half', label: '减仓' },
  { value: 'sell_all', label: '清仓' },
  { value: 'hold', label: '持有' },
] as const;

/* ============================================================
   默认参数
   ============================================================ */
const DEFAULT_ACTION_MAPPING: Record<string, ActionRule> = {
  'S+': { type: 'buy', mult: 2.0, label: '大幅加仓' },
  S: { type: 'buy', mult: 1.5, label: '加仓' },
  A: { type: 'buy', mult: 1.0, label: '小幅加仓' },
  B: { type: 'hold', mult: 0, label: '持有' },
  C: { type: 'sell_half', mult: 0.3, label: '减仓30%' },
  D: { type: 'sell_half', mult: 0.5, label: '减仓50%' },
  E: { type: 'sell_all', mult: 1.0, label: '清仓' },
};

const DEFAULT_MODEL_PARAMS: ModelParams = {
  signal_boundaries: [12, 25, 38, 52, 65, 80],
  signal_lag_days: 1,
  factor_weights: Object.fromEntries(FACTOR_NAMES.map(n => [n, parseFloat((1 / FACTOR_NAMES.length).toFixed(3))])),
  factor_enabled: Object.fromEntries(FACTOR_NAMES.map(n => [n, true])),
  action_mapping: { ...DEFAULT_ACTION_MAPPING },
  quantile_window: 252,
  sigmoid_k: 3.0,
  composite_method: 'weighted_sum',
  neutral_score: 50,
  max_position: 0.95,
  min_position: 0.05,
  stop_loss: -0.15,
  stop_loss_threshold: 1.0,
  stop_loss_reduce_pct: 50,
  take_profit: 0.30,
  take_profit_drawdown: 0.10,
  overheat_days: 10,
  overheat_factor: 0.7,
  pullback_lower: -0.08,
  pullback_buy_mult: 0.5,
  position_dev_lower: -0.05,
  position_dev_buy_mult: 0.3,
  base_buy_amount: 10000,
};

/* ============================================================
   类型
   ============================================================ */
interface BacktestStrategy {
  id: number;
  name: string;
  is_active: boolean;
  params: ModelParams;
}

interface ApiStrategy {
  id: string;
  name: string;
  description: string;
  params: Record<string, unknown>;
  is_default: boolean;
}

/* ============================================================
   子组件
   ============================================================ */

/** 方案管理栏 */
function StrategyBar({ strategies, activeId, onSelect, onSave, onDelete, onNew }: {
  strategies: BacktestStrategy[];
  activeId: number | null;
  onSelect: (id: number) => void;
  onSave: () => void;
  onDelete: (id: number) => void;
  onNew: () => void;
}) {
  return (
    <div className="card p-3 flex items-center gap-2 overflow-x-auto">
      <button onClick={onNew}
        className="px-3 py-1.5 text-xs border border-dashed border-gray-300 rounded-lg text-gray-400
                   hover:border-brand-500 hover:text-brand-500 transition-colors shrink-0">
        ＋ 新建方案
      </button>
      {strategies.map(s => (
        <button key={s.id} onClick={() => onSelect(s.id)}
          className={`px-3 py-1.5 text-xs rounded-lg border transition-all shrink-0 ${
            activeId === s.id ? 'bg-brand-500 text-white border-brand-500' : 'bg-white text-gray-600 border-gray-200 hover:border-brand-300'
          }`}>
          {s.name}
          {s.is_active && <span className="ml-1 text-[9px] opacity-70">(活跃)</span>}
        </button>
      ))}
      <div className="ml-auto flex gap-1 shrink-0">
        <button onClick={onSave} className="p-1.5 rounded hover:bg-gray-100 text-gray-400 hover:text-brand-500" title="保存方案">
          <Save className="w-3.5 h-3.5" />
        </button>
        {activeId !== null && (
          <button onClick={() => onDelete(activeId)} className="p-1.5 rounded hover:bg-gray-100 text-gray-400 hover:text-red-500" title="删除方案">
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        )}
      </div>
    </div>
  );
}

/** 折叠参数面板 */
function ParamPanel({ title, open, onToggle, badge, children }: {
  title: string; open: boolean; onToggle: () => void; badge?: string; children: React.ReactNode;
}) {
  return (
    <div className="card overflow-hidden">
      <button onClick={onToggle}
        className="w-full flex items-center justify-between px-4 py-2.5 text-xs font-medium text-gray-600 hover:bg-gray-50 transition-colors">
        <span className="flex items-center gap-2">
          {title}
          {badge && <span className="text-[9px] text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded-full">{badge}</span>}
        </span>
        <ChevronDown className={`w-3.5 h-3.5 text-gray-400 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && <div className="px-4 pb-3 space-y-2.5 border-t border-gray-100">{children}</div>}
    </div>
  );
}

/** 范围滑块 */
function RangeSlider({ label, value, min, max, step = 1, unit = '', onChange }: {
  label?: string; value: number; min: number; max: number; step?: number; unit?: string;
  onChange: (v: number) => void;
}) {
  const pct = ((value - min) / (max - min)) * 100;
  return (
    <div className="flex items-center gap-2 text-xs">
      {label && <span className="w-24 shrink-0 text-gray-500 text-[10px]">{label}</span>}
      <input type="range" min={min} max={max} step={step} value={value}
        onChange={e => onChange(parseFloat(e.target.value))}
        className="flex-1 h-1.5 bg-gray-200 rounded-full appearance-none cursor-pointer accent-brand-500
                   [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3.5 [&::-webkit-slider-thumb]:h-3.5
                   [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-brand-500 [&::-webkit-slider-thumb]:shadow-sm
                   [&::-webkit-slider-thumb]:cursor-pointer [&::-webkit-slider-thumb]:-mt-[5px]" />
      <span className="w-16 text-right text-[10px] font-mono text-gray-600 tabular-nums">
        {typeof value === 'number' ? value.toFixed(step < 1 ? 2 : 0) : value}{unit}
      </span>
    </div>
  );
}

/** ---- Category 1: 信号映射 ---- */
function SignalMappingPanel({ params, onChange }: { params: ModelParams; onChange: (p: ModelParams) => void }) {
  return (
    <div className="space-y-2">
      <p className="text-[10px] text-gray-400">调整6个信号分界线，分数低于边界→对应信号</p>
      {params.signal_boundaries.map((v, i) => {
        const sig = SIGNAL_LEVELS[i];
        return (
          <div key={i} className="flex items-center gap-2">
            <span className={`px-1.5 py-0.5 text-[10px] font-bold rounded ${SIGNAL_BG[sig]}`}>{sig}</span>
            <span className="text-[9px] text-gray-400 w-12">{SIGNAL_LABELS[sig]}</span>
            <input type="range" min={0} max={100} step={1} value={v}
              onChange={e => {
                const next = [...params.signal_boundaries];
                next[i] = parseInt(e.target.value);
                onChange({ ...params, signal_boundaries: next });
              }}
              className="flex-1 h-1.5 bg-gray-200 rounded-full appearance-none cursor-pointer accent-brand-500
                         [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3.5 [&::-webkit-slider-thumb]:h-3.5
                         [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-brand-500 [&::-webkit-slider-thumb]:shadow-sm
                         [&::-webkit-slider-thumb]:cursor-pointer [&::-webkit-slider-thumb]:-mt-[5px]" />
            <span className="w-8 text-right text-[10px] font-mono text-gray-600 tabular-nums">{v}</span>
          </div>
        );
      })}
      <div className="pt-1 border-t border-gray-100">
        <RangeSlider label="信号滞后天数" value={params.signal_lag_days} min={0} max={5} step={1} unit="天"
          onChange={v => onChange({ ...params, signal_lag_days: v })} />
      </div>
    </div>
  );
}

/** ---- Category 2: 因子权重 ---- */
function FactorWeightsPanel({ params, onChange }: { params: ModelParams; onChange: (p: ModelParams) => void }) {
  const enabledWeight = useMemo(() => {
    return FACTOR_NAMES.reduce((sum, n) => {
      return sum + (params.factor_enabled[n] ? (params.factor_weights[n] || 0) : 0);
    }, 0);
  }, [params]);

  return (
    <div className="space-y-1.5">
      <p className="text-[10px] text-gray-400">开关因子 + 滑块调节权重，有效权重总和应≈1.0</p>
      {FACTOR_NAMES.map(name => {
        const enabled = params.factor_enabled[name] ?? true;
        const weight = params.factor_weights[name] ?? parseFloat((1 / FACTOR_NAMES.length).toFixed(3));
        return (
          <div key={name} className={`flex items-center gap-2 text-xs ${!enabled ? 'opacity-40' : ''}`}>
            <button onClick={() => onChange({ ...params, factor_enabled: { ...params.factor_enabled, [name]: !enabled } })}
              className={`w-7 h-4 rounded-full transition-colors relative ${enabled ? 'bg-brand-500' : 'bg-gray-300'}`}>
              <span className={`absolute top-0.5 ${enabled ? 'right-0.5' : 'left-0.5'} w-3 h-3 bg-white rounded-full shadow transition-all`} />
            </button>
            <span className="w-8 shrink-0 font-mono text-[10px] text-gray-500">{name}</span>
            <span className="w-12 shrink-0 text-[10px] text-gray-600">{FACTOR_LABELS[name]}</span>
            <input type="range" min={0} max={0.5} step={0.005} value={weight}
              disabled={!enabled}
              onChange={e => onChange({ ...params, factor_weights: { ...params.factor_weights, [name]: parseFloat(e.target.value) } })}
              className="flex-1 h-1.5 bg-gray-200 rounded-full appearance-none cursor-pointer accent-brand-500 disabled:opacity-30
                         [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3.5 [&::-webkit-slider-thumb]:h-3.5
                         [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-brand-500 [&::-webkit-slider-thumb]:shadow-sm
                         [&::-webkit-slider-thumb]:cursor-pointer [&::-webkit-slider-thumb]:-mt-[5px]" />
            <span className="w-10 text-right text-[10px] font-mono text-gray-400 tabular-nums">{weight.toFixed(3)}</span>
          </div>
        );
      })}
      <p className="text-[10px] text-gray-400 pt-1 border-t border-gray-100">
        有效总和：
        <span className={`font-mono ${Math.abs(enabledWeight - 1.0) > 0.05 ? 'text-red-500 font-bold' : 'text-green-500'}`}>
          {enabledWeight.toFixed(3)}
        </span>
      </p>
    </div>
  );
}

/** ---- Category 3: 行动映射 ---- */
function ActionMappingPanel({ params, onChange }: { params: ModelParams; onChange: (p: ModelParams) => void }) {
  return (
    <div className="space-y-1.5">
      <p className="text-[10px] text-gray-400">7级信号 → 行动类型 + 操作倍数</p>
      {SIGNAL_LEVELS.map(sig => {
        const rule = params.action_mapping[sig] || DEFAULT_ACTION_MAPPING[sig];
        return (
          <div key={sig} className="flex items-center gap-2 text-xs">
            <span className={`px-1.5 py-0.5 text-[10px] font-bold rounded ${SIGNAL_BG[sig]}`}>{sig}</span>
            <select value={rule.type}
              onChange={e => {
                const newType = e.target.value as ActionRule['type'];
                const autoLabel = ACTION_TYPE_OPTIONS.find(o => o.value === newType)?.label || '';
                const newMapping = { ...params.action_mapping, [sig]: { ...rule, type: newType, label: autoLabel } };
                onChange({ ...params, action_mapping: newMapping });
              }}
              className="px-2 py-0.5 border border-gray-200 rounded text-[10px] bg-white">
              {ACTION_TYPE_OPTIONS.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
            </select>
            <input type="range" min={0} max={3} step={0.1} value={rule.mult}
              onChange={e => {
                const newMapping = { ...params.action_mapping, [sig]: { ...rule, mult: parseFloat(e.target.value) } };
                onChange({ ...params, action_mapping: newMapping });
              }}
              className="flex-1 h-1.5 bg-gray-200 rounded-full appearance-none cursor-pointer accent-brand-500
                         [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:w-3.5 [&::-webkit-slider-thumb]:h-3.5
                         [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-brand-500 [&::-webkit-slider-thumb]:shadow-sm
                         [&::-webkit-slider-thumb]:cursor-pointer [&::-webkit-slider-thumb]:-mt-[5px]" />
            <span className="w-6 text-right text-[10px] font-mono text-gray-400 tabular-nums">{rule.mult.toFixed(1)}</span>
            <span className="w-14 text-[10px] text-gray-500">{rule.label}</span>
          </div>
        );
      })}
    </div>
  );
}

/** ---- Category 4: 因子引擎 ---- */
function FactorEnginePanel({ params, onChange }: { params: ModelParams; onChange: (p: ModelParams) => void }) {
  return (
    <div className="space-y-2">
      <p className="text-[10px] text-gray-400">全局因子引擎参数，替代每因子单独Sigmoid设置</p>
      <RangeSlider label="分位数窗口" value={params.quantile_window} min={60} max={504} step={1} unit="天"
        onChange={v => onChange({ ...params, quantile_window: v })} />
      <RangeSlider label="Sigmoid陡峭度" value={params.sigmoid_k} min={0.5} max={10} step={0.5}
        onChange={v => onChange({ ...params, sigmoid_k: v })} />
      <div className="flex items-center gap-2 text-xs">
        <span className="w-24 shrink-0 text-gray-500 text-[10px]">聚合方式</span>
        <select value={params.composite_method}
          onChange={e => onChange({ ...params, composite_method: e.target.value })}
          className="flex-1 px-2 py-0.5 border border-gray-200 rounded text-[10px] bg-white">
          <option value="weighted_sum">加权求和 (weighted_sum)</option>
          <option value="geometric_mean">几何平均 (geometric_mean)</option>
        </select>
      </div>
      <RangeSlider label="中性分数" value={params.neutral_score} min={30} max={70} step={1}
        onChange={v => onChange({ ...params, neutral_score: v })} />
    </div>
  );
}

/** ---- Category 5: 仓位风控 ---- */
function PositionRiskPanel({ params, onChange }: { params: ModelParams; onChange: (p: ModelParams) => void }) {
  const u = (key: keyof ModelParams, v: number) => onChange({ ...params, [key]: v });
  return (
    <div className="space-y-3">
      {/* 仓位限制 */}
      <div>
        <p className="text-[10px] text-gray-500 font-medium mb-1">📏 仓位限制</p>
        <RangeSlider label="最大仓位" value={params.max_position} min={0.5} max={1.0} step={0.05} unit=""
          onChange={v => u('max_position', v)} />
        <div className="mt-1">
          <RangeSlider label="最小仓位" value={params.min_position} min={0} max={0.3} step={0.05} unit=""
            onChange={v => u('min_position', v)} />
        </div>
      </div>

      {/* 止损 */}
      <div>
        <p className="text-[10px] text-gray-500 font-medium mb-1">🛡️ 止损</p>
        <RangeSlider label="止损线" value={params.stop_loss} min={-0.30} max={-0.05} step={0.01} unit=""
          onChange={v => u('stop_loss', v)} />
        <div className="mt-1"><RangeSlider label="触发阈值倍数" value={params.stop_loss_threshold} min={0.5} max={2.0} step={0.1}
          onChange={v => u('stop_loss_threshold', v)} /></div>
        <div className="mt-1"><RangeSlider label="止损减仓比例" value={params.stop_loss_reduce_pct} min={10} max={100} step={5} unit="%"
          onChange={v => u('stop_loss_reduce_pct', v)} /></div>
      </div>

      {/* 止盈 */}
      <div>
        <p className="text-[10px] text-gray-500 font-medium mb-1">💰 止盈</p>
        <RangeSlider label="止盈线" value={params.take_profit} min={0.10} max={1.0} step={0.05} unit=""
          onChange={v => u('take_profit', v)} />
        <div className="mt-1"><RangeSlider label="止盈回撤触发" value={params.take_profit_drawdown} min={0.03} max={0.30} step={0.01} unit=""
          onChange={v => u('take_profit_drawdown', v)} /></div>
      </div>

      {/* 过热 */}
      <div>
        <p className="text-[10px] text-gray-500 font-medium mb-1">🔥 过热检测</p>
        <RangeSlider label="连续天数" value={params.overheat_days} min={3} max={30} step={1} unit="天"
          onChange={v => u('overheat_days', v)} />
        <div className="mt-1"><RangeSlider label="减仓系数" value={params.overheat_factor} min={0.3} max={1.0} step={0.05}
          onChange={v => u('overheat_factor', v)} /></div>
      </div>

      {/* 回调/偏离 */}
      <div>
        <p className="text-[10px] text-gray-500 font-medium mb-1">📉 回调/偏离加仓</p>
        <RangeSlider label="回调下限" value={params.pullback_lower} min={-0.20} max={-0.02} step={0.01}
          onChange={v => u('pullback_lower', v)} />
        <div className="mt-1"><RangeSlider label="回调加仓倍数" value={params.pullback_buy_mult} min={0.1} max={1.0} step={0.1}
          onChange={v => u('pullback_buy_mult', v)} /></div>
        <div className="mt-1"><RangeSlider label="偏离下限" value={params.position_dev_lower} min={-0.20} max={-0.01} step={0.01}
          onChange={v => u('position_dev_lower', v)} /></div>
        <div className="mt-1"><RangeSlider label="偏离加仓倍数" value={params.position_dev_buy_mult} min={0.1} max={1.0} step={0.1}
          onChange={v => u('position_dev_buy_mult', v)} /></div>
      </div>

      {/* 基础金额 */}
      <div>
        <p className="text-[10px] text-gray-500 font-medium mb-1">💵 基础金额</p>
        <RangeSlider label="单次加仓金额" value={params.base_buy_amount} min={1000} max={50000} step={1000} unit="元"
          onChange={v => u('base_buy_amount', v)} />
      </div>
    </div>
  );
}

/** ---- 回测结果展示 ---- */
function BacktestResultPanel({ result }: { result: BacktestResultV5 | null }) {
  if (!result) {
    return (
      <div className="card p-8 text-center">
        <TrendingUp className="w-8 h-8 text-gray-300 mx-auto mb-2" />
        <p className="text-gray-500 text-sm font-medium">点击「运行回测」查看结果</p>
        <p className="text-[10px] text-gray-300 mt-1">基于 V5.0 信号系统进行历史回测</p>
      </div>
    );
  }

  // 8个指标卡
  const metrics = [
    { label: '初始金额', value: '¥100,000', cls: 'text-gray-700' },
    { label: '最终金额', value: `¥${(100000 * (1 + result.total_return / 100)).toLocaleString('zh-CN', { maximumFractionDigits: 0 })}`, cls: result.total_return >= 0 ? 'text-red-500' : 'text-green-500' },
    { label: '总收益率', value: `${result.total_return.toFixed(2)}%`, cls: result.total_return >= 0 ? 'text-red-500' : 'text-green-500' },
    { label: '信号准确率', value: `${(result.signal_accuracy ?? 0).toFixed(1)}%`, cls: 'text-brand-500' },
    { label: '最大回撤', value: `${result.max_drawdown.toFixed(2)}%`, cls: 'text-green-500' },
    { label: '夏普比率', value: result.sharpe_ratio.toFixed(2), cls: result.sharpe_ratio >= 1 ? 'text-brand-500' : 'text-gray-700' },
    { label: '风控触发', value: `${result.risk_stats?.risk_triggers ?? 0}次`, cls: 'text-orange-500', icon: <Shield className="w-3 h-3" /> },
    { label: '回调加仓', value: `${(result.risk_stats?.pullback_buys ?? 0) + (result.risk_stats?.deviation_buys ?? 0)}次`, cls: 'text-cyan-500' },
  ];

  // SVG 权益曲线
  const renderCurve = () => {
    const curve = result.equity_curve;
    if (!curve || curve.length < 2) {
      return <svg viewBox="0 0 500 160" className="w-full h-36"><text x="250" y="80" textAnchor="middle" fill="#94A3B8" fontSize="10">暂无曲线数据</text></svg>;
    }

    const w = 500, h = 160, padX = 30, padY = 20;
    const innerW = w - padX * 2, innerH = h - padY * 2;

    const values = curve.map(p => p.value);
    const minV = Math.min(...values), maxV = Math.max(...values);
    const rangeV = maxV - minV || 1;

    const points = curve.map((p, i) => {
      const x = padX + (i / (curve.length - 1)) * innerW;
      const y = padY + innerH - ((p.value - minV) / rangeV) * innerH;
      return { x, y };
    });
    const pathD = points.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ');

    // 面积填充路径
    const areaD = `${pathD} L${points[points.length - 1].x},${padY + innerH} L${points[0].x},${padY + innerH} Z`;

    // 基准线
    const baseY = padY + innerH - ((values[0] - minV) / rangeV) * innerH;

    // 基准曲线
    const benchCurve = result.benchmark_curve;
    let benchPathD = '';
    if (benchCurve && benchCurve.length > 1) {
      const bValues = benchCurve.map(p => p.value);
      const bMin = Math.min(minV, ...bValues), bMax = Math.max(maxV, ...bValues);
      const bRange = bMax - bMin || 1;
      const bPoints = benchCurve.map((p, i) => {
        const x = padX + (i / (benchCurve.length - 1)) * innerW;
        const y = padY + innerH - ((p.value - bMin) / bRange) * innerH;
        return { x, y };
      });
      benchPathD = bPoints.map((p, i) => `${i === 0 ? 'M' : 'L'}${p.x},${p.y}`).join(' ');
    }

    return (
      <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-36">
        <defs>
          <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#14B8A6" stopOpacity="0.3" />
            <stop offset="100%" stopColor="#14B8A6" stopOpacity="0.02" />
          </linearGradient>
        </defs>
        {/* 基准起始线 */}
        <line x1={padX} y1={baseY} x2={w - padX} y2={baseY} stroke="#94A3B8" strokeWidth="1" strokeDasharray="4,2" />
        {/* 面积填充 */}
        <path d={areaD} fill="url(#areaGrad)" />
        {/* 策略曲线 */}
        <path d={pathD} fill="none" stroke="#14B8A6" strokeWidth="2" />
        {/* 基准曲线 */}
        {benchPathD && <path d={benchPathD} fill="none" stroke="#94A3B8" strokeWidth="1.5" strokeDasharray="3,3" />}
        {/* 图例 */}
        <rect x={padX} y={6} width={12} height={3} fill="#14B8A6" rx={1} />
        <text x={padX + 16} y={10} fill="#14B8A6" fontSize="8">策略</text>
        <rect x={padX + 50} y={6} width={12} height={3} fill="#94A3B8" rx={1} />
        <text x={padX + 66} y={10} fill="#94A3B8" fontSize="8">基准</text>
      </svg>
    );
  };

  // 操作汇总
  const summaryText = result.summary_text || '';

  // daily_log
  const dailyLog = result.daily_log || [];

  return (
    <div className="card p-4 space-y-4">
      <h3 className="text-sm font-bold text-gray-700">回测结果</h3>

      {/* 8指标卡 */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        {metrics.map(it => (
          <div key={it.label} className="bg-gray-50 rounded-lg p-2.5">
            <p className="text-[10px] text-gray-400 flex items-center gap-1">
              {it.icon}{it.label}
            </p>
            <p className={`text-base font-bold ${it.cls}`}>{it.value}</p>
          </div>
        ))}
      </div>

      {/* 收益率曲线 */}
      <div className="bg-gray-50 rounded-lg p-3">
        <p className="text-[10px] text-gray-400 mb-1">收益率曲线（策略 vs 基准）</p>
        {renderCurve()}
      </div>

      {/* 操作汇总 */}
      {summaryText && (
        <div className="bg-brand-50 rounded-lg p-2.5 flex items-center gap-2">
          <TrendingUp className="w-3.5 h-3.5 text-brand-500 shrink-0" />
          <p className="text-[11px] text-brand-700 font-medium">{summaryText}</p>
        </div>
      )}

      {/* 风控统计 */}
      {result.risk_stats && (result.risk_stats.risk_triggers > 0 || result.risk_stats.pullback_buys > 0) && (
        <div className="bg-orange-50 rounded-lg p-2.5 flex items-center gap-2">
          <AlertTriangle className="w-3.5 h-3.5 text-orange-500 shrink-0" />
          <p className="text-[10px] text-orange-700">
            风控触发 {result.risk_stats.risk_triggers}次
            （止损{result.risk_stats.stop_loss_triggers}·过热{result.risk_stats.overheat_triggers}）
            · 回调加仓{result.risk_stats.pullback_buys}·偏离加仓{result.risk_stats.deviation_buys}
          </p>
        </div>
      )}

      {/* 每日操作日志 */}
      {dailyLog.length > 0 && (
        <div>
          <h4 className="text-xs font-medium text-gray-600 mb-1.5">每日操作日志（最近{dailyLog.length}条）</h4>
          <div className="overflow-x-auto max-h-48 overflow-y-auto border border-gray-200 rounded-lg">
            <table className="w-full text-[10px] text-left">
              <thead className="bg-gray-50 sticky top-0">
                <tr className="text-gray-400">
                  <th className="px-2 py-1">日期</th>
                  <th className="px-2 py-1">信号</th>
                  <th className="px-2 py-1">净值</th>
                  <th className="px-2 py-1">建议操作</th>
                  <th className="px-2 py-1">持仓市值</th>
                  <th className="px-2 py-1">原因</th>
                </tr>
              </thead>
              <tbody>
                {dailyLog.map((log, i) => (
                  <tr key={i} className="border-t border-gray-100 hover:bg-gray-50">
                    <td className="px-2 py-1 font-mono text-gray-600">{log.date}</td>
                    <td className="px-2 py-1">
                      <span className={`px-1 py-0.5 rounded text-[9px] font-bold ${SIGNAL_BG[log.signal] || ''}`}>{log.signal}</span>
                    </td>
                    <td className="px-2 py-1 font-mono text-gray-700">{log.nav.toFixed(2)}</td>
                    <td className="px-2 py-1 text-gray-700">{log.advice_text}</td>
                    <td className="px-2 py-1 font-mono text-gray-600">¥{log.position_value.toLocaleString('zh-CN', { maximumFractionDigits: 0 })}</td>
                    <td className="px-2 py-1 text-gray-400 max-w-[200px] truncate">{log.reason}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}
    </div>
  );
}


/* ============================================================
   主页面
   ============================================================ */
export default function Backtest() {
  const [strategies, setStrategies] = useState<BacktestStrategy[]>([
    { id: 1, name: '稳健方案', is_active: true, params: { ...DEFAULT_MODEL_PARAMS } },
    { id: 2, name: '激进方案', is_active: false, params: { ...DEFAULT_MODEL_PARAMS, action_mapping: { ...DEFAULT_ACTION_MAPPING, 'B': { type: 'buy', mult: 0.5, label: '小幅加仓' } }, overheat_days: 15, stop_loss: -0.20 } },
  ]);
  const [activeId, setActiveId] = useState<number | null>(1);
  const [panels, setPanels] = useState<Record<string, boolean>>({
    signal: true, factors: false, action: false, engine: false, risk: false,
  });
  const [running, setRunning] = useState(false);
  const [result, setResult] = useState<BacktestResultV5 | null>(null);
  const [error, setError] = useState<string | null>(null);

  const activeStrategy = strategies.find(s => s.id === activeId) ?? null;
  const togglePanel = (key: string) => setPanels(prev => ({ ...prev, [key]: !prev[key] }));

  const updateParams = (newParams: ModelParams) => {
    if (!activeId) return;
    setStrategies(prev => prev.map(s => s.id !== activeId ? s : { ...s, params: newParams }));
  };

  /** 运行回测 */
  const handleRun = async () => {
    if (!activeStrategy) return;
    setRunning(true);
    setError(null);
    try {
      const p = activeStrategy.params;
      const data = await runBacktestV5({
        index_code: 'SH000300',
        start_date: '2024-01-01',
        end_date: new Date().toISOString().slice(0, 10),
        initial_capital: 100000,
        signal_boundaries: p.signal_boundaries,
        signal_lag_days: p.signal_lag_days,
        factor_weights: p.factor_weights,
        factor_enabled: p.factor_enabled,
        action_mapping: p.action_mapping,
        quantile_window: p.quantile_window,
        sigmoid_k: p.sigmoid_k,
        composite_method: p.composite_method,
        neutral_score: p.neutral_score,
        risk_params: {
          max_position: p.max_position,
          min_position: p.min_position,
          stop_loss: p.stop_loss,
          stop_loss_threshold: p.stop_loss_threshold,
          stop_loss_reduce_pct: p.stop_loss_reduce_pct,
          take_profit: p.take_profit,
          take_profit_drawdown: p.take_profit_drawdown,
          overheat_days: p.overheat_days,
          overheat_factor: p.overheat_factor,
          pullback_lower: p.pullback_lower,
          pullback_buy_mult: p.pullback_buy_mult,
          position_dev_lower: p.position_dev_lower,
          position_dev_buy_mult: p.position_dev_buy_mult,
          base_buy_amount: p.base_buy_amount,
        },
      });
      setResult(data);
    } catch (err: any) {
      setError(err?.message || '回测运行失败，请重试');
    } finally {
      setRunning(false);
    }
  };

  /** 保存方案 */
  const handleSave = async () => {
    if (!activeStrategy) return;
    try {
      await saveBacktestStrategyV5({ name: activeStrategy.name, params_json: activeStrategy.params as any });
    } catch (err: any) {
      alert(err?.message || '保存方案失败');
    }
  };

  /** 删除方案 */
  const handleDelete = async (id: number) => {
    try {
      await deleteBacktestStrategyV5(id);
      setStrategies(prev => prev.filter(s => s.id !== id));
      if (activeId === id) {
        const remaining = strategies.filter(s => s.id !== id);
        setActiveId(remaining.length > 0 ? remaining[0].id : null);
      }
    } catch (err: any) {
      alert(err?.message || '删除方案失败');
    }
  };

  return (
    <div className="max-w-5xl mx-auto space-y-4">
      <div>
        <h1 className="text-xl font-bold text-gray-800">历史回溯 V5.0</h1>
        <p className="text-xs text-gray-400 mt-0.5">方案管理 · 5类参数 · 策略回测 · 风控统计</p>
      </div>

      {/* 方案管理栏 */}
      <StrategyBar strategies={strategies} activeId={activeId} onSelect={setActiveId}
        onSave={handleSave} onDelete={handleDelete}
        onNew={() => {
          const newId = Math.max(0, ...strategies.map(s => s.id)) + 1;
          setStrategies(prev => [...prev, { id: newId, name: `新方案${newId}`, is_active: false, params: { ...DEFAULT_MODEL_PARAMS } }]);
          setActiveId(newId);
        }}
      />

      {/* 5类折叠参数面板 */}
      <div className="space-y-2">
        <ParamPanel title="信号映射边界" open={panels.signal} onToggle={() => togglePanel('signal')} badge="6滑块">
          <SignalMappingPanel params={activeStrategy?.params ?? DEFAULT_MODEL_PARAMS} onChange={updateParams} />
        </ParamPanel>

        <ParamPanel title="因子权重" open={panels.factors} onToggle={() => togglePanel('factors')} badge="11因子">
          <FactorWeightsPanel params={activeStrategy?.params ?? DEFAULT_MODEL_PARAMS} onChange={updateParams} />
        </ParamPanel>

        <ParamPanel title="行动映射" open={panels.action} onToggle={() => togglePanel('action')} badge="7信号→行动">
          <ActionMappingPanel params={activeStrategy?.params ?? DEFAULT_MODEL_PARAMS} onChange={updateParams} />
        </ParamPanel>

        <ParamPanel title="因子引擎" open={panels.engine} onToggle={() => togglePanel('engine')} badge="4参数">
          <FactorEnginePanel params={activeStrategy?.params ?? DEFAULT_MODEL_PARAMS} onChange={updateParams} />
        </ParamPanel>

        <ParamPanel title="仓位风控" open={panels.risk} onToggle={() => togglePanel('risk')} badge="13参数">
          <PositionRiskPanel params={activeStrategy?.params ?? DEFAULT_MODEL_PARAMS} onChange={updateParams} />
        </ParamPanel>
      </div>

      {/* 运行回测按钮 */}
      <button onClick={handleRun} disabled={running}
        className={`w-full py-2.5 rounded-lg text-sm font-medium text-white transition-colors ${
          running ? 'bg-gray-400 cursor-not-allowed' : 'bg-brand-500 hover:bg-brand-600'
        }`}>
        {running ? '回测运行中...' : '▶ 运行回测'}
      </button>

      {/* 错误提示 */}
      {error && (
        <div className="card p-4 text-center">
          <p className="text-red-500 text-sm">{error}</p>
          <button onClick={handleRun} className="mt-2 px-4 py-1.5 text-xs bg-brand-500 text-white rounded-lg hover:bg-brand-600">重试</button>
        </div>
      )}

      {/* 回测结果 */}
      <BacktestResultPanel result={result} />
    </div>
  );
}
