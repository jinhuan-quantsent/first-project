import { ChevronDown } from 'lucide-react';

/** 折叠参数面板 */
export function ParamPanel({ title, open, onToggle, badge, children }: {
  title: string; open: boolean; onToggle: () => void; badge?: string; children: React.ReactNode;
}) {
  return (
    <div className="card overflow-hidden">
      <button onClick={onToggle}
        className="w-full flex items-center justify-between px-4 py-2.5 text-xs font-medium text-gray-600 hover:bg-gray-50 transition-colors">
        <span className="flex items-center gap-2">
          {title}
          {badge && <span className="text-[10px] text-gray-400 bg-gray-100 px-1.5 py-0.5 rounded-full">{badge}</span>}
        </span>
        <ChevronDown className={`w-3.5 h-3.5 text-gray-400 transition-transform ${open ? 'rotate-180' : ''}`} />
      </button>
      {open && <div className="px-4 pb-3 space-y-2.5 border-t border-gray-100">{children}</div>}
    </div>
  );
}
