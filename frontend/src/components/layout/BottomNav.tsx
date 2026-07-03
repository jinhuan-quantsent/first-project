import { NavLink, useLocation } from 'react-router-dom';
import {
  LayoutDashboard,
  Search,
  Star,
  Briefcase,
  BarChart3,
  Layers,
  Radio,
} from 'lucide-react';
import { clsx } from 'clsx';

const NAV_ITEMS = [
  { to: '/dashboard', icon: LayoutDashboard, label: '大盘' },
  { to: '/signals', icon: Radio, label: '信号' },
  { to: '/', icon: Search, label: '查询' },
  { to: '/watchlist', icon: Star, label: '自选' },
  { to: '/portfolio', icon: Briefcase, label: '持仓' },
  { to: '/sectors', icon: Layers, label: '板块' },
  { to: '/backtest', icon: BarChart3, label: '回测' },
];

export default function BottomNav() {
  const location = useLocation();

  return (
    <nav
      className="md:hidden fixed bottom-0 left-0 right-0 bg-white border-t border-gray-200 flex items-center justify-around z-50"
      style={{ height: '56px', paddingBottom: 'env(safe-area-inset-bottom)' }}
    >
      {NAV_ITEMS.map((item) => {
        const isActive = item.to === '/'
          ? location.pathname === '/'
          : location.pathname.startsWith(item.to);
        return (
          <NavLink
            key={item.to}
            to={item.to}
            className={clsx(
              'flex flex-col items-center justify-center gap-0.5 py-1 px-1 transition-colors min-w-0',
              isActive ? 'text-brand-500' : 'text-gray-400'
            )}
          >
            <item.icon className="w-[18px] h-[18px]" />
            <span className="text-[10px]">{item.label}</span>
          </NavLink>
        );
      })}
    </nav>
  );
}
