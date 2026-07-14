import { useEffect, useRef } from 'react';
import { apiClient } from '@/lib/api';
import { useAuthStore } from '@/store/auth';

const CHECK_INTERVAL = 60000;
const WARNING_BEFORE_EXPIRY = 5 * 60;
const REFRESH_BEFORE_EXPIRY = 60;
const IDLE_TIMEOUT_MINUTES = 30;
const IDLE_TIMEOUT_MS = IDLE_TIMEOUT_MINUTES * 60 * 1000;
const IDLE_WARNING_MS = 5 * 60 * 1000;

export const useTokenExpiration = () => {
  const logout = useAuthStore((state) => state.logout);
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const warningShown = useRef(false);
  const idleWarningShown = useRef(false);
  const lastActivityTime = useRef(Date.now());
  const idleTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const idleWarningRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!isAuthenticated) return;

    const checkExpiration = async () => {
      const expiresAtStr = sessionStorage.getItem('token_expires_at');
      const token = sessionStorage.getItem('access_token');

      if (!expiresAtStr || !token) {
        return;
      }

      const expiresAt = parseInt(expiresAtStr, 10);
      const now = Math.floor(Date.now() / 1000);
      const remainingSeconds = expiresAt - now;

      if (remainingSeconds <= 0) {
        warningShown.current = false;
        await handleExpired();
        return;
      }

      if (remainingSeconds <= WARNING_BEFORE_EXPIRY && !warningShown.current) {
        warningShown.current = true;
        const minutes = Math.ceil(remainingSeconds / 60);
        import('sonner').then(({ toast }) => {
          toast.warning('Session about to expire', {
            description: `Your session will expire in ${minutes} minute(s). Please save your work.`,
            duration: 10000,
          });
        }).catch(() => {});
      }

      if (remainingSeconds <= REFRESH_BEFORE_EXPIRY) {
        await handleRefresh();
      }
    };

    const handleRefresh = async () => {
      const refreshToken = sessionStorage.getItem('refresh_token');
      if (!refreshToken) {
        await handleExpired();
        return;
      }

      try {
        const response = await apiClient.post('/auth/refresh', {
          refresh_token: refreshToken,
        }, {
          timeout: 10000,
        });

        const { access_token, refresh_token } = response.data;
        sessionStorage.setItem('access_token', access_token);
        sessionStorage.setItem('refresh_token', refresh_token);

        try {
        const payload = access_token.split('.')[1];
          const decoded = atob(payload.replace(/-/g, '+').replace(/_/g, '/'));
          const parsed = JSON.parse(decoded);
          if (parsed?.exp) {
            sessionStorage.setItem('token_expires_at', parsed.exp.toString());
          }
        } catch {}

        warningShown.current = false;
        resetIdleTimer();
      } catch {
        await handleExpired();
      }
    };

    const handleExpired = async () => {
      logout();
      import('sonner').then(({ toast }) => {
        toast.error('Session expired', {
          description: 'Your session has expired. Please log in again.',
        });
      }).catch(() => {});

      setTimeout(() => {
        window.location.href = '/login';
      }, 500);
    };

    const handleIdleTimeout = async () => {
      logout();
      import('sonner').then(({ toast }) => {
        toast.error('Session timeout', {
          description: 'Your session has timed out due to inactivity. Please log in again.',
        });
      }).catch(() => {});

      setTimeout(() => {
        window.location.href = '/login';
      }, 500);
    };

    const resetIdleTimer = () => {
      lastActivityTime.current = Date.now();
      idleWarningShown.current = false;

      if (idleWarningRef.current) {
        clearTimeout(idleWarningRef.current);
        idleWarningRef.current = null;
      }

      if (idleTimeoutRef.current) {
        clearTimeout(idleTimeoutRef.current);
        idleTimeoutRef.current = null;
      }

      idleWarningRef.current = setTimeout(() => {
        import('sonner').then(({ toast }) => {
          toast.warning('Session will timeout soon', {
            description: 'You have been inactive for a while. Your session will expire in 5 minutes.',
            duration: 10000,
          });
        }).catch(() => {});
        idleWarningShown.current = true;
      }, IDLE_TIMEOUT_MS - IDLE_WARNING_MS);

      idleTimeoutRef.current = setTimeout(() => {
        handleIdleTimeout();
      }, IDLE_TIMEOUT_MS);
    };

    checkExpiration();
    const interval = setInterval(checkExpiration, CHECK_INTERVAL);

    resetIdleTimer();

    const activityEvents = ['mousedown', 'mousemove', 'keydown', 'scroll', 'touchstart'];
    activityEvents.forEach((event) => {
      window.addEventListener(event, resetIdleTimer, { passive: true });
    });

    return () => {
      clearInterval(interval);
      if (idleTimeoutRef.current) {
        clearTimeout(idleTimeoutRef.current);
      }
      if (idleWarningRef.current) {
        clearTimeout(idleWarningRef.current);
      }
      activityEvents.forEach((event) => {
        window.removeEventListener(event, resetIdleTimer);
      });
    };
  }, [isAuthenticated, logout]);
};