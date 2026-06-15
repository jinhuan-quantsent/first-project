/**
 * Backtest - V5.0 历史回溯页
 * 方案管理栏 + 5类折叠参数面板 + 回测结果展示
 */
import { useState, useEffect, useCallback } from 'react';
import { SlidersHorizontal, Save, Trash2, Play, RefreshCw, TrendingUp } from 'lucide-react';
import { clsx } from 'clsx';
import { runBacktestV5, saveBacktestStrategyV5, deleteBacktestStrategyV5 } from '../api/backtest';
import client from '../api/client';

/* ============================================================
   11 因子中英文映射
   ============================================================ */
const FACTOR_LABELS: Record<string, string> = {
  VOL:  '波动率',
  ADR:  '涨跌比',
  ERP:  '股债比',
  FLOW: '北向资金',
  ETF:  'ETF资金',
  NHNL: '新高新低',
  TURN: '换手率',
  POS:  '持仓结构',
  NBF:  '融资余额',
  PCR:  '看跌看涨比',
  NEWF: '新发基金',
};
const FACTOR_NAMES = Object.keys(FACTOR_LABELS);
const DEFAULT_WEIGHT = 1 / FACTOR_NAMES.length; // ≈0.091
const DEFAULT_SIGMOID = { c: 0.50, k: 3.0 };

/* ============================================================
   类型
   ============================================================ */
interface BacktestStrategy {
  id: number;
  name: string;
  is_active: boolean;
  params: {
    signal_boundaries: number[];
    factor_weights: Record<string, number>;
    sigmoid_params: Record<string, { c: number; k: number }>;
    position_matrix: number[][];
    risk_params: { cost_threshold: number; frequency_days: number; max_adjustment: number };
  };
}

/** API 返回的策略格式（id 为字符串） */
interface ApiStrategy {
  id: string;
  name: string;
  description: string;
  params: {
    buy_signals?: string[];
    sell_signals?: string[];
    hold_signals?: string[];
  };
  is_default: boolean;
}

/** API 返回的策略格式（id 为字符串） */
interface ApiStrategy {
  id: string;
  name: string;
  description: string;
  params: {
    buy_signals?: string[];
    sell_signals?: string[];
    hold_signals?: string[];
  };
  is_default: boolean;
}

interface BacktestResult {
  total_return: number;
  annual_return: number;
  max_drawdown: number;
  win_rate: number;
  sharpe: number;
  benchmark_return: number;
  equity_curve?: { date: string; value: number }[];
}

const DEFAULT_PARAMS: BacktestStrategy['params'] = {
  signal_boundaries: [12, 25, 38, 52, 65, 80],
  factor_weights: Object.fromEntries(FACTOR_NAMES.map(n => [n, DEFAULT_WEIGHT])),
  sigmoid_params: Object.fromEntries(FACTOR_NAMES.map(n => [n, { ...DEFAULT_SIGMOID }])),
  position_matrix: [
    [0.00, 0.00, 0.00, 0.00, 0.00, 0.00, 0.00], // S+ (空仓)
    [0.00, 0.00, 0.00, 0.20, 0.20, 0.30, 0.30], // S
    [0.00, 0.00, 0.20, 0.30, 0.40, 0.50, 0.50], // A
    [0.00, 0.20, 0.30, 0.40, 0.50, 0.60, 0.60], // B
    [0.30, 0.40, 0.50, 0.60, 0.70, 0.80, 0.80], // C
    [0.50, 0.60, 0.70, 0.80, 0.90, 0.95, 0.95], // D
    [0.70, 0.80, 0.90, 0.95, 1.00, 1.00, 1.00], // E (满仓)
  ],
  risk_params: { cost_threshold: 0.015, frequency_days: 7, max_adjustment: 0.20 },
};

/** 将 API 返回的策略转换为前端格式 */
function mapApiStrategy(s: ApiStrategy, idx: number): BacktestStrategy {
  return {
    id: idx + 1,
    name: s.name,
    is_active: s.is_default,
    params: { ...DEFAULT_PARAMS },
  };
}

