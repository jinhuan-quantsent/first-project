/**
 * Toast - 全局通知组件
 * 使用 Zustand 管理状态，支持 success / error / info 三种类型
 * 自动 2.5s 消失，带 translateY + opacity 过渡动画
 */
import { create } from 'zustand';
import { CheckCircle, XCircle, Info, X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { clsx } from 'clsx';

// ==================== Store ====================
interface ToastItem {
  id: number;
  type: 'success' | 'error' | 'info';
  message: string;
}

interface ToastState {
  toasts: ToastItem[];
  addToast: (type: ToastItem['type'], message: string) => void;
  removeToast: (id: number) => void;
}

let _nextId = 0;

export const useToastStore = create<ToastState>((set) => ({
  toasts: [],
  addToast: (type, message) => {
    const id = ++_nextId;
    set((s) => ({ toasts: [...s.toasts, { id, type, message }] }));
    // 自动移除
    setTimeout(() => {
      set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) }));
    }, 2500);
  },
  removeToast: (id) => {
    set((s) => ({ toasts: s.toasts.filter((t) => t.id !== id) }));
  },
}));

// ==================== 便捷方法 ====================
export const toast = {
  success: (msg: string) => useToastStore.getState().addToast('success', msg),
  error: (msg: string) => useToastStore.getState().addToast('error', msg),
  info: (msg: string) => useToastStore.getState().addToast('info', msg),
};

// ==================== 单条Toast组件 ====================
function ToastCard({ item, onRemove }: { item: ToastItem; onRemove: () => void }) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    // 入场动画
    requestAnimationFrame(() => setVisible(true));
  }, []);

  const IconMap = {
    success: <CheckCircle className="w-4 h-4 text-green-500" />,
    error: <XCircle className="w-4 h-4 text-red-500" />,
    info: <Info className="w-4 h-4 text-blue-500" />,
  };

  const BorderMap = {
    success: 'border-l-green-500',
    error: 'border-l-red-500',
    info: 'border-l-blue-500',
  };

  return (
    <div
      className={clsx(
        'flex items-center gap-2 px-4 py-3 bg-white border border-gray-100 rounded-lg shadow-lg border-l-4',
        BorderMap[item.type],
        'transition-all duration-300 ease-out',
        visible ? 'translate-y-0 opacity-100' : 'translate-y-4 opacity-0',
      )}
    >
      {IconMap[item.type]}
      <span className="text-sm text-gray-700 flex-1">{item.message}</span>
      <button onClick={onRemove} className="text-gray-300 hover:text-gray-500 transition-colors">
        <X className="w-3.5 h-3.5" />
      </button>
    </div>
  );
}

// ==================== 全局Toast容器 ====================
export default function ToastContainer() {
  const { toasts, removeToast } = useToastStore();

  if (toasts.length === 0) return null;

  return (
    <div className="fixed top-4 right-4 z-[9999] flex flex-col gap-2 w-80">
      {toasts.map((item) => (
        <ToastCard key={item.id} item={item} onRemove={() => removeToast(item.id)} />
      ))}
    </div>
  );
}
