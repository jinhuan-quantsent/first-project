import { useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import AppLayout from './components/layout/AppLayout';
import ToastContainer from './components/common/Toast';
import Dashboard from './pages/DashboardV5';
import FundSearch from './pages/FundSearchV5';
import Watchlist from './pages/WatchlistV5';
import Portfolio from './pages/PortfolioV5';
import Backtest from './pages/Backtest';
import Login from './pages/Login';
import Register from './pages/Register';
import { useAppStore } from './store';

function App() {
  const { auth } = useAppStore();

  useEffect(() => {
    auth.restoreSession();
  }, []);

  return (
    <BrowserRouter>
      <ToastContainer />
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route element={<AppLayout />}>
          {/* V5.0：/ 默认指向基金查询页 */}
          <Route path="/" element={<FundSearch />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/watchlist" element={<Watchlist />} />
          <Route path="/portfolio" element={<Portfolio />} />
          <Route path="/backtest" element={<Backtest />} />
          {/* 兼容旧路径 /review → /backtest */}
          <Route path="/review" element={<Navigate to="/backtest" replace />} />
          {/* 兼容旧路径 */}
          <Route path="/search" element={<Navigate to="/" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}

export default App;
