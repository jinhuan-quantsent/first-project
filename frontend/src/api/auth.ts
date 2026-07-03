import client from './client';
import type { AuthResponse, ApiResponse } from '../types';

export async function login(email: string, password: string): Promise<AuthResponse> {
  const { data } = await client.post<ApiResponse<AuthResponse>>('/api/v5/auth/login', { email, password });
  return data.data;
}

export async function register(email: string, password: string): Promise<{ user_id: string; email: string; email_confirmed: boolean; message: string }> {
  const { data } = await client.post<ApiResponse>('/api/v5/auth/register', { email, password });
  return data.data as any;
}

export async function logout(): Promise<void> {
  try {
    await client.post('/api/v5/auth/logout');
  } finally {
    localStorage.removeItem('fsa_jwt_token');
    localStorage.removeItem('fsa_user_info');
  }
}
