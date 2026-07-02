import '@/i18n';
import React, { useEffect, Suspense, lazy } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from 'sonner';
import ProtectedRoute from './components/ProtectedRoute';
import Layout from './components/Layout';
import ErrorBoundary from './components/ErrorBoundary';
import { logger } from './lib/logger';

// Lazy-loaded pages for code splitting
const Login = lazy(() => import('./pages/Login'));
const PasswordReset = lazy(() => import('./pages/PasswordReset'));
const Dashboard = lazy(() => import('./pages/Dashboard'));
const Terminals = lazy(() => import('./pages/Terminals'));
const Whitelist = lazy(() => import('./pages/Whitelist'));
const Blacklist = lazy(() => import('./pages/Blacklist'));
const DataSources = lazy(() => import('./pages/DataSources'));
const AuditLogs = lazy(() => import('./pages/AuditLogs'));
const Profile = lazy(() => import('./pages/Profile'));
const Users = lazy(() => import('./pages/Users'));
const Roles = lazy(() => import('./pages/Roles'));
const AuthProviders = lazy(() => import('./pages/AuthProviders'));
const Backup = lazy(() => import('./pages/Backup'));
const Notifications = lazy(() => import('./pages/Notifications'));
const SystemSettings = lazy(() => import('./pages/SystemSettings'));
const GeneralSettings = lazy(() => import('./pages/GeneralSettings'));
const Forbidden = lazy(() => import('./pages/Forbidden'));

// Preload page components on hover to eliminate lazy-load flash
export const pagePreloadMap: Record<string, () => Promise<unknown>> = {
  '/dashboard': () => import('./pages/Dashboard'),
  '/terminals': () => import('./pages/Terminals'),
  '/whitelist': () => import('./pages/Whitelist'),
  '/blacklist': () => import('./pages/Blacklist'),
  '/data-sources': () => import('./pages/DataSources'),
  '/audit-logs': () => import('./pages/AuditLogs'),
  '/profile': () => import('./pages/Profile'),
  '/users': () => import('./pages/Users'),
  '/roles': () => import('./pages/Roles'),
  '/auth-providers': () => import('./pages/AuthProviders'),
  '/backup': () => import('./pages/Backup'),
  '/notifications': () => import('./pages/Notifications'),
  '/system-settings': () => import('./pages/SystemSettings'),
  '/general-settings': () => import('./pages/GeneralSettings'),
};
import { apiClient } from './lib/api';
import { useAuthStore } from './store/auth';
import { useThemeStore } from './store/theme';
import branding from './config/branding';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: (count, error: unknown) => {
        // Don't retry on 401 — the interceptor handles token refresh
        const status = (error as { response?: { status?: number } })?.response?.status;
        if (status === 401) return false;
        return count < 1;
      },
      refetchOnWindowFocus: false,
      staleTime: 30 * 1000,
    },
  },
});

const App: React.FC = () => {
  const { initializeAuth, isAuthenticated, isInitializing } = useAuthStore();
  const { initTheme } = useThemeStore();

  useEffect(() => {
    document.title = branding.title;
    const link = document.querySelector("link[rel~='icon']") as HTMLLinkElement;
    if (link) {
      link.href = branding.favicon;
    }
  }, []);

  useEffect(() => {
    initializeAuth();
    initTheme();

    // Register global error listeners
    const handleUnhandledError = (event: ErrorEvent) => {
      logger.error('Global', `Uncaught error: ${event.message}`, {
        filename: event.filename,
        lineno: event.lineno,
        colno: event.colno,
      });
    };

    const handleUnhandledRejection = (event: PromiseRejectionEvent) => {
      logger.error('Global', `Unhandled promise rejection: ${String(event.reason)}`);
    };

    window.addEventListener('error', handleUnhandledError);
    window.addEventListener('unhandledrejection', handleUnhandledRejection);

    return () => {
      window.removeEventListener('error', handleUnhandledError);
      window.removeEventListener('unhandledrejection', handleUnhandledRejection);
    };
  }, [initializeAuth, initTheme]);

  useEffect(() => {
    if (isAuthenticated) {
      queryClient.prefetchQuery({
        queryKey: ['terminals'],
        queryFn: async () => {
          const response = await apiClient.get('/terminals/search');
          return response.data;
        },
      });

      queryClient.prefetchQuery({
        queryKey: ['whitelist'],
        queryFn: async () => {
          const response = await apiClient.get('/whitelist/');
          return response.data;
        },
      });
    }
  }, [isAuthenticated]);

  if (isInitializing) {
    return (
      <div className="h-screen w-screen flex items-center justify-center bg-background">
        <div className="flex flex-col items-center space-y-3">
          <div className="h-8 w-8 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
          <span className="text-sm text-muted-foreground">Loading...</span>
        </div>
      </div>
    );
  }

  return (
    <QueryClientProvider client={queryClient}>
      <ErrorBoundary>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={
              <Suspense fallback={
                <div className="h-screen w-screen flex items-center justify-center bg-background">
                  <div className="h-8 w-8 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
                </div>
              }>
                <Login />
              </Suspense>
            } />
            <Route path="/password-reset" element={
              <Suspense fallback={
                <div className="h-screen w-screen flex items-center justify-center bg-background">
                  <div className="h-8 w-8 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
                </div>
              }>
                <PasswordReset />
              </Suspense>
            } />
            <Route path="/403" element={
              <Suspense fallback={
                <div className="h-screen w-screen flex items-center justify-center bg-background">
                  <div className="h-8 w-8 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
                </div>
              }>
                <Forbidden />
              </Suspense>
            } />
            <Route
              path="/"
              element={
                <ProtectedRoute>
                  <Layout />
                </ProtectedRoute>
              }
            >
              <Route index element={<Navigate to="/dashboard" replace />} />
              <Route path="dashboard" element={<Dashboard />} />
              <Route path="terminals" element={<ProtectedRoute requiredPermission="terminal:read"><Terminals /></ProtectedRoute>} />
              <Route path="whitelist" element={<ProtectedRoute requiredPermission="whitelist:read"><Whitelist /></ProtectedRoute>} />
              <Route path="blacklist" element={<ProtectedRoute requiredPermission="blacklist:read"><Blacklist /></ProtectedRoute>} />
              <Route path="data-sources" element={<ProtectedRoute requiredPermission="datasource:read"><DataSources /></ProtectedRoute>} />
              <Route path="audit-logs" element={<ProtectedRoute requiredPermission="audit:read"><AuditLogs /></ProtectedRoute>} />
              <Route path="system-settings" element={<ProtectedRoute requiredPermission="system:manage"><SystemSettings /></ProtectedRoute>} />
              <Route path="general-settings" element={<ProtectedRoute requiredPermission="system:manage"><GeneralSettings /></ProtectedRoute>} />
              <Route path="auth-providers" element={<ProtectedRoute requiredPermission="system:manage"><AuthProviders /></ProtectedRoute>} />
              <Route path="backup" element={<ProtectedRoute requiredPermission="system:manage"><Backup /></ProtectedRoute>} />
              <Route path="notifications" element={<ProtectedRoute requiredPermission="system:manage"><Notifications /></ProtectedRoute>} />
              <Route path="profile" element={<Profile />} />
              <Route path="users" element={<ProtectedRoute requiredPermission="user:read"><Users /></ProtectedRoute>} />
              <Route path="roles" element={<ProtectedRoute requiredPermission="role:read"><Roles /></ProtectedRoute>} />
            </Route>
          </Routes>
        </BrowserRouter>
        <Toaster position="top-right" richColors />
      </ErrorBoundary>
    </QueryClientProvider>
  );
};

export default App;
