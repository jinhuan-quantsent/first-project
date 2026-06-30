import { useState } from 'react';
import { Pencil } from 'lucide-react';
import type { BacktestStrategy } from '../../stores/backtest';

/** 方案管理栏 — 下拉选择 + 4按钮 + 重命名 */
export function StrategyBar({ strategies, activeId, onSelect, onSave, onDelete, onNew, onApply, onRename, systemActiveSchemeName }: {
  strategies: BacktestStrategy[];
  activeId: number | null;
  onSelect: (id: number) => void;
  onSave: () => void;
  onDelete: (id: number) => void;
  onNew: () => void;
  onApply: () => void;
  onRename: (newName: string) => void;
  systemActiveSchemeName: string | null;
}) {
  const [editing, setEditing] = useState(false);
  const [editName, setEditName] = useState('');
  const activeStrategy = strategies.find(s => s.id === activeId) ?? null;

  const startRename = () => {
    if (!activeStrategy) return;
    setEditName(activeStrategy.name);
    setEditing(true);
  };

  const confirmRename = () => {
    const trimmed = editName.trim();
    if (trimmed && trimmed !== activeStrategy?.name) {
      onRename(trimmed);
    }
    setEditing(false);
  };

  const handleRenameKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter') confirmRename();
    if (e.key === 'Escape') setEditing(false);
  };

  return (
    <div className="card p-3 flex items-center gap-3 overflow-x-auto">
      <div className="flex items-center gap-2 shrink-0">
        <span className="text-xs text-gray-500 shrink-0">当前方案：</span>
        <select
          value={activeId ?? ''}
          onChange={e => onSelect(Number(e.target.value))}
          className="px-3 py-1.5 text-xs border border-gray-200 rounded-lg bg-white text-gray-700 focus:outline-none focus:ring-1 focus:ring-brand-500 min-w-[120px]"
        >
          {strategies.map(s => (
            <option key={s.id} value={s.id}>
              {s.name}{s.is_active ? ' (活跃)' : ''}
            </option>
          ))}
        </select>
        {activeStrategy?.is_active && (
          <span className="flex items-center gap-1 text-xs text-green-600 bg-green-50 px-1.5 py-0.5 rounded-full shrink-0">
            <span className="w-1.5 h-1.5 rounded-full bg-green-500" />
            活跃
          </span>
        )}
        {activeStrategy && editing ? (
          <input
            type="text"
            value={editName}
            onChange={e => setEditName(e.target.value)}
            onBlur={confirmRename}
            onKeyDown={handleRenameKeyDown}
            autoFocus
            className="px-2 py-0.5 text-xs border border-brand-300 rounded focus:outline-none focus:ring-1 focus:ring-brand-500 w-28"
          />
        ) : activeStrategy ? (
          <button
            onClick={startRename}
            className="p-0.5 rounded hover:bg-gray-100 text-gray-400 hover:text-brand-500 transition-colors"
            title="重命名方案"
          >
            <Pencil className="w-3 h-3" />
          </button>
        ) : null}
      </div>

      <div className="w-px h-5 bg-gray-200 shrink-0" />

      <div className="flex items-center gap-1.5 shrink-0">
        <button onClick={onNew}
          className="px-3 py-1.5 text-xs border border-dashed border-gray-300 rounded-lg text-gray-500
                     hover:border-brand-500 hover:text-brand-500 transition-colors">
          新建方案
        </button>
        <button onClick={onSave} disabled={!activeId}
          className="px-3 py-1.5 text-xs border border-gray-200 rounded-lg text-gray-600
                     hover:bg-gray-50 hover:border-brand-300 transition-colors disabled:opacity-40 disabled:cursor-not-allowed">
          保存当前
        </button>
        <button onClick={() => activeId && onDelete(activeId)} disabled={!activeId}
          className="px-3 py-1.5 text-xs border border-red-200 rounded-lg text-red-500
                     hover:bg-red-50 hover:border-red-400 transition-colors disabled:opacity-40 disabled:cursor-not-allowed">
          删除方案
        </button>
        <button onClick={onApply} disabled={!activeId}
          className="px-3 py-1.5 text-xs border border-brand-200 rounded-lg text-brand-600 bg-brand-50
                     hover:bg-brand-100 hover:border-brand-400 transition-colors disabled:opacity-40 disabled:cursor-not-allowed">
          应用到系统
        </button>

        <div className="ml-auto flex items-center gap-2 shrink-0">
          {systemActiveSchemeName && (
            <span className="text-xs text-green-400 bg-green-900/30 px-2 py-1 rounded whitespace-nowrap">
              系统方案: {systemActiveSchemeName}
            </span>
          )}
        </div>
      </div>
    </div>
  );
}
