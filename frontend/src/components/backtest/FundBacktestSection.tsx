import { useState, useEffect, useCallback, useRef } from 'react';
import { Search } from 'lucide-react';
import type { BacktestStrategy } from '../../stores/backtest';
import client from '../../api/client';

interface FundSuggestion {
  code: string;
  name: string;
  type?: string;
  nav?: number;
}

/** 单基金回测参数区（智能输入框） */
export function FundBacktestSection({ strategies, activeStrategyId, selectedFund, onFundSelect, backtestParams, onParamsChange }: {
  strategies: BacktestStrategy[];
  activeStrategyId: number | null;
  selectedFund: FundSuggestion | null;
  onFundSelect: (fund: FundSuggestion | null) => void;
  backtestParams: {
    startDate: string;
    endDate: string;
    initialCapital: number;
    strategyId: number | null;
  };
  onParamsChange: (params: {
    startDate: string;
    endDate: string;
    initialCapital: number;
    strategyId: number | null;
  }) => void;
}) {
  const [fundInput, setFundInput] = useState('');
  const [suggestions, setSuggestions] = useState<FundSuggestion[]>([]);
  const [showSuggestions, setShowSuggestions] = useState(false);
  const [highlightIdx, setHighlightIdx] = useState(-1);
  const debounceTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const wrapperRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (activeStrategyId && !backtestParams.strategyId) {
      onParamsChange({ ...backtestParams, strategyId: activeStrategyId });
    }
  }, [activeStrategyId]);

  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setShowSuggestions(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const searchFunds = useCallback(async (keyword: string) => {
    if (!keyword || keyword.length < 1) {
      setSuggestions([]);
      setShowSuggestions(false);
      return;
    }
    try {
      const res = await client.get('/api/v5/fund/search', {
        params: { keyword, page_size: 8 },
      });
      const items = res.data?.data?.items || [];
      const mapped: FundSuggestion[] = items.map((f: any) => ({
        code: f.fund_code || '',
        name: f.fund_name || f.fund_short_name || '',
        type: f.fund_type || '',
        nav: f.nav || 0,
      }));
      setSuggestions(mapped);
      setShowSuggestions(mapped.length > 0);
      setHighlightIdx(-1);
    } catch {
      setSuggestions([]);
      setShowSuggestions(false);
    }
  }, []);

  const handleFundInput = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setFundInput(val);
    onFundSelect(null);
    if (debounceTimerRef.current) clearTimeout(debounceTimerRef.current);
    debounceTimerRef.current = setTimeout(() => searchFunds(val), 300);
  };

  const selectFund = (fund: FundSuggestion) => {
    onFundSelect(fund);
    setFundInput(`${fund.code} ${fund.name}`);
    setShowSuggestions(false);
    setHighlightIdx(-1);
  };

  const handleFundKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (!showSuggestions || suggestions.length === 0) return;
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setHighlightIdx(prev => Math.min(prev + 1, suggestions.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setHighlightIdx(prev => Math.max(prev - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      if (highlightIdx >= 0 && highlightIdx < suggestions.length) {
        selectFund(suggestions[highlightIdx]);
      }
    } else if (e.key === 'Escape') {
      setShowSuggestions(false);
    }
  };

  return (
    <div className="card p-4">
      <h3 className="text-sm font-bold text-gray-700 mb-3">回测参数</h3>
      <div className="grid grid-cols-2 md:grid-cols-5 gap-3">
        <div ref={wrapperRef} className="relative">
          <label className="text-xs text-gray-400 block mb-1">选择基金</label>
          <div className="relative">
            <input
              type="text"
              placeholder="输入基金代码或名称，如 320007 或 诺安成长"
              value={fundInput}
              onChange={handleFundInput}
              onFocus={() => fundInput.length >= 1 && suggestions.length > 0 && setShowSuggestions(true)}
              onKeyDown={handleFundKeyDown}
              className="w-full px-3 py-1.5 text-xs border border-gray-200 rounded-lg bg-white focus:outline-none focus:ring-1 focus:ring-brand-500 pr-7"
            />
            <Search className="absolute right-2 top-1/2 -translate-y-1/2 w-3.5 h-3.5 text-gray-300" />
          </div>
          {showSuggestions && suggestions.length > 0 && (
            <div className="absolute z-10 w-full mt-1 bg-white border border-gray-200 rounded-lg shadow-lg max-h-48 overflow-y-auto">
              {suggestions.map((f, idx) => (
                <div
                  key={f.code}
                  onClick={() => selectFund(f)}
                  className={`px-3 py-2 cursor-pointer flex justify-between items-center text-xs ${
                    idx === highlightIdx ? 'bg-brand-50' : 'hover:bg-gray-50'
                  }`}
                >
                  <span className="text-gray-700 truncate">
                    {f.name}
                    {f.type && <span className="ml-1 text-gray-400 text-[10px]">{f.type}</span>}
                  </span>
                  <span className="text-gray-400 text-[10px] shrink-0 ml-2">{f.code}</span>
                </div>
              ))}
            </div>
          )}
          {selectedFund && (
            <div className="mt-1 flex items-center gap-1">
              <span className="px-1.5 py-0.5 bg-brand-50 text-brand-600 text-[10px] rounded">{selectedFund.code}</span>
              <span className="text-[10px] text-gray-400">{selectedFund.name}</span>
              <button
                onClick={() => { onFundSelect(null); setFundInput(''); }}
                className="text-[10px] text-gray-300 hover:text-red-400 ml-0.5"
              >✕</button>
            </div>
          )}
        </div>
        <div>
          <label className="text-xs text-gray-400 block mb-1">开始日期</label>
          <input type="date" value={backtestParams.startDate}
            onChange={e => onParamsChange({ ...backtestParams, startDate: e.target.value })}
            className="w-full px-3 py-1.5 text-xs border border-gray-200 rounded-lg bg-white focus:outline-none focus:ring-1 focus:ring-brand-500" />
        </div>
        <div>
          <label className="text-xs text-gray-400 block mb-1">结束日期</label>
          <input type="date" value={backtestParams.endDate}
            onChange={e => onParamsChange({ ...backtestParams, endDate: e.target.value })}
            className="w-full px-3 py-1.5 text-xs border border-gray-200 rounded-lg bg-white focus:outline-none focus:ring-1 focus:ring-brand-500" />
        </div>
        <div>
          <label className="text-xs text-gray-400 block mb-1">初始买入金额（元）</label>
          <input type="number" value={backtestParams.initialCapital}
            onChange={e => onParamsChange({ ...backtestParams, initialCapital: Number(e.target.value) })}
            min={1000} step={1000}
            className="w-full px-3 py-1.5 text-xs border border-gray-200 rounded-lg bg-white font-mono focus:outline-none focus:ring-1 focus:ring-brand-500" />
        </div>
        <div>
          <label className="text-xs text-gray-400 block mb-1">因子方案</label>
          <select value={backtestParams.strategyId ?? ''}
            onChange={e => onParamsChange({ ...backtestParams, strategyId: Number(e.target.value) })}
            className="w-full px-3 py-1.5 text-xs border border-gray-200 rounded-lg bg-white focus:outline-none focus:ring-1 focus:ring-brand-500">
            {strategies.map(s => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
        </div>
      </div>
      {selectedFund && (
        <div className="mt-2 flex items-center gap-3 text-[10px] text-gray-400">
          <span>已选: <strong className="text-gray-600">{selectedFund.name}</strong></span>
          {(selectedFund.nav ?? 0) > 0 && <span>净值: {selectedFund.nav!.toFixed(4)}</span>}
          {selectedFund.type && <span>类型: {selectedFund.type}</span>}
          <span className="text-brand-500">将使用逐日追踪模式进行基金回测</span>
        </div>
      )}
    </div>
  );
}
