/**
 * CollapsibleSection — 可折叠区域组件
 */
import { useState } from 'react';
import { ChevronUp, ChevronDown } from 'lucide-react';

export default function CollapsibleSection({
  title,
  icon: Icon,
  badge,
  defaultOpen = false,
  onToggle,
  children,
}: {
  title: string;
  icon: React.ComponentType<{ className?: string }>;
  badge?: string;
  defaultOpen?: boolean;
  onToggle?: () => void;
  children: React.ReactNode;
}) {
  const [open, setOpen] = useState(defaultOpen);

  const handleToggle = () => {
    const next = !open;
    setOpen(next);
    if (next && onToggle) onToggle();
  };

  return (
    <div>
      <button
        onClick={handleToggle}
        className="flex items-center gap-2 mb-2 w-full text-left hover:bg-gray-50/50 rounded px-1 py-0.5 transition-colors"
      >
        <Icon className="w-3.5 h-3.5 text-gray-400 shrink-0" />
        <span className="text-xs font-medium text-gray-600">{title}</span>
        {badge && <span className="text-[10px] text-gray-400 ml-auto mr-1">{badge}</span>}
        {open ? (
          <ChevronUp className="w-3 h-3 text-gray-400 shrink-0" />
        ) : (
          <ChevronDown className="w-3 h-3 text-gray-400 shrink-0" />
        )}
      </button>
      {open && children}
    </div>
  );
}
