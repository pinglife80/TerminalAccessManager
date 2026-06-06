import React, { useEffect } from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { Toaster } from 'sonner';
import Login from './pages/Login';
import Dashboard from './pages/Dashboard';
import MacAddresses from './pages/MacAddresses';
import Whitelist from './pages/Whitelist';
import Blacklist from './pages/Blacklist';
import AuditLogs from './pages/AuditLogs';
import ProtectedRoute from './components/ProtectedRoute';
import Layout from './components/Layout';
import ErrorBoundary from './components/ErrorBoundary';
import { apiClient } from './lib/api';
import branding from './config/branding';

const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      retry: 1,
      refetchOnWindowFocus: false,
    },
  },
});

const App: React.FC = () => {
  // Set document title from branding config
  useEffect(() => {
    document.title = branding.title;
    // Update favicon if configured
    const link = document.querySelector("link[rel~='icon']") as HTMLLinkElement;
    if (link) {
      link.href = branding.favicon;
    }
  }, []);
  useEffect(() => {
    const token = sessionStorage.getItem('access_token');
    if (token) {
      queryClient.prefetchQuery({
        queryKey: ['macAddresses'],
        queryFn: async () => {
          const response = await apiClient.get('/mac/search');
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
  }, []);

  return (
    <QueryClientProvider client={queryClient}>
      <ErrorBoundary>
        <BrowserRouter>
          <Routes>
            <Route path="/login" element={<Login />} />
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
              <Route path="mac-addresses" element={<MacAddresses />} />
              <Route path="whitelist" element={<Whitelist />} />
              <Route path="blacklist" element={<Blacklist />} />
              <Route path="audit-logs" element={<AuditLogs />} />
            </Route>
          </Routes>
        </BrowserRouter>
        <Toaster position="top-right" richColors />
      </ErrorBoundary>
    </QueryClientProvider>
  );
};

export default App;
