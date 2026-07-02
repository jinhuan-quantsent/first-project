/**
 * PositionDetailPanel — 持仓详情展开面板（主编排器）
 * V5.1: 结构化 Gate 数据 + 轨道标签 + 信号切换 + 子组件拆分
 *
 * 子组件拆分（原 1486 行 → ~350 行编排器 + 8 子文件）:
 *   types.ts          — 共享类型 + 常量 + getOverallStatus()
 *   utils.ts          — formatMoney/formatChange
 *   StarRating.tsx    — 星级显示
 *   NavTrendChart.tsx — SVG 走势图
 *   NavHistoryList.tsx— 净值列表
 *   TrendGuardPanel.tsx — 趋势卫士面板（含 Gate1/2/E）
 *   CollapsibleSection.tsx — 可折叠区域
 *   SafetyPadBar.tsx  — 安全垫进度条
 *   AdjustDialog.tsx  — 加仓/减仓对话框
 */
import { useState, useCallback } from 'react';
import SentimentBadge from '../common/SentimentBadge';
import ExpandableReason, { adaptReason } from '../common/ExpandableReason';
import { Shield, TrendingUp, TrendingDown, BarChart3, Activity, FileText, Award, AlertTriangle, Trash2, Loader2 } from 'lucide-react';
import client from '../../api/client';
import { clsx } from 'clsx';
import type { PositionDetailData, PositionDetailPanelProps } from './types';

// Re-export types for backward compatibility (PortfolioV5.tsx imports from here)
export type { PositionDetailData, PositionDetailPanelProps } from './types';
import { STATUS_CONFIG, TRACK_BADGE, getOverallStatus } from './types';
import { formatMoney, formatChange } from './utils';
import StarRating from './StarRating';
import NavTrendChart from './NavTrendChart';
import NavHistoryList from './NavHistoryList';
import TrendGuardPanel from './TrendGuardPanel';
import IntradayPreviewPanel from './intraday/IntradayPreviewPanel';
import CollapsibleSection from './CollapsibleSection';
import SafetyPadBar from './SafetyPadBar';
import AdjustDialog from './AdjustDialog';

