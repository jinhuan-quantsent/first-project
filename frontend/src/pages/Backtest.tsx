/**
 * Backtest - V5.0 策略回测页（Tab 式三栏布局）
 * 1) 参数配置 — 方案管理 + 5类参数 + 运行按钮
 * 2) 回测结果 — 指标卡 + 权益曲线 + 逐日追踪（懒加载）
 * 3) 信号分析 — 信号绩效 + 板块热力图（懒加载）
 */
import { useEffect, useState, lazy, Suspense } from 'react';
import { useBacktestStore } from '../stores/backtest';
import { DEFAULT_MODEL_PARAMS } from '../utils/paramsMapper';

// 首屏必需组件 — 同步加载
import { StrategyBar } from '../components/backtest/StrategyBar';
import { ParamPanel } from '../components/backtest/ParamPanel';
import { SignalMappingPanel } from '../components/backtest/SignalMappingPanel';
import { FactorWeightsPanel } from '../components/backtest/FactorWeightsPanel';
import { ActionMappingPanel } from '../components/backtest/ActionMappingPanel';
import { FactorEnginePanel } from '../components/backtest/FactorEnginePanel';
import { PositionRiskPanel } from '../components/backtest/PositionRiskPanel';
import { FundBacktestSection } from '../components/backtest/FundBacktestSection';

// ECharts 组件 — 懒加载，首屏不加载 644KB 的 echarts
const BacktestResultPanel = lazy(() =>
  import('../components/backtest/BacktestResultPanel').then(m => ({ default: m.BacktestResultPanel }))
);
const DailyTrackingResultPanel = lazy(() =>
  import('../components/backtest/DailyTrackingResultPanel').then(m => ({ default: m.DailyTrackingResultPanel }))
);
const SignalAnalysisPanel = lazy(() =>
  import('../components/backtest/SignalAnalysisPanel').then(m => ({ default: m.SignalAnalysisPanel }))
);

/** 懒加载 Loading 占位 */
function LazyPlaceholder({ text = '加载中...' }: { text?: string }) {
  return (
    <div className="card p-8 text-center">
      <div className="inline-block w-5 h-5 border-2 border-brand-500 border-t-transparent rounded-full animate-spin mb-2" />
      <p className="text-gray-400 text-xs">{text}</p>
    </div>
  );
}

type TabKey = 'params' | 'result' | 'signal';

const TABS: { key: TabKey; label: string; desc: string }[] = [
  { key: 'params', label: '参数配置', desc: '方案管理 · 5类参数' },
  { key: 'result', label: '回测结果', desc: '指标 · 曲线 · 追踪' },
  { key: 'signal', label: '信号分析', desc: '绩效 · 热力图' },
];

