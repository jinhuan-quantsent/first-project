import { useEffect } from 'react';
import { Outlet, useNavigate } from 'react-router-dom';
import MarketSnapshotBar from './MarketSnapshotBar';
import Sidebar from './Sidebar';
import Disclaimer from '../common/Disclaimer';
import Avatar from '../common/Avatar';
import { useAppStore } from '../../store';

export default function AppLayout() {
  const { loadSnapshot, loadMultiIndex, disclaimerAccepted, auth } = useAppStore();
  const navigate = useNavigate();

  useEffect(() => {
    loadSnapshot();
    loadMultiIndex();
    const interval = setInterval(() => {
      loadSnapshot();
      loadMultiIndex();
    }, 60000);
    return () => clearInterval(interval);
  }, [loadSnapshot, loadMultiIndex]);

  const handleLogout = () => {
    auth.logout();
    navigate('/login');
  };

  return (
    <div className="h-full flex flex-col">
      <MarketSnapshotBar />

      <div className="flex flex-1 overflow-hidden" style={{ paddingTop: 'var(--snapshot-bar-height)' }}>
        <Sidebar />

        <main className="flex-1 overflow-y-auto bg-gray-50 p-4 md:p-6">
          {/* 顶部用户栏 */}
          <div className="flex justify-end items-center gap-3 mb-4">
            <div className="flex items-center gap-2">
              <Avatar email={auth.user?.email || ''} size={28} />
              <span className="text-sm text-gray-600">
                {auth.user?.email || ''}
              </span>
            </div>
            <button
              onClick={handleLogout}
              className="text-sm text-gray-500 hover:text-red-500 transition-colors px-2 py-1 rounded hover:bg-red-50"
            >
              登出
            </button>
          </div>

          <Outlet />
        </main>
      </div>

      {!disclaimerAccepted && <Disclaimer />}
    </div>
  );
}