export default function PositionDetailPanel({ data, onCollapse, onExecute, onDelete, onIncrease, onDecrease, signalSwitched, trackType }: PositionDetailPanelProps) {
  const daily = formatChange(data.dailyReturn);
  const holding = formatChange(data.holdingReturn);
  const holdingRate = formatChange(data.holdingReturnRate, true);

  // 结构化 Gate 数据提取
  const gates = data.trendGuard?.gates;
  const overallStatus = getOverallStatus(gates);
  const effectiveTrackType = trackType || gates?.sector_track || data.trendGuard?.sector_track;
  const sc = STATUS_CONFIG[overallStatus] || STATUS_CONFIG['normal'];
  const trackBadge = effectiveTrackType ? TRACK_BADGE[effectiveTrackType] : null;

  // D信号特殊处理
  const isDSignalHold = data.signalLevel === 'D' && data.action === 'hold';

  // 仓位金额计算
  const targetAmount = (data.totalAssets ?? data.totalValue ?? 0) * (data.targetPositionPct ?? 0) / 100;
  const needAmount = Math.max(0, targetAmount - (data.marketValue ?? 0));
  const cashAvailable = data.cashAmount ?? 0;
  const actualIncreaseAmount = Math.min(needAmount, cashAvailable);
  const cashInsufficient = cashAvailable < needAmount && needAmount > 0;
  const sellAmount = Math.max(0, (data.marketValue ?? 0) - targetAmount);

  // 执行状态
  const [executeAmount, setExecuteAmount] = useState('');
  const [executing, setExecuting] = useState(false);
  const [backfilling, setBackfilling] = useState(false);
  const [dailyExecCount, setDailyExecCount] = useState(() => {
    const key = `exec_count_${data.fundCode}_${new Date().toISOString().slice(0, 10)}`;
    return parseInt(localStorage.getItem(key) || '0', 10);
  });
  const [confirmDelete, setConfirmDelete] = useState(false);

  // 手动加仓/减仓对话框
  const [adjustDialogOpen, setAdjustDialogOpen] = useState(false);
  const [adjustMode, setAdjustMode] = useState<'increase' | 'decrease'>('increase');

  // 懒加载状态
  const [perfRecords, setPerfRecords] = useState(data.performanceRecords);
  const [perfWinRate, setPerfWinRate] = useState(data.winRate);
  const [perfWinRateDetail, setPerfWinRateDetail] = useState(data.winRateDetail);
  const [perfStats, setPerfStats] = useState<any>(null);
  const [perfLoading, setPerfLoading] = useState(false);
  const [perfLoaded, setPerfLoaded] = useState(data.performanceRecords.length > 0);

  const [tradeRecords, setTradeRecords] = useState(data.tradeRecords);
  const [tradeLoading, setTradeLoading] = useState(false);
  const [tradeLoaded, setTradeLoaded] = useState(data.tradeRecords.length > 0);

  const DAILY_LIMIT = 3;
  const canExecute = dailyExecCount < DAILY_LIMIT;

  const handleExecute = async () => {
    if (!executeAmount || parseFloat(executeAmount) <= 0) return;
    if (!canExecute || !onExecute) return;
    setExecuting(true);
    try {
      await onExecute();
      const key = `exec_count_${data.fundCode}_${new Date().toISOString().slice(0, 10)}`;
      const newCount = dailyExecCount + 1;
      localStorage.setItem(key, String(newCount));
      setDailyExecCount(newCount);
      setExecuteAmount('');
    } finally {
      setExecuting(false);
    }
  };

  const handleBackfill = async () => {
    if (backfilling) return;
    setBackfilling(true);
    try {
      const resp = await client.post('/api/v5/admin/backfill-fund', { fund_code: data.fundCode });
      if (resp.data?.code === 0) {
        alert(resp.data?.data?.message || '数据回填成功');
      } else {
        alert(resp.data?.message || '回填失败');
      }
    } catch (err: any) {
      alert(err?.response?.data?.detail || err?.response?.data?.message || '回填请求失败');
    } finally {
      setBackfilling(false);
    }
  };

  const handleDelete = () => {
    if (!confirmDelete) {
      setConfirmDelete(true);
      setTimeout(() => setConfirmDelete(false), 3000);
      return;
    }
    if (onDelete) onDelete();
  };

  const loadPerformance = useCallback(async () => {
    if (perfLoaded || perfLoading) return;
    setPerfLoading(true);
    try {
      const resp = await client.get('/api/v5/portfolio/advice-history', { params: { fund_code: data.fundCode } });
      const d = resp.data?.data;
      if (d) {
        setPerfWinRate(d.stats?.win_rate ?? 0);
        setPerfWinRateDetail(d.stats?.verified_count ? `${d.stats.verified_count}条已验证` : '');
        setPerfStats(d.stats ?? null);
        setPerfRecords((d.items || []).slice(0, 10).map((a: any) => ({
          date: a.date?.slice(0, 10) || '',
          signal: a.signal_level || '',
          operation: a.advice_type === 'buy' ? '买入' : a.advice_type === 'reduce' ? '减仓' : a.advice_type === 'hold' ? '持有' : '观望',
          position: a.suggested_position != null ? `${a.suggested_position.toFixed(1)}%` : '-',
          isExecuted: !!a.is_executed,
          correctUp: a.is_verified && a.actual_result > 0,
          correctDown: a.is_verified && a.actual_result < 0,
          returnPct: a.actual_result || 0,
          reason: a.advice_content || '',
        })));
      }
      setPerfLoaded(true);
    } catch {} finally {
      setPerfLoading(false);
    }
  }, [data.fundCode, perfLoaded, perfLoading]);

  const loadTradeRecords = useCallback(async () => {
    if (tradeLoaded || tradeLoading) return;
    setTradeLoading(true);
    try {
      const resp = await client.get('/api/v5/portfolio/trade-records', { params: { fund_code: data.fundCode } });
      const d = resp.data?.data;
      if (d) {
        setTradeRecords((d.items || []).slice(0, 10).map((t: any) => ({
          date: t.date || '',
          type: t.type || '调仓',
          amount: t.amount || 0,
          nav: t.nav || 0,
          fee: t.fee || 0,
        })));
      }
      setTradeLoaded(true);
    } catch {} finally {
      setTradeLoading(false);
    }
  }, [data.fundCode, tradeLoaded, tradeLoading]);

  return (
    <div className="bg-white border-t border-gray-100 animate-fadeIn">
      {/* ====== 子区1: 展开标题行 ====== */}
      <div className="flex items-center gap-3 px-4 py-3 border-b border-gray-50">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2">
            <span className="text-sm font-bold text-gray-800 truncate">{data.fundName}</span>
            {trackBadge && (
              <span className={clsx('text-[10px] px-1.5 py-0.5 rounded font-medium', trackBadge.bg, trackBadge.color)}>
                {trackBadge.label}
              </span>
            )}
            {signalSwitched && (
              <span className="text-[10px] text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded">
                信号当日切换
              </span>
            )}
          </div>
          <span className="text-[10px] text-gray-400 font-mono">{data.fundCode}</span>
        </div>

        {/* overall_status 风控状态大标签 */}
        <div className={clsx('shrink-0 px-2.5 py-1 rounded-lg border text-xs font-bold', sc.bg, sc.color, sc.border)}>
          {sc.icon} {sc.label}
        </div>

        {/* 市值+编辑+删除 */}
        <div className="text-right shrink-0 mr-2 flex items-center gap-1">
          <p className="text-sm font-bold text-gray-800 font-mono">{formatMoney(data.marketValue)}</p>
          <button className="text-gray-300 hover:text-[var(--brand-cyan)] transition-colors text-xs ml-1" title="编辑">
            ✎
          </button>
          {onDelete && (
            <button
              onClick={handleDelete}
              className={clsx(
                'transition-colors text-xs ml-1 p-0.5 rounded',
                confirmDelete
                  ? 'bg-red-100 text-red-600 px-2 py-1 text-[10px] font-medium'
                  : 'text-gray-300 hover:text-red-500 hover:bg-red-50'
              )}
              title={confirmDelete ? '再次点击确认删除' : '删除持仓'}
            >
              {confirmDelete ? '确认删除?' : <Trash2 className="w-3.5 h-3.5" />}
            </button>
          )}
        </div>

        {/* 昨收/持有 */}
        <div className="text-right shrink-0 space-y-0.5">
          <p className={`text-xs font-mono ${daily.className}`}>
            昨收 {daily.text}
          </p>
          <p className={`text-xs font-mono ${holding.className}`}>
            持有 {holding.text}
            <span className={`ml-1 ${holdingRate.className}`}>({holdingRate.text})</span>
          </p>
        </div>

        {/* 信号+原因+收起 */}
        <div className="flex items-center gap-2 shrink-0 ml-2">
          <SentimentBadge level={data.signalLevel} size="sm" variant="inline" />
          <div className="max-w-[200px]">
            <ExpandableReason
              reason={adaptReason(data.signalReason, data.signalLevel)}
              signalLevel={data.signalLevel}
              actionAdvice={data.action === 'increase' ? 'buy' : data.action === 'decrease' ? 'sell' : 'hold'}
              variant="compact"
              summaryMaxLength={20}
            />
          </div>
          <button onClick={onCollapse} className="p-1 rounded hover:bg-gray-100 transition-colors">
            <svg className="w-4 h-4 text-gray-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="18 15 12 9 6 15" />
            </svg>
          </button>
        </div>
      </div>

      <div className="px-4 py-3 space-y-4">
        {/* ====== 子区2: 核心决策卡 ====== */}
        <div className={clsx('rounded-lg p-3 space-y-2 border', sc.bg.replace('50', '50/30'), sc.border.replace('200', '100/50'))}>
          <div className="flex items-center gap-3 flex-wrap">
            <span className="text-xs text-gray-500">
              {data.complianceDirection === 'new' ? '▲ 新仓' : '↓ 最近清仓'}
            </span>
            {data.complianceStars > 0 ? (
              <StarRating value={data.complianceStars} max={4} />
            ) : (
              <span className="text-[10px] text-gray-400">置信度暂无数据</span>
            )}
            <span className={clsx(
              'text-xs px-2 py-0.5 rounded font-medium',
              data.action === 'increase' ? 'bg-red-50 text-red-600' :
              data.action === 'decrease' ? 'bg-green-50 text-green-600' :
              isDSignalHold ? 'bg-gray-100 text-gray-500' :
              'bg-gray-100 text-gray-600'
            )}>
              {data.action === 'increase' ? '加仓' : data.action === 'decrease' ? '减仓' : isDSignalHold ? '观望（动量延续）' : '持有'}
            </span>
            {trackBadge && (
              <span className={clsx('text-[10px] px-1.5 py-0.5 rounded font-medium', trackBadge.bg, trackBadge.color)}>
                {trackBadge.label}轨道
              </span>
            )}
          </div>
          <p className="text-xs text-gray-600 leading-relaxed">{data.recommendationReason}</p>
          {isDSignalHold && (
            <p className="text-[10px] text-amber-600 bg-amber-50/50 rounded px-2 py-1">
              D信号=贪婪动量延续，当前按观望处理，暂不触发减仓
            </p>
          )}
          {data.updateNote && (
            <p className="text-[10px] text-gray-400">{data.updateNote}</p>
          )}
        </div>

        {/* ====== 子区2.5: 操作建议执行 ====== */}
        {onExecute && (
          <div className="bg-gradient-to-r from-cyan-50 to-teal-50 rounded-lg p-3 space-y-2 border border-cyan-100/50">
            <div className="flex items-center gap-2">
              <Shield className="w-3.5 h-3.5 text-[var(--brand-cyan)]" />
              <span className="text-xs font-medium text-gray-700">操作建议执行</span>
              {data.targetPositionPct !== undefined && data.targetPositionPct !== null && (
                <span className="text-[10px] text-gray-400 ml-auto">
                  目标仓位: {data.targetPositionPct}%{(data.totalAssets ?? data.totalValue) ? `(${formatMoney(targetAmount)})` : ""}
                  {data.denominatorType === 'total_assets' && <span className="ml-1 px-1 py-0.5 bg-blue-50 text-blue-500 rounded text-[9px]">基准:总资产</span>}
                  {data.suggestedBuyAmount > 0 && <span className="ml-1 text-[9px] text-red-400">建议买入{formatMoney(data.suggestedBuyAmount)}</span>}
                  {data.suggestedSellAmount > 0 && <span className="ml-1 text-[9px] text-green-500">建议卖出{formatMoney(data.suggestedSellAmount)}</span>}
                </span>
              )}
            </div>

            {/* P3: 安全垫可视化进度条 */}
            {data.targetPositionPct !== undefined && data.targetPositionPct !== null && (
              <SafetyPadBar data={data} />
            )}

            {/* V5.1: 现金不足警告 */}
            {data.cashWarning && (
              <div className="text-xs text-amber-600 bg-amber-50 rounded p-1.5 flex items-center gap-1">
                <span className="font-medium">现金不足</span>
                <span>{data.cashWarning}</span>
              </div>
            )}
            {/* V5.1: 组合约束说明 */}
            {data.portfolioConstraints && data.portfolioConstraints.length > 0 && (
              <div className="text-xs text-orange-600 bg-orange-50 rounded p-1.5">
                <span className="font-medium">组合约束: </span>
                {data.portfolioConstraints.join("; ")}
              </div>
            )}
            {/* 建议理由 */}
            {data.reason && (
              <div className="flex items-start gap-2 bg-white/60 rounded-md p-2">
                <span className="text-[10px] text-gray-400 shrink-0 mt-0.5">建议理由</span>
                <span className="text-xs text-gray-700 font-medium leading-relaxed">{data.reason}</span>
              </div>
            )}

            {/* 数据异常兜底 */}
            {(!data.action || data.action === null) && (
              <div className="flex items-center gap-1.5 bg-amber-50 rounded-md p-1.5">
                <AlertTriangle className="w-3 h-3 text-amber-500 shrink-0" />
                <span className="text-[10px] text-amber-700">数据异常，仅供参考</span>
              </div>
            )}

            {/* 操作区域 */}
            {data.action === 'hold' ? (
              <div className="flex items-center justify-center py-1.5">
                <span className="text-xs text-gray-500">持有不动</span>
              </div>
            ) : data.action === 'increase' ? (
              <div className="space-y-2">
                {needAmount > 0 && (
                  <div className="flex items-center gap-2 bg-white/60 rounded-md p-1.5">
                    <span className="text-[10px] text-gray-400 shrink-0">
                      {cashInsufficient ? '现金不足，最多可加仓' : '建议加仓'}
                    </span>
                    <span className={clsx('text-xs font-bold font-mono', cashInsufficient ? 'text-amber-600' : 'text-red-500')}>
                      {formatMoney(actualIncreaseAmount)}
                    </span>
                    {cashInsufficient && (
                      <span className="text-[10px] text-gray-400">（目标需{formatMoney(needAmount)}）</span>
                    )}
                  </div>
                )}
                <div className="flex items-center gap-2">
                  <span className="text-xs text-gray-500 shrink-0">买入金额</span>
                  <div className="flex-1 flex items-center gap-1">
                    <span className="text-xs text-gray-400">¥</span>
                    <input
                      type="text"
                      value={executeAmount}
                      onChange={(e) => setExecuteAmount(e.target.value.replace(/[^\d.]/g, ''))}
                      placeholder="输入金额"
                      disabled={!canExecute}
                      className="flex-1 text-sm font-mono border border-red-200 rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-red-400 disabled:bg-gray-100 disabled:text-gray-400"
                    />
                  </div>
                  <button
                    onClick={handleExecute}
                    disabled={!canExecute || !executeAmount || parseFloat(executeAmount) <= 0 || executing}
                    className={clsx(
                      'flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium transition-all',
                      canExecute && executeAmount && parseFloat(executeAmount) > 0 && !executing
                        ? 'bg-red-500 text-white hover:bg-red-600 shadow-sm'
                        : 'bg-gray-100 text-gray-400 cursor-not-allowed'
                    )}
                  >
                    <svg className="w-3 h-3" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21" /></svg>
                    {executing ? '执行中...' : '执行'}
                  </button>
                </div>
              </div>
            ) : data.action === 'decrease' ? (
              <div className="space-y-2">
                {sellAmount > 0 && (
                  <div className="flex items-center gap-2 bg-white/60 rounded-md p-1.5">
                    <span className="text-[10px] text-gray-400 shrink-0">建议卖出</span>
                    <span className="text-xs font-bold text-green-500 font-mono">{formatMoney(sellAmount)}</span>
                  </div>
                )}
                <div className="flex items-center gap-2">
                  <span className="text-xs text-gray-500 shrink-0">卖出金额</span>
                  <div className="flex-1 flex items-center gap-1">
                    <span className="text-xs text-gray-400">¥</span>
                    <input
                      type="text"
                      value={executeAmount}
                      onChange={(e) => setExecuteAmount(e.target.value.replace(/[^\d.]/g, ''))}
                      placeholder="输入金额"
                      disabled={!canExecute}
                      className="flex-1 text-sm font-mono border border-green-200 rounded px-2 py-1 focus:outline-none focus:ring-1 focus:ring-green-400 disabled:bg-gray-100 disabled:text-gray-400"
                    />
                  </div>
                  <button
                    onClick={handleExecute}
                    disabled={!canExecute || !executeAmount || parseFloat(executeAmount) <= 0 || executing}
                    className={clsx(
                      'flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium transition-all',
                      canExecute && executeAmount && parseFloat(executeAmount) > 0 && !executing
                        ? 'bg-green-500 text-white hover:bg-green-600 shadow-sm'
                        : 'bg-gray-100 text-gray-400 cursor-not-allowed'
                    )}
                  >
                    <svg className="w-3 h-3" viewBox="0 0 24 24" fill="currentColor"><polygon points="5 3 19 12 5 21" /></svg>
                    {executing ? '执行中...' : '执行'}
                  </button>
                </div>
              </div>
            ) : (
              <div className="flex items-center justify-center py-1.5">
                <span className="text-xs text-gray-500">数据异常，默认建议持有，仅供参考</span>
              </div>
            )}

            {!canExecute && (
              <p className="text-[10px] text-red-400">今日执行次数已达上限，请明日再试</p>
            )}
          </div>
        )}

        {/* ====== 手动加仓/减仓按钮 ====== */}
        {(onIncrease || onDecrease) && (
          <div className="flex items-center gap-2">
            {onIncrease && (
              <button
                onClick={() => { setAdjustMode('increase'); setAdjustDialogOpen(true); }}
                className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium bg-red-50 text-red-600 hover:bg-red-100 border border-red-200 transition-all"
              >
                <TrendingUp className="w-3 h-3" />
                加仓
              </button>
            )}
            {onDecrease && (
              <button
                onClick={() => { setAdjustMode('decrease'); setAdjustDialogOpen(true); }}
                className="flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-medium bg-green-50 text-green-600 hover:bg-green-100 border border-green-200 transition-all"
              >
                <TrendingDown className="w-3 h-3" />
                减仓
              </button>
            )}
            <span className="text-[10px] text-gray-400 ml-auto">
              可用现金 {formatMoney(data.cashAmount ?? 0)}
            </span>
          </div>
        )}

        {/* 手动加仓/减仓对话框 */}
        <AdjustDialog
          open={adjustDialogOpen}
          mode={adjustMode}
          data={data}
          onConfirm={async (amt, date) => {
            const callback = adjustMode === 'increase' ? onIncrease : onDecrease;
            if (callback) await callback(amt, date);
          }}
          onCancel={() => setAdjustDialogOpen(false)}
        />

        {/* ====== 盘中预演（交易时段内显示） ====== */}
        <IntradayPreviewPanel fundCode={data.fundCode} />

        {/* ====== 趋势卫士解读 ====== */}
        {data.trendGuard ? (
          <TrendGuardPanel tg={data.trendGuard} />
        ) : (
          (data.trendGuardText || data.trendText || data.marketStatus) && (
            <div className="bg-gradient-to-r from-blue-50 to-indigo-50 rounded-lg p-3 space-y-1.5 border border-blue-100/50">
              {data.marketStatus && (
                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-gray-400 shrink-0">市场现状</span>
                  <span className="text-xs text-gray-600 font-medium">{data.marketStatus}</span>
                </div>
              )}
              {(data.trendGuardText || data.trendText) && (
                <div className="flex items-center gap-2">
                  <span className="text-[10px] text-gray-400 shrink-0">趋势解读</span>
                  <span className="text-xs text-blue-600 font-medium">{data.trendGuardText || data.trendText}</span>
                </div>
              )}
            </div>
          )
        )}

        {/* ====== 基金净值列表 ====== */}
        <div>
          <div className="flex items-center gap-2 mb-2">
            <BarChart3 className="w-3.5 h-3.5 text-gray-400" />
            <span className="text-xs font-medium text-gray-600">基金净值</span>
            <span className="text-[10px] text-gray-400 ml-auto">近15日</span>
          </div>
          <NavHistoryList data={data.navHistory} />
        </div>

        {/* 数据回填按钮 */}
        <div className="flex items-center justify-end">
          <button
            onClick={handleBackfill}
            disabled={backfilling}
            className={clsx(
              'flex items-center gap-1 px-2.5 py-1 rounded-lg text-[10px] font-medium transition-all',
              backfilling
                ? 'bg-gray-100 text-gray-400 cursor-not-allowed'
                : 'bg-gray-50 text-gray-500 hover:bg-gray-100 hover:text-gray-700 border border-gray-200'
            )}
          >
            <svg className={clsx('w-3 h-3', backfilling && 'animate-spin')} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <polyline points="1 4 1 10 7 10" /><path d="M3.51 15a9 9 0 1 0 2.13-9.36L1 10" />
            </svg>
            {backfilling ? '回填中...' : '数据回填'}
          </button>
        </div>

        {/* ====== 绩效记录 ====== */}
        <CollapsibleSection
          title="绩效记录"
          icon={Activity}
          badge={`${perfWinRate}% 胜率${perfWinRateDetail ? ` (${perfWinRateDetail})` : ''}`}
          onToggle={loadPerformance}
        >
          {perfLoading ? (
            <div className="flex items-center justify-center py-3">
              <Loader2 className="w-4 h-4 text-gray-300 animate-spin" />
              <span className="text-[10px] text-gray-400 ml-1">加载中...</span>
            </div>
          ) : perfRecords.length === 0 ? (
            <p className="text-[10px] text-gray-300 text-center py-2">暂无绩效记录</p>
          ) : (
            <div className="space-y-2">
              {perfStats && (
                <div className="bg-gray-50 rounded-lg p-2 grid grid-cols-4 gap-2 text-center">
                  <div><p className="text-[9px] text-gray-400">总建议</p><p className="text-sm font-bold text-gray-700">{perfStats.total_advice ?? 0}</p></div>
                  <div><p className="text-[9px] text-gray-400">已执行</p><p className="text-sm font-bold text-blue-500">{perfStats.executed ?? 0}</p></div>
                  <div><p className="text-[9px] text-gray-400">买入胜率</p><p className="text-sm font-bold text-red-500">{perfStats.buy_verified ? `${perfStats.buy_win_rate}%` : '—'}<span className="text-[9px] text-gray-400 ml-0.5">{perfStats.buy_verified ? `${perfStats.buy_correct}/${perfStats.buy_verified}` : `(${perfStats.buy_count}次)`}</span></p></div>
                  <div><p className="text-[9px] text-gray-400">减仓胜率</p><p className="text-sm font-bold text-green-500">{perfStats.reduce_verified ? `${perfStats.reduce_win_rate}%` : '—'}<span className="text-[9px] text-gray-400 ml-0.5">{perfStats.reduce_verified ? `${perfStats.reduce_correct}/${perfStats.reduce_verified}` : `(${perfStats.reduce_count}次)`}</span></p></div>
                </div>
              )}
              <div className="overflow-x-auto">
                <table className="w-full text-[10px]">
                  <thead><tr className="text-gray-400 border-b border-gray-100"><th className="py-1 text-left font-medium">日期</th><th className="py-1 text-left font-medium">操作</th><th className="py-1 text-left font-medium">仓位</th><th className="py-1 text-center font-medium">✓执</th><th className="py-1 text-center font-medium">✓验</th><th className="py-1 text-right font-medium">收益率</th><th className="py-1 text-left font-medium pl-2">原因</th></tr></thead>
                  <tbody>
                    {perfRecords.slice(0, 10).map((rec, i) => {
                      const ret = formatChange(rec.returnPct, true);
                      return (
                        <tr key={i} className="border-b border-gray-50">
                          <td className="py-1 text-gray-500 font-mono whitespace-nowrap">{rec.date}</td>
                          <td className="py-1"><span className={`px-1.5 py-0.5 rounded text-[9px] font-medium ${rec.operation === '买入' ? 'bg-red-100 text-red-600' : rec.operation === '减仓' ? 'bg-green-100 text-green-600' : rec.operation === '持有' ? 'bg-blue-100 text-blue-600' : 'bg-gray-100 text-gray-500'}`}>{rec.operation}</span></td>
                          <td className="py-1 text-gray-500 font-mono">{rec.position || '-'}</td>
                          <td className="py-1 text-center">{rec.isExecuted ? '✓' : '☐'}</td>
                          <td className="py-1 text-center">{(rec.correctUp || rec.correctDown) ? '✓' : '☐'}</td>
                          <td className={`py-1 text-right font-mono ${ret.className}`}>{ret.text}</td>
                          <td className="py-1 text-gray-400 pl-2 truncate max-w-[160px]" title={rec.reason}>{rec.reason}</td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>
          )}
        </CollapsibleSection>

        {/* ====== 交易记录 ====== */}
        <CollapsibleSection title="交易记录" icon={FileText} onToggle={loadTradeRecords}>
          {tradeLoading ? (
            <div className="flex items-center justify-center py-3"><Loader2 className="w-4 h-4 text-gray-300 animate-spin" /><span className="text-[10px] text-gray-400 ml-1">加载中...</span></div>
          ) : tradeRecords.length === 0 ? (
            <p className="text-[10px] text-gray-300 text-center py-2">暂无交易记录</p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-[10px]">
                <thead><tr className="text-gray-400 border-b border-gray-100"><th className="py-1 text-left font-medium">日期</th><th className="py-1 text-left font-medium">类型</th><th className="py-1 text-right font-medium">金额</th><th className="py-1 text-right font-medium">净值</th><th className="py-1 text-right font-medium">费用</th></tr></thead>
                <tbody>
                  {tradeRecords.map((rec, i) => (
                    <tr key={i} className="border-b border-gray-50">
                      <td className="py-1 text-gray-500 font-mono">{rec.date}</td>
                      <td className={`py-1 font-medium ${rec.type === '买入' ? 'text-red-500' : rec.type === '卖出' ? 'text-green-500' : 'text-gray-500'}`}>{rec.type}</td>
                      <td className="py-1 text-right text-gray-600 font-mono">¥{rec.amount.toLocaleString()}</td>
                      <td className="py-1 text-right text-gray-500 font-mono">{rec.nav > 0 ? rec.nav.toFixed(4) : '-'}</td>
                      <td className="py-1 text-right text-gray-400 font-mono">{rec.fee > 0 ? rec.fee.toLocaleString() : '-'}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CollapsibleSection>

        {/* ====== 走势图 ====== */}
        <CollapsibleSection title="近期走势图" icon={TrendingUp} badge="近3月">
          <div className="bg-gray-50 rounded-lg p-2"><NavTrendChart data={data.navHistory} /></div>
        </CollapsibleSection>

        {/* ====== 重仓股 ====== */}
        <CollapsibleSection title={`前${Math.max(data.topHoldings.length, 1)}大重仓股`} icon={BarChart3}>
          {data.topHoldings.length === 0 ? (
            <p className="text-[10px] text-gray-300 text-center py-2">暂无重仓股数据</p>
          ) : (
            <div className="grid grid-cols-2 gap-x-4 gap-y-2">
              {data.topHoldings.map((stock, i) => (
                <div key={i} className="flex items-start justify-between">
                  <div className="min-w-0">
                    <p className="text-xs font-medium text-gray-700 truncate">{stock.name}</p>
                    <p className="text-[10px] text-gray-400 truncate">{stock.description}</p>
                  </div>
                  <span className="text-[10px] text-gray-500 font-mono shrink-0 ml-2">{stock.pct.toFixed(2)}%</span>
                </div>
              ))}
            </div>
          )}
        </CollapsibleSection>

        {/* ====== 基础评级 ====== */}
        <CollapsibleSection title="基础评级" icon={Award}>
          {data.morningStarRating > 0 || data.ratingDetails.length > 0 ? (
            <div className="bg-gray-50 rounded-lg p-3 space-y-1.5">
              {data.morningStarRating > 0 && (
                <div className="flex items-center gap-2">
                  <span className="text-xs text-gray-500">晨星评级</span>
                  <StarRating value={data.morningStarRating} />
                </div>
              )}
              {data.ratingDetails.map((detail, i) => (
                <p key={i} className="text-[10px] text-gray-400">{detail}</p>
              ))}
            </div>
          ) : (
            <p className="text-[10px] text-gray-300 text-center py-2">基础评级暂无数据</p>
          )}
        </CollapsibleSection>

        {/* ====== 今日评估 ====== */}
        <CollapsibleSection title="今日评估" icon={Shield}>
          <p className="text-xs text-gray-500 leading-relaxed mb-3">{data.todayEvaluation}</p>
          <div className="grid grid-cols-3 gap-3">
            {([
              { period: '短期', judgment: data.shortTerm.label, reason: data.shortTerm.reason },
              { period: '中期', judgment: data.midTerm.label, reason: data.midTerm.reason },
              { period: '长期', judgment: data.longTerm.label, reason: data.longTerm.reason },
            ]).map((term) => (
              <div key={term.period} className="bg-gray-50 rounded-lg p-3 text-center">
                <p className="text-[10px] text-gray-400 mb-1">{term.period}</p>
                <p className={`text-sm font-bold ${term.judgment === '看多' ? 'text-red-500' : term.judgment === '看空' ? 'text-green-500' : 'text-gray-600'}`}>{term.judgment}</p>
                <p className="text-[10px] text-gray-400 mt-0.5 truncate">{term.reason}</p>
              </div>
            ))}
          </div>
        </CollapsibleSection>
      </div>
    </div>
  );
}
