import axios from 'axios';
import type { ApiResponse } from '../types';

const client = axios.create({
  baseURL: import.meta.env.VITE_API_BASE_URL || '',
  timeout: 15000,
  headers: {
    'Content-Type': 'application/json',
  },
});

const TOKEN_KEY = 'fsa_jwt_token';

// 请求拦截器：注入 JWT（游客 token 不注入，让后端 AUTH_DISABLED 自动降级）
client.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem(TOKEN_KEY);
    if (token && token !== 'guest-token' && config.headers) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => Promise.reject(error),
);

// 响应拦截器：处理业务码 + 401 跳转登录
client.interceptors.response.use(
  (response) => {
    const data = response.data as ApiResponse;
    if (data.code !== 0) {
      console.warn(`API Warning: ${data.message}`);
    }
    return response;
  },
  (error) => {
    if (error.response) {
      const status = error.response.status;
      if (status === 401) {
        const token = localStorage.getItem(TOKEN_KEY);
        // 游客模式下遇到 401 不强制跳转登录页（该接口可能需要认证，但不应阻断浏览）
        if (token === 'guest-token') {
          console.warn('Guest user hit 401 on a protected endpoint, skipping redirect.');
        } else {
          // Token 过期或无效 → 清除并跳转登录页
          localStorage.removeItem(TOKEN_KEY);
          localStorage.removeItem('fsa_user_info');
          if (window.location.pathname !== '/login') {
            window.location.href = '/login';
          }
        }
      }
      console.error(`API Error ${status}:`, error.response.data);
    } else if (error.request) {
      console.error('Network Error:', error.message);
    }
    return Promise.reject(error);
  },
);

export default client;
