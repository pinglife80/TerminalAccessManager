import axios from 'axios';
import { useAuthStore } from '@/store/auth';

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
  timeout: 30000,
});

apiClient.interceptors.request.use(
  (config) => {
    const token = sessionStorage.getItem('access_token');
    if (token) {
      config.headers.Authorization = `Bearer ${token}`;
    }
    return config;
  },
  (error) => {
    return Promise.reject(error);
  }
);

// Concurrent refresh control: only one refresh at a time
let isRefreshing = false;
let failedQueue: Array<{
  resolve: (token: string) => void;
  reject: (error: unknown) => void;
}> = [];

const processQueue = (error: unknown, token: string | null = null) => {
  failedQueue.forEach(({ resolve, reject }) => {
    if (error) {
      reject(error);
    } else {
      resolve(token!);
    }
  });
  failedQueue = [];
};

apiClient.interceptors.response.use(
  (response) => response,
  async (error) => {
    const originalRequest = error.config;

    // Skip token refresh for login/auth endpoints
    const isAuthEndpoint = originalRequest.url?.includes('/auth/login') ||
      originalRequest.url?.includes('/auth/refresh');

    if (error.response?.status === 401 && !originalRequest._retry && !isAuthEndpoint) {
      // If already refreshing, queue this request
      if (isRefreshing) {
        return new Promise((resolve, reject) => {
          failedQueue.push({
            resolve: (token: string) => {
              originalRequest._retry = true; // Prevent infinite loop on re-401
              originalRequest.headers.Authorization = `Bearer ${token}`;
              resolve(apiClient(originalRequest));
            },
            reject,
          });
        });
      }

      originalRequest._retry = true;
      isRefreshing = true;

      try {
        const refreshToken = sessionStorage.getItem('refresh_token');
        if (!refreshToken) {
          throw new Error('No refresh token');
        }

        const response = await apiClient.post('/auth/refresh', {
          refresh_token: refreshToken,
        }, {
          timeout: 10000,
        });

        const { access_token, refresh_token } = response.data;
        sessionStorage.setItem('access_token', access_token);
        sessionStorage.setItem('refresh_token', refresh_token);

        // Process queued requests with new token
        processQueue(null, access_token);

        originalRequest.headers.Authorization = `Bearer ${access_token}`;
        return apiClient(originalRequest);
      } catch (refreshError) {
        // Refresh failed — notify user and redirect
        processQueue(refreshError, null);

        sessionStorage.removeItem('access_token');
        sessionStorage.removeItem('refresh_token');
        useAuthStore.getState().logout();

        // Show session expired toast (import toast lazily to avoid circular deps)
        import('sonner').then(({ toast }) => {
          toast.error('Session expired', { description: 'Please log in again' });
        }).catch(() => {
          // Ignore dynamic import failure
        });

        // Small delay to allow toast to render
        setTimeout(() => {
          window.location.href = '/login';
        }, 500);

        return Promise.reject(refreshError);
      } finally {
        isRefreshing = false;
      }
    }

    return Promise.reject(error);
  }
);
