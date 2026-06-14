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

// 请求拦截器：注入 JWT
client.interceptors.request.use(
  (config) => {
    const token = localStorage.getItem(TOKEN_KEY);
    if (token && config.headers) {
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
        // Token 过期或无效 → 清除并跳转登录页
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem('fsa_user_info');
        if (window.location.pathname !== '/login') {
          window.location.href = '/login';
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
