import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { useAppStore } from '../store';

export default function Login() {
  const { auth } = useAppStore();
  const navigate = useNavigate();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [localError, setLocalError] = useState('');

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setLocalError('');
    auth.clearError();

    if (!email || !password) {
      setLocalError('请填写邮箱和密码');
      return;
    }
    if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      setLocalError('邮箱格式不正确');
      return;
    }
    if (password.length < 8) {
      setLocalError('密码长度至少 8 位');
      return;
    }

    try {
      await auth.login(email, password);
      navigate('/');
    } catch {
      // authError is set in store
    }
  };

  const errorMsg = localError || auth.authError;

  return (
    <div className="min-h-screen flex items-center justify-center bg-[var(--bg-primary)] px-4">
      <div className="w-full max-w-md bg-white rounded-2xl p-8 shadow-xl border border-gray-100">
        <h1 className="text-2xl font-bold text-gray-800 text-center mb-2">基金情绪分析系统</h1>
        <p className="text-gray-400 text-center mb-8">登录以访问个性化数据，或以游客身份浏览</p>

        {errorMsg && (
          <div className="mb-4 p-3 bg-red-50 border border-red-200 rounded-lg text-red-600 text-sm">
            {errorMsg}
          </div>
        )}

        <form onSubmit={handleSubmit} noValidate className="space-y-5">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1.5">邮箱</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="user@example.com"
              className="w-full px-4 py-2.5 bg-gray-50 border border-gray-200 rounded-lg text-gray-800 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1.5">密码</label>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="输入密码（8位以上）"
              className="w-full px-4 py-2.5 bg-gray-50 border border-gray-200 rounded-lg text-gray-800 placeholder-gray-400 focus:outline-none focus:ring-2 focus:ring-brand-500 focus:border-transparent"
            />
          </div>

          <button
            type="submit"
            disabled={auth.authLoading}
            className="w-full py-2.5 bg-brand-500 hover:bg-brand-600 disabled:bg-brand-200 text-white font-medium rounded-lg transition-colors"
          >
            {auth.authLoading ? '登录中...' : '登录'}
          </button>
        </form>

        {/* 游客模式入口 */}
        <div className="mt-5 flex items-center gap-3">
          <div className="flex-1 h-px bg-gray-200" />
          <span className="text-xs text-gray-400">或</span>
          <div className="flex-1 h-px bg-gray-200" />
        </div>
        <button
          type="button"
          onClick={() => {
            auth.guestLogin();
            navigate('/');
          }}
          className="mt-3 w-full py-2.5 border border-gray-300 text-gray-600 hover:bg-gray-50 font-medium rounded-lg transition-colors"
        >
          以游客身份访问
        </button>

        <p className="mt-6 text-center text-sm text-gray-500">
          还没有账号？{' '}
          <Link to="/register" className="text-brand-500 hover:text-brand-600">
            注册
          </Link>
        </p>
      </div>
    </div>
  );
}