/** 获取 API 策略列表 */
async function fetchStrategiesFromApi(): Promise<ApiStrategy[]> {
  try {
    const res = await client.get<{ code: number; data: ApiStrategy[]; message: string }>(
      '/api/v5/backtest/strategies',
    );
    if (res.data.code === 0 && Array.isArray(res.data.data)) {
      return res.data.data;
    }
    return [];
  } catch {
    // 静默失败，使用硬编码备用策略
    return [];
  }
}

/* ============================================================
   子组件
   ============================================================ */

/** 方案管理栏 */
function StrategyBar({
  strategies,
  activeId,
  onSelect,
  onSave,
  onDelete,
  onNew,
}: {
  strategies: BacktestStrategy[];
  activeId: number | null;
  onSelect: (id: number) => void;
  onSave: () => void;
  onDelete: (id: number) => void;
  onNew: () => void;
}) {
  return (
    <div className="card p-3 flex items-center gap-2 overflow-x-auto">
      <button
        onClick={onNew}
        className="px-3 py-1.5 text-xs border border-dashed border-gray-300 rounded-lg text-gray-400
                   hover:border-brand-500 hover:text-brand-500 transition-colors shrink-0"
      >
        ＋ 新建方案
      </button>

      {strategies.map((s) => (
        <button
          key={s.id}
          onClick={() => onSelect(s.id)}
          className={`px-3 py-1.5 text-xs rounded-lg border transition-all shrink-0 ${
            activeId === s.id
              ? 'bg-brand-500 text-white border-brand-500'
              : 'bg-white text-gray-600 border-gray-200 hover:border-brand-300'
          }`}
        >
          {s.name}
          {s.is_active && <span className="ml-1 text-[9px]">(活跃)</span>}
        </button>
      ))}

      <div className="ml-auto flex gap-1 shrink-0">
        <button onClick={onSave} className="p-1.5 rounded hover:bg-gray-100 text-gray-400 hover:text-brand-500 transition-colors" title="保存方案">
          <Save className="w-3.5 h-3.5" />
        </button>
        {activeId !== null && (
          <button onClick={() => onDelete(activeId)} className="p-1.5 rounded hover:bg-gray-100 text-gray-400 hover:text-red-500 transition-colors" title="删除方案">
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        )}
      </div>
    </div>
  );
}

/** 折叠参数面板（通用） */
function ParamPanel({
  title,
  open,
  onToggle,
  children,
}: {
  title: string;
  open: boolean;
  onToggle: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="card overflow-hidden">
      <button
        onClick={onToggle}
        className="w-full flex items-center justify-between px-4 py-2.5 text-xs font-medium text-gray-600
                   hover:bg-gray-50 transition-colors"
      >
        <span>{title}</span>
        <svg className={`w-3.5 h-3.5 text-gray-400 transition-transform ${open ? 'rotate-180' : ''}`} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
          <path strokeLinecap="round" strokeLinejoin="round" d="M19 9l-7 7-7-7" />
        </svg>
      </button>
      {open && <div className="px-4 pb-3 space-y-2 border-t border-gray-100">{children}</div>}
    </div>
  );
}

