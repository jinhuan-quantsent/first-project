import { useEffect } from 'react';
import { Outlet } from 'react-router-dom';
import MarketSnapshotBar from './MarketSnapshotBar';
import Sidebar from './Sidebar';
import Disclaimer from '../common/Disclaimer';
import { useAppStore } from '../../store';

export default function AppLayout() {
  const { loadSnapshot, loadMultiIndex, disclaimerAccepted } = useAppStore();

  useEffect(() => {
    loadSnapshot();
    loadMultiIndex();
    // 每60秒刷新
    const interval = setInterval(() => {
      loadSnapshot();
      loadMultiIndex();
    }, 60000);
    return () => clearInterval(interval);
  }, [loadSnapshot, loadMultiIndex]);

  return (
    <div className="h-full flex flex-col">
      {/* 顶部快照条 - sticky 40px */}
      <MarketSnapshotBar />

      <div className="flex flex-1 overflow-hidden" style={{ paddingTop: 'var(--snapshot-bar-height)' }}>
        {/* 左侧导航 */}
        <Sidebar />

        {/* 右侧内容 */}
        <main className="flex-1 overflow-y-auto bg-gray-50 p-4 md:p-6">
          <Outlet />
        </main>
      </div>

      {/* 免责声明弹窗 */}
      {!disclaimerAccepted && <Disclaimer />}
    </div>
  );
}
