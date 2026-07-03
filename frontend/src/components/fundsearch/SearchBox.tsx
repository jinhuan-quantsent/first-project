/**
 * SearchBox - 基金搜索框
 * 支持关键词搜索 + 类型筛选 + 防抖（由父组件控制）
 */
import { Search } from 'lucide-react';
import { clsx } from 'clsx';

const FUND_TYPES = ['', '股票型', '混合型', '指数型', '债券型', '货币型'];

interface SearchBoxProps {
  keyword: string;
  fundType: string;
  loading: boolean;
  onKeywordChange: (v: string) => void;
  onTypeChange: (v: string) => void;
  onSearch: () => void;
}

export default function SearchBox({
  keyword,
  fundType,
  loading,
  onKeywordChange,
  onTypeChange,
  onSearch,
}: SearchBoxProps) {
  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') onSearch();
  };

  return (
    <div className="card p-4">
      <div className="flex flex-col sm:flex-row gap-3">
        {/* 搜索输入框 */}
        <div className="flex-1 relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-gray-400 pointer-events-none" />
          <input
            type="text"
            value={keyword}
            onChange={(e) => onKeywordChange(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="搜索基金名称、代码、简称..."
            className="w-full pl-9 pr-4 py-2 text-sm border border-gray-200 rounded-lg
                       focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent
                       placeholder:text-gray-300"
          />
        </div>

        {/* 类型筛选 */}
        <select
          value={fundType}
          onChange={(e) => onTypeChange(e.target.value)}
          className="px-3 py-2 text-sm border border-gray-200 rounded-lg
                     focus:outline-none focus:ring-2 focus:ring-brand-500 bg-white"
        >
          {FUND_TYPES.map((t) => (
            <option key={t} value={t}>
              {t || '全部类型'}
            </option>
          ))}
        </select>

        {/* 搜索按钮 */}
        <button
          onClick={onSearch}
          disabled={loading}
          className={clsx(
            'px-6 py-2 text-sm font-medium rounded-lg text-white transition-colors',
            loading
              ? 'bg-gray-400 cursor-not-allowed'
              : 'bg-brand-500 hover:bg-brand-600 active:bg-brand-700',
          )}
        >
          {loading ? '搜索中...' : '搜索'}
        </button>
      </div>
    </div>
  );
}
