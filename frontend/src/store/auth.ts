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
  login: (user: User, accessToken: string, refreshToken: string) => void;
  logout: () => void;
  setUser: (user: User) => void;
}

export const useAuthStore = create<AuthState>()((set) => ({
  user: null,
  isAuthenticated: false,
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
}));
