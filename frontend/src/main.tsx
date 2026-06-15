import React from 'react';
import ReactDOM from 'react-dom/client';
import App from './App';
import './index.css';

/**
 * ErrorBoundary — 捕获所有子组件渲染/事件错误，
 * 防止整个 App 白屏，显示错误信息 + 刷新按钮
 */
class ErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { hasError: boolean; errorMessage: string }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false, errorMessage: '' };
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, errorMessage: error.message || '未知错误' };
  }

  componentDidCatch(error: Error, errorInfo: React.ErrorInfo) {
    console.error('[ErrorBoundary]', error, errorInfo);
  }

  private handleReload = () => {
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      return (
        <div className="min-h-screen flex items-center justify-center bg-gray-50 px-4">
          <div className="card p-8 max-w-md w-full text-center space-y-4">
            <div className="text-4xl">⚠️</div>
            <p className="text-red-500 font-bold text-lg">页面出现错误</p>
            <p className="text-xs text-gray-500 font-mono break-all">{this.state.errorMessage}</p>
            <button
              onClick={this.handleReload}
              className="px-4 py-1.5 text-xs bg-brand-500 text-white rounded-lg hover:bg-brand-600 transition-colors"
            >
              刷新页面
            </button>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <App />
    </ErrorBoundary>
  </React.StrictMode>,
);