/** 回测结果展示 */
function BacktestResultPanel({ result }: { result: BacktestResult | null }) {
  if (!result) {
    return (
      <div className="card p-8 text-center">
        <TrendingUp className="w-8 h-8 text-gray-300 mx-auto mb-2" />
        <p className="text-gray-500 text-sm font-medium">点击「运行回测」查看结果</p>
        <p className="text-[10px] text-gray-300 mt-1">基于 V5.0 信号系统进行历史回测</p>
      </div>
    );
  }

  const items = [
    { label: '累计收益', value: `${result.total_return.toFixed(2)}%`, cls: result.total_return >= 0 ? 'text-red-500' : 'text-green-500' },
    { label: '年化收益', value: `${result.annual_return.toFixed(2)}%`, cls: result.annual_return >= 0 ? 'text-red-500' : 'text-green-500' },
    { label: '最大回撤', value: `${result.max_drawdown.toFixed(2)}%`, cls: 'text-green-500' },
    { label: '胜率',     value: `${result.win_rate.toFixed(1)}%`,  cls: 'text-gray-700' },
    { label: '夏普比率', value: result.sharpe.toFixed(2),          cls: result.sharpe >= 1 ? 'text-brand-500' : 'text-gray-700' },
    { label: '基准收益', value: `${result.benchmark_return.toFixed(2)}%`, cls: result.benchmark_return >= 0 ? 'text-red-500' : 'text-green-500' },
  ];

  /** 用真实equity_curve数据生成SVG折线 */
  const renderCurve = () => {
    const curve = result.equity_curve;
    if (!curve || curve.length < 2) {
      // 无曲线数据时显示占位
      return (
        <svg viewBox="0 0 400 120" className="w-full h-32">
          <text x="200" y="60" textAnchor="middle" fill="#94A3B8" fontSize="10">暂无曲线数据</text>
        </svg>
      );
    }

    const w = 400;
    const h = 120;
    const padX = 20;
    const padY = 15;
    const innerW = w - padX * 2;
    const innerH = h - padY * 2;

    const values = curve.map((p) => p.value);
    const minV = Math.min(...values);
    const maxV = Math.max(...values);
    const rangeV = maxV - minV || 1;

    const points = curve.map((p, i) => {
      const x = padX + (i / (curve.length - 1)) * innerW;
      const y = padY + innerH - ((p.value - minV) / rangeV) * innerH;
      return `${x},${y}`;
    }).join(' ');

    // 基准线（起始值水平线）
    const baseY = padY + innerH - ((values[0] - minV) / rangeV) * innerH;

    return (
      <svg viewBox={`0 0 ${w} ${h}`} className="w-full h-32">
        {/* 基准起始线 */}
        <line x1={padX} y1={baseY} x2={w - padX} y2={baseY} stroke="#94A3B8" strokeWidth="1" strokeDasharray="4,2" />
        {/* 策略曲线 */}
        <polyline
          fill="none" stroke="#14B8A6" strokeWidth="2"
          points={points}
        />
        <text x={w - padX - 5} y={12} fill="#94A3B8" fontSize="8" textAnchor="end">基准</text>
        <text x={w - padX - 5} y={24} fill="#14B8A6" fontSize="8" textAnchor="end">策略</text>
      </svg>
    );
  };

  return (
    <div className="card p-4 space-y-4">
      <h3 className="text-sm font-bold text-gray-700">回测结果</h3>
      <div className="grid grid-cols-2 md:grid-cols-3 gap-3">
        {items.map((it) => (
          <div key={it.label} className="bg-gray-50 rounded-lg p-3">
            <p className="text-[10px] text-gray-400">{it.label}</p>
            <p className={`text-lg font-bold ${it.cls}`}>{it.value}</p>
          </div>
        ))}
      </div>

      {/* 收益率曲线（真实数据） */}
      <div className="bg-gray-50 rounded-lg p-3">
        <p className="text-[10px] text-gray-400 mb-2">收益率曲线（策略 vs 基准）</p>
        {renderCurve()}
      </div>
    </div>
  );
}

/* ============================================================
   主页面
   ============================================================ */
