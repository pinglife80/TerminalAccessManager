import { useEffect, useRef, useState, useCallback } from 'react';
import { apiClient } from '@/lib/api';
import { useAuthStore } from '@/store/auth';

const CHECK_INTERVAL = 60000;
const WARNING_BEFORE_EXPIRY = 5 * 60;
const REFRESH_BEFORE_EXPIRY = 60;
const IDLE_TIMEOUT_MINUTES = 30;
const IDLE_TIMEOUT_MS = IDLE_TIMEOUT_MINUTES * 60 * 1000;
const IDLE_WARNING_MS = 5 * 60 * 1000;

export interface SessionWarning {
  show: boolean;
  type: 'expiry' | 'idle';
  countdown: number;
  onContinue: () => void;
  onLogout: () => void;
  onClose: () => void;
}

export const useTokenExpiration = (): SessionWarning => {
  const logout = useAuthStore((state) => state.logout);
  const isAuthenticated = useAuthStore((state) => state.isAuthenticated);
  const warningShown = useRef(false);
  const idleWarningShown = useRef(false);
  const lastActivityTime = useRef(Date.now());
  const idleTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const idleWarningRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const [warning, setWarning] = useState<{ show: boolean; type: 'expiry' | 'idle'; countdown: number }>({
    show: false,
    type: 'expiry',
    countdown: 0,
  });

  const dismissWarning = useCallback(() => {
    setWarning({ show: false, type: 'expiry', countdown: 0 });
  }, []);

  const performLogout = useCallback(() => {
    dismissWarning();
    logout();
    // Defer the hard redirect to the next tick so React flushes the logout
    // state update (isAuthenticated -> false) before navigation. Without this,
    // the synchronous location change can race with React's re-render, leaving
    // the dialog dismissed but the page still on the authenticated route.
    window.setTimeout(() => {
      window.location.replace('/login');
    }, 0);
  }, [dismissWarning, logout]);

  const resetIdleTimer = useCallback(() => {
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
      idleWarningShown.current = true;
      setWarning({ show: true, type: 'idle', countdown: Math.floor(IDLE_WARNING_MS / 1000) });
    }, IDLE_TIMEOUT_MS - IDLE_WARNING_MS);

    idleTimeoutRef.current = setTimeout(() => {
      performLogout();
    }, IDLE_TIMEOUT_MS);
  }, [performLogout]);

  const handleExpired = useCallback(() => {
    dismissWarning();
    logout();
    import('sonner').then(({ toast }) => {
      toast.error('Session expired', {
        description: 'Your session has expired. Please log in again.',
      });
    }).catch(() => {});

    setTimeout(() => {
      window.location.replace('/login');
    }, 500);
  }, [dismissWarning, logout]);

  const handleRefresh = useCallback(async () => {
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
      // Auto-refresh (sliding session) only dismisses the expiry warning. It must
      // NOT dismiss an idle-timeout warning nor reset the idle timer: a token
      // refresh is not user activity, so an idle user must still be logged out.
      if (!idleWarningShown.current) {
        dismissWarning();
      }
    } catch {
      await handleExpired();
    }
  }, [dismissWarning, handleExpired]);

  useEffect(() => {
    if (!isAuthenticated) return;

    const checkExpiration = async () => {
      const expiresAtStr = sessionStorage.getItem('token_expires_at');
      const token = sessionStorage.getItem('access_token');

      if (!expiresAtStr || !token) {
        // Missing expiry info or token => treat as expired instead of silently returning
        await handleExpired();
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
        setWarning({ show: true, type: 'expiry', countdown: remainingSeconds });
      }

      if (remainingSeconds <= REFRESH_BEFORE_EXPIRY) {
        await handleRefresh();
      }
    };

    checkExpiration();
    const interval = setInterval(checkExpiration, CHECK_INTERVAL);

    resetIdleTimer();

    const activityEvents = ['mousedown', 'mousemove', 'keydown', 'scroll', 'touchstart'];
    const onActivity = () => resetIdleTimer();
    activityEvents.forEach((event) => {
      window.addEventListener(event, onActivity, { passive: true });
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
        window.removeEventListener(event, onActivity);
      });
    };
  }, [isAuthenticated, handleExpired, handleRefresh, resetIdleTimer]);

  // Countdown effect for the warning dialog: auto-logout when it reaches zero
  useEffect(() => {
    if (!warning.show) return;

    if (warning.countdown <= 0) {
      performLogout();
      return;
    }

    const timer = setTimeout(() => {
      setWarning((prev) => (prev.show ? { ...prev, countdown: prev.countdown - 1 } : prev));
    }, 1000);

    return () => clearTimeout(timer);
  }, [warning, performLogout]);

  const onContinue = useCallback(() => {
    resetIdleTimer();
    dismissWarning();
    if (warning.type === 'expiry') {
      handleRefresh();
    }
  }, [resetIdleTimer, dismissWarning, warning.type, handleRefresh]);

  const onClose = useCallback(() => {
    dismissWarning();
  }, [dismissWarning]);

  return {
    show: warning.show,
    type: warning.type,
    countdown: warning.countdown,
    onContinue,
    onLogout: performLogout,
    onClose,
  };
};