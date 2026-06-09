import { create } from 'zustand';

interface User {
  id: number;
  username: string;
  email: string | null;
  is_active: boolean;
  is_superuser: boolean;
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
      const { default: axios } = await import('axios');
      const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1';
      const response = await axios.get(`${API_BASE_URL}/auth/me`, {
        headers: { Authorization: `Bearer ${token}` },
        timeout: AUTH_TIMEOUT,
      });
      set({ user: response.data, isAuthenticated: true, isInitializing: false });
    } catch {
      // Token invalid or expired, try refresh
      const refreshToken = sessionStorage.getItem('refresh_token');
      if (refreshToken) {
        try {
          const { default: axios } = await import('axios');
          const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || '/api/v1';
          const response = await axios.post(`${API_BASE_URL}/auth/refresh`, {
            refresh_token: refreshToken,
          }, {
            timeout: AUTH_TIMEOUT,
          });
          const { access_token, refresh_token: new_refresh } = response.data;
          sessionStorage.setItem('access_token', access_token);
          sessionStorage.setItem('refresh_token', new_refresh);

          // Fetch user info with new token
          const meResponse = await axios.get(`${API_BASE_URL}/auth/me`, {
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