export default function Backtest() {
  const [strategies, setStrategies] = useState<BacktestStrategy[]>([
    { id: 1, name: '稳健方案', is_active: true,  params: { ...DEFAULT_PARAMS, risk_params: { cost_threshold: 0.015, frequency_days: 7, max_adjustment: 0.20 } } },
    { id: 2, name: '激进方案', is_active: false, params: { ...DEFAULT_PARAMS, risk_params: { cost_threshold: 0.010, frequency_days: 5, max_adjustment: 0.30 } } },
  ]);
  const [activeId,    setActiveId]    = useState<number | null>(1);
  const [panels,      setPanels]      = useState<Record<string, boolean>>({
    signal: true, factors: false, sigmoid: false, position: false, risk: false,
  });
  const [running,      setRunning]     = useState(false);
  const [result,       setResult]      = useState<BacktestResult | null>(null);
  const [error,        setError]       = useState<string | null>(null);
  const [loadingStrategies, setLoadingStrategies] = useState(false);

  /** 从 API 加载策略列表 */
  useEffect(() => {
    let cancelled = false;
    const loadStrategies = async () => {
      setLoadingStrategies(true);
      try {
        const apiStrategies = await fetchStrategiesFromApi();
        if (cancelled) return;
        if (apiStrategies.length > 0) {
          const mapped = apiStrategies.map(mapApiStrategy);
          setStrategies(mapped);
          const defaultStrat = mapped.find(s => s.is_active);
          if (defaultStrat) {
            setActiveId(defaultStrat.id);
          } else if (mapped.length > 0) {
            setActiveId(mapped[0].id);
          }
        }
        // 如果 API 返回空，保留硬编码的备用策略
      } catch {
        // 静默失败，保留默认策略
      } finally {
        if (!cancelled) setLoadingStrategies(false);
      }
    };
    loadStrategies();
    return () => { cancelled = true; };
  }, []);

  const activeStrategy = strategies.find((s) => s.id === activeId) ?? null;

  const togglePanel = (key: string) => {
    setPanels((prev) => ({ ...prev, [key]: !prev[key] }));
  };

  /** 运行回测 - 调用真实API */
  const handleRun = async () => {
    if (!activeStrategy) return;
    setRunning(true);
    setError(null);
    try {
      const data = await runBacktestV5({
        index_code: 'SH000300',
        start_date: '2024-01-01',
        end_date: new Date().toISOString().slice(0, 10),
        initial_capital: 1000000,
        signal_boundaries: activeStrategy.params.signal_boundaries,
        factor_weights: activeStrategy.params.factor_weights,
        sigmoid_params: activeStrategy.params.sigmoid_params,
        position_matrix: activeStrategy.params.position_matrix,
        risk_params: {
          cost_threshold: activeStrategy.params.risk_params.cost_threshold,
          frequency_limit_days: activeStrategy.params.risk_params.frequency_days,
          max_single_adjustment: activeStrategy.params.risk_params.max_adjustment,
        },
      });

      setResult({
        total_return: data.total_return,
        annual_return: data.annual_return,
        max_drawdown: data.max_drawdown,
        win_rate: data.win_rate,
        sharpe: data.sharpe_ratio,
        benchmark_return: data.benchmark_return,
        equity_curve: data.equity_curve,
      });
    } catch (err: any) {
      setError(err?.message || '回测运行失败，请重试');
    } finally {
      setRunning(false);
    }
  };

  /** 保存方案 - 调用真实API */
  const handleSave = async () => {
    if (!activeStrategy) return;
    try {
      await saveBacktestStrategyV5({
        name: activeStrategy.name,
        params_json: activeStrategy.params as any,
      });
    } catch (err: any) {
      alert(err?.message || '保存方案失败');
    }
  };

  /** 删除方案 - 调用真实API */
  const handleDelete = async (id: number) => {
    try {
      await deleteBacktestStrategyV5(id);
      setStrategies((prev) => prev.filter((s) => s.id !== id));
      if (activeId === id) {
        const remaining = strategies.filter((s) => s.id !== id);
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
        <p className="text-xs text-gray-400 mt-0.5">
          方案管理 · 参数调节 · 策略回测
          {loadingStrategies && <span className="ml-2 text-brand-500">加载策略中...</span>}
        </p>
      </div>

      {/* 方案管理栏 */}
      <StrategyBar
        strategies={strategies}
        activeId={activeId}
        onSelect={setActiveId}
        onSave={handleSave}
        onDelete={handleDelete}
        onNew={() => {
          const newId = Math.max(0, ...strategies.map((s) => s.id)) + 1;
          setStrategies((prev) => [...prev, { id: newId, name: `新方案${newId}`, is_active: false, params: { ...DEFAULT_PARAMS } }]);
          setActiveId(newId);
        }}
      />

      {/* 5类折叠参数面板 */}
      <div className="space-y-2">
        <ParamPanel title="信号映射边界" open={panels.signal} onToggle={() => togglePanel('signal')}>
          <div className="flex items-center gap-2 text-xs">
            <span className="text-gray-400">边界值</span>
            {(activeStrategy?.params.signal_boundaries ?? [12, 25, 38, 52, 65, 80]).map((v, i) => (
              <input key={i} type="number" defaultValue={v} className="w-14 px-1.5 py-0.5 border border-gray-200 rounded text-xs" />
            ))}
          </div>
        </ParamPanel>

        <ParamPanel title="因子权重" open={panels.factors} onToggle={() => togglePanel('factors')}>
          <p className="text-[10px] text-gray-400 mb-2">权重总和应=1.0（修改后点击保存方案）</p>
          <div className="space-y-1.5">
            {FACTOR_NAMES.map(name => {
              const w = activeStrategy?.params.factor_weights?.[name] ?? DEFAULT_WEIGHT;
              return (
                <div key={name} className="flex items-center gap-2 text-xs">
                  <span className="w-12 shrink-0 font-mono text-[10px] text-gray-500">{name}</span>
                  <span className="w-14 shrink-0 text-[10px] text-gray-600">{FACTOR_LABELS[name]}</span>
                  <input
                    type="number"
                    step="0.01"
                    min="0"
                    max="1"
                    value={Number(w.toFixed(2))}
                    onChange={e => {
                      if (!activeStrategy) return;
                      const v = parseFloat(e.target.value) || 0;
                      setStrategies(prev => prev.map(s => {
                        if (s.id !== activeId) return s;
                        return {
                          ...s,
                          params: {
                            ...s.params,
                            factor_weights: { ...s.params.factor_weights, [name]: v },
                          },
                        };
                      }));
                    }}
                    className="flex-1 px-1.5 py-0.5 border border-gray-200 rounded text-xs"
                  />
                  <span className="w-10 text-right text-[10px] text-gray-400 tabular-nums">{w.toFixed(2)}</span>
                </div>
              );
            })}
          </div>
          <p className="text-[10px] text-gray-400 mt-2">
            当前总和：
            <span className={`font-mono ${activeStrategy && Math.abs(Object.values(activeStrategy.params.factor_weights ?? {}).reduce((a: number, b: number) => a + b, 0) - 1.0) > 0.01 ? 'text-red-500 font-bold' : 'text-green-500'}`}>
              {activeStrategy ? Object.values(activeStrategy.params.factor_weights ?? {}).reduce((a: number, b: number) => a + b, 0).toFixed(2) : '—.——'}
            </span>
          </p>
        </ParamPanel>

        <ParamPanel title="Sigmoid 参数" open={panels.sigmoid} onToggle={() => togglePanel('sigmoid')}>
          <p className="text-[10px] text-gray-400 mb-2">每因子 (c, k)：c=中点（默认0.50），k=陡峭度（默认3.0）</p>
          <div className="space-y-1.5">
            {FACTOR_NAMES.map(name => {
              const p = activeStrategy?.params.sigmoid_params?.[name] ?? DEFAULT_SIGMOID;
              return (
                <div key={name} className="flex items-center gap-2 text-xs">
                  <span className="w-12 shrink-0 font-mono text-[10px] text-gray-500">{name}</span>
                  <span className="w-14 shrink-0 text-[10px] text-gray-600">{FACTOR_LABELS[name]}</span>
                  <input
                    type="number" step="0.01" min="0.01" max="0.99"
                    value={Number(p.c.toFixed(2))}
                    onChange={e => {
                      if (!activeStrategy) return;
                      const v = parseFloat(e.target.value) || 0.50;
                      setStrategies(prev => prev.map(s => {
                        if (s.id !== activeId) return s;
                        return {
                          ...s,
                          params: {
                            ...s.params,
                            sigmoid_params: { ...s.params.sigmoid_params, [name]: { ...p, c: v } },
                          },
                        };
                      }));
                    }}
                    className="w-14 px-1.5 py-0.5 border border-gray-200 rounded text-xs text-center"
                  />
                  <input
                    type="number" step="0.5" min="0.5" max="20"
                    value={Number(p.k.toFixed(1))}
                    onChange={e => {
                      if (!activeStrategy) return;
                      const v = parseFloat(e.target.value) || 3.0;
                      setStrategies(prev => prev.map(s => {
                        if (s.id !== activeId) return s;
                        return {
                          ...s,
                          params: {
                            ...s.params,
                            sigmoid_params: { ...s.params.sigmoid_params, [name]: { ...p, k: v } },
                          },
                        };
                      }));
                    }}
                    className="w-14 px-1.5 py-0.5 border border-gray-200 rounded text-xs text-center"
                  />
                </div>
              );
            })}
          </div>
        </ParamPanel>

        <ParamPanel title="仓位矩阵" open={panels.position} onToggle={() => togglePanel('position')}>
          <p className="text-[10px] text-gray-400 mb-2">5体制 × 7信号 = 35个仓位值（开发中，暂不可编辑）</p>
          <div className="overflow-x-auto">
            <table className="w-full text-[10px] text-left">
              <thead>
                <tr className="text-gray-400">
                  <th className="px-1 py-0.5">体制＼信号</th>
                  {['S+', 'S', 'A', 'B', 'C', 'D', 'E'].map(s => (
                    <th key={s} className="px-1 py-0.5 text-center">{s}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {['极度恐惧', '恐惧', '中性', '乐观', '极度乐观'].map((reg, ri) => (
                  <tr key={reg} className="border-t border-gray-100">
                    <td className="px-1 py-0.5 text-gray-500">{reg}</td>
                    {(activeStrategy?.params.position_matrix?.[ri] ?? Array(7).fill(0)).map((v: number, ci: number) => (
                      <td key={ci} className="px-1 py-0.5 text-center font-mono">
                        {Number(v.toFixed(2))}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </ParamPanel>

        <ParamPanel title="风控参数" open={panels.risk} onToggle={() => togglePanel('risk')}>
          <div className="grid grid-cols-3 gap-2 text-xs">
            <div><span className="text-gray-400">交易成本阈值</span><input type="number" defaultValue={activeStrategy?.params.risk_params.cost_threshold ?? 0.015} step="0.005" className="mt-0.5 w-full px-1.5 py-0.5 border border-gray-200 rounded text-xs" /></div>
            <div><span className="text-gray-400">频率限制天数</span><input type="number" defaultValue={activeStrategy?.params.risk_params.frequency_days ?? 7} className="mt-0.5 w-full px-1.5 py-0.5 border border-gray-200 rounded text-xs" /></div>
            <div><span className="text-gray-400">单次最大调整</span><input type="number" defaultValue={activeStrategy?.params.risk_params.max_adjustment ?? 0.20} step="0.05" className="mt-0.5 w-full px-1.5 py-0.5 border border-gray-200 rounded text-xs" /></div>
          </div>
        </ParamPanel>
      </div>

      {/* 运行回测按钮 */}
      <button
        onClick={handleRun}
        disabled={running}
        className={`w-full py-2.5 rounded-lg text-sm font-medium text-white transition-colors ${
          running ? 'bg-gray-400 cursor-not-allowed' : 'bg-brand-500 hover:bg-brand-600'
        }`}
      >
        {running ? '回测运行中...' : '▶ 运行回测'}
      </button>

      {/* 错误提示 */}
      {error && (
        <div className="card p-4 text-center">
          <p className="text-red-500 text-sm">{error}</p>
          <button
            onClick={handleRun}
            className="mt-2 px-4 py-1.5 text-xs bg-brand-500 text-white rounded-lg hover:bg-brand-600"
          >
            重试
          </button>
        </div>
      )}

      {/* 回测结果 */}
      <BacktestResultPanel result={result} />
    </div>
  );
}
