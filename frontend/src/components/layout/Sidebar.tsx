import { NavLink, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  Search,
  Star,
  Briefcase,
  BarChart3,
} from 'lucide-react';

const NAV_ITEMS = [
  { to: '/', icon: LayoutDashboard, label: '仪表盘' },
  { to: '/search', icon: Search, label: '基金查询' },
  { to: '/watchlist', icon: Star, label: '自选' },
  { to: '/portfolio', icon: Briefcase, label: '持仓' },
  { to: '/review', icon: BarChart3, label: '复盘' },
];

export default function Sidebar() {
  const location = useLocation();

  return (
    <aside
      className="hidden md:flex flex-col bg-white border-r border-gray-200 shrink-0 overflow-y-auto"
      style={{ width: 'var(--sidebar-width)' }}
    >
      {/* Logo */}
      <div className="flex items-center gap-2 px-4 py-4 border-b border-gray-100">
        <div className="w-8 h-8 rounded-lg bg-gradient-to-br from-blue-500 to-purple-600 flex items-center justify-center">
          <BarChart3 className="w-4 h-4 text-white" />
        </div>
        <div>
          <div className="text-sm font-bold text-gray-800">情绪分析</div>
          <div className="text-[10px] text-gray-400">V3.5</div>
        </div>
      </div>

      {/* 导航菜单 */}
      <nav className="flex-1 py-3">
        {NAV_ITEMS.map((item) => {
          const isActive = item.to === '/'
            ? location.pathname === '/'
            : location.pathname.startsWith(item.to);

          return (
            <NavLink
              key={item.to}
              to={item.to}
              className={`flex items-center gap-3 px-4 py-2.5 mx-2 rounded-lg text-sm transition-colors ${
                isActive
                  ? 'bg-blue-50 text-blue-600 font-medium'
                  : 'text-gray-600 hover:bg-gray-50 hover:text-gray-800'
              }`}
            >
              <item.icon className="w-4 h-4" />
              <span>{item.label}</span>
            </NavLink>
          );
        })}
      </nav>

      {/* 底部信息 */}
      <div className="px-4 py-3 border-t border-gray-100">
        <div className="text-[10px] text-gray-400">
          数据仅供参考<br />
          不构成投资建议
        </div>
      </div>
    </aside>
  );
}
