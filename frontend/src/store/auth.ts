import { create } from 'zustand';
import { apiClient } from '@/lib/api';

interface User {
  id: number;
  username: string;
  email: string | null;
  is_active: boolean;
  is_superuser: boolean;
  roles: string[];
  permissions: string[];
}

interface AuthState {
  user: User | null;
  isAuthenticated: boolean;
  isInitializing: boolean;
  login: (user: User, accessToken: string, refreshToken: string) => void;
  logout: () => void;
  setUser: (user: User) => void;
  initializeAuth: () => Promise<void>;
}

const AUTH_TIMEOUT = 10000; // 10 seconds

export const useAuthStore = create<AuthState>()((set) => ({
  user: null,
  isAuthenticated: false,
  isInitializing: true,
  login: (user, accessToken, refreshToken) => {
    sessionStorage.setItem('access_token', accessToken);
    sessionStorage.setItem('refresh_token', refreshToken);
    set({ user, isAuthenticated: true });
  },
  logout: () => {
    sessionStorage.removeItem('access_token');
    sessionStorage.removeItem('refresh_token');
    set({ user: null, isAuthenticated: false });
  },
  setUser: (user) => set({ user }),
  initializeAuth: async () => {
    const token = sessionStorage.getItem('access_token');
    if (!token) {
      set({ isInitializing: false });
      return;
    }

    try {
      const response = await apiClient.get('/auth/me', {
        headers: { Authorization: `Bearer ${token}` },
        timeout: AUTH_TIMEOUT,
      });
      set({ user: response.data, isAuthenticated: true, isInitializing: false });
    } catch {
      // Token invalid or expired, try refresh
      const refreshToken = sessionStorage.getItem('refresh_token');
      if (refreshToken) {
        try {
          const response = await apiClient.post('/auth/refresh', {
            refresh_token: refreshToken,
          }, {
            timeout: AUTH_TIMEOUT,
          });
          const { access_token, refresh_token: new_refresh } = response.data;
          sessionStorage.setItem('access_token', access_token);
          sessionStorage.setItem('refresh_token', new_refresh);

          // Fetch user info with new token
          const meResponse = await apiClient.get('/auth/me', {
            headers: { Authorization: `Bearer ${access_token}` },
            timeout: AUTH_TIMEOUT,
          });
          set({ user: meResponse.data, isAuthenticated: true, isInitializing: false });
        } catch {
          // Refresh also failed, clear session
          sessionStorage.removeItem('access_token');
          sessionStorage.removeItem('refresh_token');
          set({ user: null, isAuthenticated: false, isInitializing: false });
        }
      } else {
        sessionStorage.removeItem('access_token');
        set({ user: null, isAuthenticated: false, isInitializing: false });
      }
    }
  },
}));
