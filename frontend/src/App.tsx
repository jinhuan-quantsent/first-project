import { useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate, Outlet } from 'react-router-dom';
import AppLayout from './components/layout/AppLayout';
import Dashboard from './pages/DashboardV5';
import FundSearch from './pages/FundSearchV5';
import Watchlist from './pages/WatchlistV5';
import Portfolio from './pages/PortfolioV5';
import Review from './pages/Backtest';
import Login from './pages/Login';
import Register from './pages/Register';
import { useAppStore } from './store';

function ProtectedRoute() {
  const { auth } = useAppStore();

  useEffect(() => {
    auth.restoreSession();
  }, []);

  if (!auth.isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return <Outlet />;
}

function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route element={<ProtectedRoute />}>
          <Route element={<AppLayout />}>
            {/* V5.0：/ 默认指向基金查询页 */}
            <Route path="/" element={<FundSearch />} />
            <Route path="/watchlist" element={<Watchlist />} />
            <Route path="/portfolio" element={<Portfolio />} />
            <Route path="/review" element={<Review />} />
            {/* 兼容旧路径 */}
            <Route path="/search" element={<Navigate to="/" replace />} />
          </Route>
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