export default function Backtest() {
  const {
    strategies, activeId, systemActiveSchemeName,
    panels, running, result, error,
    selectedFund, backtestParams,
    setActiveId, updateParams, addStrategy,
    handleSave, handleDelete, handleApply, renameStrategy,
    loadSavedStrategies, handleRunBacktest,
    togglePanel, setSelectedFund, setBacktestParams,
  } = useBacktestStore();

  const [activeTab, setActiveTab] = useState<TabKey>('params');

  // 加载已保存的方案列表
  useEffect(() => {
    loadSavedStrategies();
  }, [loadSavedStrategies]);

  // 运行完回测自动切到结果 Tab
  useEffect(() => {
    if (result) setActiveTab('result');
  }, [result]);

  const activeStrategy = strategies.find(s => s.id === activeId) ?? null;
  const activeParams = activeStrategy?.params ?? DEFAULT_MODEL_PARAMS;

  return (
    <div className="max-w-5xl mx-auto space-y-3 md:space-y-4 px-1">
      <div>
        <h1 className="text-xl font-bold text-gray-800">策略回测 V5.0</h1>
        <p className="text-xs text-gray-400 mt-0.5">方案管理 · 5类参数 · 策略回测 · 信号分析</p>
      </div>

      {/* Tab 导航 */}
      <div className="flex gap-1 bg-gray-100 rounded-lg p-1">
        {TABS.map(tab => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`flex-1 py-2 px-3 rounded-md text-xs font-medium transition-colors ${
              activeTab === tab.key
                ? 'bg-white text-brand-600 shadow-sm'
                : 'text-gray-500 hover:text-gray-700'
            }`}
          >
            {tab.label}
            <span className="hidden md:inline text-[10px] text-gray-400 ml-1">{tab.desc}</span>
          </button>
        ))}
      </div>

      {/* Tab 内容 */}
      {activeTab === 'params' && (
        <div className="space-y-4">
          {/* 方案管理栏 */}
          <StrategyBar
            strategies={strategies}
            activeId={activeId}
            onSelect={setActiveId}
            onSave={handleSave}
            onDelete={handleDelete}
            onNew={addStrategy}
            onApply={handleApply}
            onRename={renameStrategy}
            systemActiveSchemeName={systemActiveSchemeName}
          />

          {/* 5类折叠参数面板 */}
          <div className="space-y-2">
            <ParamPanel title="信号映射边界" open={panels.signal} onToggle={() => togglePanel('signal')} badge="6滑块">
              <SignalMappingPanel params={activeParams} onChange={updateParams} />
            </ParamPanel>
            <ParamPanel title="因子权重" open={panels.factors} onToggle={() => togglePanel('factors')} badge="11因子">
              <FactorWeightsPanel params={activeParams} onChange={updateParams} />
            </ParamPanel>
            <ParamPanel title="行动映射" open={panels.action} onToggle={() => togglePanel('action')} badge="7信号→行动">
              <ActionMappingPanel params={activeParams} onChange={updateParams} />
            </ParamPanel>
            <ParamPanel title="因子引擎" open={panels.engine} onToggle={() => togglePanel('engine')} badge="4参数">
              <FactorEnginePanel params={activeParams} onChange={updateParams} />
            </ParamPanel>
            <ParamPanel title="仓位风控" open={panels.risk} onToggle={() => togglePanel('risk')} badge="13参数">
              <PositionRiskPanel params={activeParams} onChange={updateParams} />
            </ParamPanel>
          </div>

          {/* 单基金回测参数区 */}
          <FundBacktestSection
            strategies={strategies}
            activeStrategyId={activeId}
            selectedFund={selectedFund}
            onFundSelect={setSelectedFund}
            backtestParams={backtestParams}
            onParamsChange={setBacktestParams}
          />

          {/* 运行回测按钮 */}
          <button
            onClick={handleRunBacktest}
            disabled={running}
            className={`w-full py-2.5 rounded-lg text-sm font-medium text-white transition-colors flex items-center justify-center gap-2 ${
              running ? 'bg-gray-400 cursor-not-allowed' : 'bg-brand-500 hover:bg-brand-600'
            }`}
          >
            {running ? '回测运行中...' : `▶ 运行回测${selectedFund ? `（${selectedFund.name}）` : '（沪深300）'}`}
          </button>

          {/* 错误提示 */}
          {error && (
            <div className="card p-4 text-center">
              <p className="text-red-500 text-sm">{error}</p>
              <button onClick={handleRunBacktest} className="mt-2 px-4 py-1.5 text-xs bg-brand-500 text-white rounded-lg hover:bg-brand-600">重试</button>
            </div>
          )}
        </div>
      )}

      {activeTab === 'result' && (
        <Suspense fallback={<LazyPlaceholder text="加载回测结果组件..." />}>
          <div className="space-y-4">
            {/* 快捷入口：没有结果时引导运行 */}
            {!result && !error && (
              <div className="card p-6 text-center space-y-2">
                <p className="text-gray-500 text-sm">还没有回测结果</p>
                <button
                  onClick={() => setActiveTab('params')}
                  className="px-4 py-2 text-xs bg-brand-500 text-white rounded-lg hover:bg-brand-600"
                >
                  前往参数配置运行回测
                </button>
              </div>
            )}

            {/* 回测结果 — 逐日追踪模式 vs 普通模式 */}
            {result?.daily_tracking && result.daily_tracking.length > 0 ? (
              <DailyTrackingResultPanel result={result} strategyName={activeStrategy?.name} />
            ) : (
              <BacktestResultPanel result={result} />
            )}

            {/* 错误提示 */}
            {error && (
              <div className="card p-4 text-center">
                <p className="text-red-500 text-sm">{error}</p>
                <button onClick={() => setActiveTab('params')} className="mt-2 px-4 py-1.5 text-xs bg-brand-500 text-white rounded-lg hover:bg-brand-600">调整参数重试</button>
              </div>
            )}
          </div>
        </Suspense>
      )}

      {activeTab === 'signal' && (
        <Suspense fallback={<LazyPlaceholder text="加载信号分析组件..." />}>
          <SignalAnalysisPanel />
        </Suspense>
      )}
    </div>
  );
}
