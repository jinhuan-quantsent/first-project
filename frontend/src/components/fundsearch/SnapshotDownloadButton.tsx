/**
 * SnapshotDownloadButton - 决策快照 & 盘中预演 CSV下载按钮
 *
 * V5.3 新增盘中预演快照下载选项。
 * 放在基金查询页空闲区域下方，点击后弹出选择对话框。
 */
import { useState, useCallback } from 'react';
import { Download, X, Loader2, FileSpreadsheet, TrendingUp } from 'lucide-react';

const V5_PREFIX = '/api/v5';

/** 下载类型 */
const DOWNLOAD_TYPE_OPTIONS = [
  { value: 'snapshot', label: '决策快照', desc: '每日信号、评级、仓位建议历史记录', icon: FileSpreadsheet },
  { value: 'intraday_preview', label: '盘中预演快照', desc: '当天实时预演评分、估值、Gate触发', icon: TrendingUp },
];

/** 标的类型选项（仅决策快照使用） */
const TARGET_TYPE_OPTIONS = [
  { value: '', label: '全部' },
  { value: 'broad', label: '宽基指数' },
  { value: 'sector', label: '板块' },
  { value: 'fund', label: '持仓基金' },
];

export default function SnapshotDownloadButton() {
  const [showDialog, setShowDialog] = useState(false);
  const [downloadType, setDownloadType] = useState<'snapshot' | 'intraday_preview'>('snapshot');
  const [startDate, setStartDate] = useState(() => {
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
      let url: string;
      let filename: string;

      if (downloadType === 'intraday_preview') {
        // 盘中预演下载（仅当天数据）
        url = `${V5_PREFIX}/intraday-preview-download`;
        filename = `盘中预演快照_${new Date().toISOString().slice(0, 10)}.csv`;
      } else {
        // 决策快照下载（历史范围）
        const params = new URLSearchParams();
        if (startDate) params.set('start_date', startDate);
        if (endDate) params.set('end_date', endDate);
        if (targetType) params.set('target_type', targetType);
        url = `${V5_PREFIX}/snapshot-download?${params.toString()}`;
        filename = `决策快照_${startDate}_${endDate}.csv`;
      }

      const resp = await fetch(url);
      if (!resp.ok) throw new Error(`下载失败: HTTP ${resp.status}`);

      const blob = await resp.blob();
      const cdFilename = resp.headers.get('Content-Disposition')
        ? resp.headers.get('Content-Disposition')!.split('filename=')[1]?.replace(/"/g, '')
        : filename;

      const a = document.createElement('a');
      a.href = URL.createObjectURL(blob);
      a.download = cdFilename || filename;
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
  }, [downloadType, startDate, endDate, targetType]);

  const isPreview = downloadType === 'intraday_preview';

  return (
    <>
      {/* 主按钮 */}
      <button
        onClick={() => setShowDialog(true)}
        className="w-full card p-4 flex items-center gap-3 hover:shadow-md transition-shadow cursor-pointer group"
      >
        <div className="w-10 h-10 rounded-full bg-teal-50 flex items-center justify-center">
          <FileSpreadsheet className="w-5 h-5 text-teal-500" />
        </div>
        <div className="flex-1">
          <p className="text-sm font-medium text-gray-700 group-hover:text-teal-600 transition-colors">
            快照下载
          </p>
          <p className="text-xs text-gray-400">
            决策快照 / 盘中预演 CSV 导出
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
              <h3 className="text-base font-bold text-gray-800">快照下载</h3>
              <button
                onClick={() => { if (!downloading) setShowDialog(false); }}
                className="text-gray-300 hover:text-gray-500 transition-colors"
              >
                <X className="w-4 h-4" />
              </button>
            </div>

            {/* 下载类型选择 */}
            <div className="space-y-1.5">
              <label className="text-xs font-medium text-gray-600">下载类型</label>
              <div className="grid grid-cols-2 gap-2">
                {DOWNLOAD_TYPE_OPTIONS.map(opt => (
                  <button
                    key={opt.value}
                    onClick={() => setDownloadType(opt.value as 'snapshot' | 'intraday_preview')}
                    className={`p-3 rounded-lg border text-left transition-all ${
                      downloadType === opt.value
                        ? 'border-teal-400 bg-teal-50 ring-1 ring-teal-400'
                        : 'border-gray-200 bg-white hover:border-gray-300'
                    }`}
                  >
                    <div className="flex items-center gap-2 mb-1">
                      <opt.icon className={`w-4 h-4 ${downloadType === opt.value ? 'text-teal-500' : 'text-gray-400'}`} />
                      <span className={`text-sm font-medium ${downloadType === opt.value ? 'text-teal-700' : 'text-gray-700'}`}>
                        {opt.label}
                      </span>
                    </div>
                    <p className="text-xs text-gray-500">{opt.desc}</p>
                  </button>
                ))}
              </div>
            </div>

            {/* 条件选项：仅决策快照需要日期和类型筛选 */}
            {!isPreview && (
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
            )}

            {/* 预演模式提示 */}
            {isPreview && (
              <div className="bg-amber-50 border border-amber-200 rounded-lg px-3 py-2 text-xs text-amber-700">
                盘中预演快照仅导出当天实时数据，需在交易时段（9:30-15:00）下载才有数据。
              </div>
            )}

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
