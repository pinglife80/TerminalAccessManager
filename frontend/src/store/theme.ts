import { create } from 'zustand';

type Theme = 'light' | 'dark' | 'system';

interface ThemeState {
  theme: Theme;
  resolvedTheme: 'light' | 'dark';
  setTheme: (theme: Theme) => void;
  initTheme: () => void;
}

const getSystemTheme = (): 'light' | 'dark' => {
  if (typeof window !== 'undefined' && window.matchMedia('(prefers-color-scheme: dark)').matches) {
    return 'dark';
  }
  return 'light';
};

const applyTheme = (theme: Theme) => {
  const resolved = theme === 'system' ? getSystemTheme() : theme;
  const root = document.documentElement;
  if (resolved === 'dark') {
    root.classList.add('dark');
  } else {
    root.classList.remove('dark');
  }
  return resolved;
};

export const useThemeStore = create<ThemeState>()((set) => ({
  theme: 'light',
  resolvedTheme: 'light',
  setTheme: (theme) => {
    localStorage.setItem('tam-theme', theme);
    const resolved = applyTheme(theme);
    set({ theme, resolvedTheme: resolved });
  },
  initTheme: () => {
    const saved = (localStorage.getItem('tam-theme') as Theme) || 'light';
    const resolved = applyTheme(saved);
    set({ theme: saved, resolvedTheme: resolved });

    // Listen for system theme changes when using 'system' mode
    if (saved === 'system') {
      const mq = window.matchMedia('(prefers-color-scheme: dark)');
      const handler = () => {
        const resolved = applyTheme('system');
        set({ resolvedTheme: resolved });
      };
      mq.addEventListener('change', handler);
    }
  },
}));
