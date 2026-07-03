/**
 * SnapshotDownloadButton - 决策快照CSV下载按钮
 *
 * 放在基金查询页空闲区域下方，点击后弹出日期范围+类型选择，
 * 然后直接触发浏览器下载 CSV 文件。
 */
import { useState, useCallback } from 'react';
import { Download, X, Loader2, FileSpreadsheet } from 'lucide-react';

const V5_PREFIX = '/api/v5';

/** 标的类型选项 */
const TARGET_TYPE_OPTIONS = [
  { value: '', label: '全部' },
  { value: 'broad', label: '宽基指数' },
  { value: 'sector', label: '板块' },
  { value: 'fund', label: '持仓基金' },
];

export default function SnapshotDownloadButton() {
  const [showDialog, setShowDialog] = useState(false);
  const [startDate, setStartDate] = useState(() => {
    // 默认最近30天
    const d = new Date();
    d.setDate(d.getDate() - 30);
    return d.toISOString().slice(0, 10);
  });
  const [endDate, setEndDate] = useState(() => new Date().toISOString().slice(0, 10));
  const [targetType, setTargetType] = useState('');
  const [downloading, setDownloading] = useState(false);

  const handleDownload = useCallback(async () => {
    setDownloading(true);
    try {
      const params = new URLSearchParams();
      if (startDate) params.set('start_date', startDate);
      if (endDate) params.set('end_date', endDate);
      if (targetType) params.set('target_type', targetType);

      const url = `${V5_PREFIX}/snapshot-download?${params.toString()}`;

      // 直接用 fetch + blob 下载，避免 axios 拦截
      const resp = await fetch(url);
      if (!resp.ok) throw new Error(`下载失败: HTTP ${resp.status}`);

      const blob = await resp.blob();
      const filename = resp.headers.get('Content-Disposition')
        ? resp.headers.get('Content-Disposition')!.split('filename=')[1]?.replace(/"/g, '')
        : `决策快照_${startDate}_${endDate}.csv`;

      // 创建临时 <a> 触发浏览器下载
      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = filename || 'decision_snapshot.csv';
      document.body.appendChild(a);
      a.click();
      document.body.removeChild(a);
      URL.revokeObjectURL(a.href);

      setShowDialog(false);
    } catch (err: any) {
      alert(err?.message || '下载失败，请检查网络');
    } finally {
      setDownloading(false);
    }
  }, [startDate, endDate, targetType]);

  return (
    <>
      {/* 主按钮：放在基金查询页空闲区下方 */}
      <button
        onClick={() => setShowDialog(true)}
        className="w-full card p-4 flex items-center gap-3 hover:shadow-md transition-shadow cursor-pointer group"
      >
        <div className="w-10 h-10 rounded-full bg-teal-50 flex items-center justify-center">
          <FileSpreadsheet className="w-5 h-5 text-teal-500" />
        </div>
        <div className="flex-1">
          <p className="text-sm font-medium text-gray-700 group-hover:text-teal-600 transition-colors">
            决策快照下载
          </p>
          <p className="text-xs text-gray-400">
            下载每日信号、评级、仓位建议的历史记录（CSV）
          </p>
        </div>
        <Download className="w-4 h-4 text-gray-400 group-hover:text-teal-500 transition-colors" />
      </button>

      {/* 下载选项对话框 */}
      {showDialog && (
        <div
          className="fixed inset-0 bg-black/40 z-50 flex items-center justify-center"
          onClick={() => { if (!downloading) setShowDialog(false); }}
        >
          <div
            className="bg-white rounded-2xl shadow-2xl w-[380px] max-w-[90vw] p-6 space-y-4"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between">
              <h3 className="text-base font-bold text-gray-800">下载决策快照</h3>
              <button
                onClick={() => { if (!downloading) setShowDialog(false); }}
                className="text-gray-300 hover:text-gray-500 transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            <div className="space-y-3">
              <div className="space-y-1.5">
                <label className="text-xs font-medium text-gray-600">起始日期</label>
                <input
                  type="date"
                  value={startDate}
                  onChange={(e) => setStartDate(e.target.value)}
                  className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-teal-400"
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-medium text-gray-600">结束日期</label>
                <input
                  type="date"
                  value={endDate}
                  onChange={(e) => setEndDate(e.target.value)}
                  className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-teal-400"
                />
              </div>

              <div className="space-y-1.5">
                <label className="text-xs font-medium text-gray-600">标的类型</label>
                <select
                  value={targetType}
                  onChange={(e) => setTargetType(e.target.value)}
                  className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-teal-400"
                >
                  {TARGET_TYPE_OPTIONS.map(opt => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </div>
            </div>

            <div className="flex items-center gap-3 pt-2">
              <button
                onClick={() => setShowDialog(false)}
                disabled={downloading}
                className="flex-1 py-2 rounded-lg text-sm font-medium text-gray-500 bg-gray-100 hover:bg-gray-200 transition-colors disabled:opacity-50"
              >
                取消
              </button>
              <button
                onClick={handleDownload}
                disabled={downloading}
                className="flex-1 py-2 rounded-lg text-sm font-medium text-white bg-teal-500 hover:bg-teal-600 transition-colors disabled:bg-gray-300 disabled:cursor-not-allowed flex items-center justify-center gap-1.5"
              >
                {downloading ? (
                  <>
                    <Loader2 className="w-4 h-4 animate-spin" />
                    下载中...
                  </>
                ) : (
                  <>
                    <Download className="w-4 h-4" />
                    下载 CSV
                  </>
                )}
              </button>
            </div>
          </div>
        </div>
      )}
    </>
  );
}
