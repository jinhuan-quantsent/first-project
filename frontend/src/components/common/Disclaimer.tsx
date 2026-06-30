import { useAppStore } from '../../store';
import { AlertTriangle } from 'lucide-react';

export default function Disclaimer() {
  const acceptDisclaimer = useAppStore((s) => s.acceptDisclaimer);

  return (
    <div className="fixed inset-0 z-[100] bg-black/50 flex items-center justify-center p-4">
      <div className="bg-white rounded-xl shadow-2xl max-w-md w-full p-6 animate-fade-in">
        <div className="flex items-center gap-3 mb-4">
          <AlertTriangle className="w-6 h-6 text-orange-400" />
          <h2 className="text-lg font-bold text-gray-800">免责声明</h2>
        </div>

        <div className="text-sm text-gray-600 space-y-3 mb-6">
          <p>
            <strong>基金情绪分析系统</strong>（以下简称"本系统"）是一款辅助决策工具，所有数据和指标仅供学习和参考。
          </p>
          <p>
            本系统提供的情绪评分、操作建议、仓位建议等内容
            <span className="text-red-500 font-medium">不构成任何投资建议</span>。
          </p>
          <ul className="list-disc list-inside space-y-1 text-gray-500">
            <li>基金投资有风险，过往业绩不代表未来表现</li>
            <li>情绪指标基于历史数据模型，存在滞后性和偏差</li>
            <li>用户应独立判断并承担投资决策的全部风险</li>
          </ul>
        </div>

        <button
          onClick={acceptDisclaimer}
          className="w-full py-2.5 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition-colors"
        >
          我已了解，继续使用
        </button>
      </div>
    </div>
  );
}
