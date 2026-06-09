import React, { useEffect, Suspense } from 'react';
import { Outlet } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import Sidebar from './Sidebar';
import HeaderControls from './HeaderControls';
import { useBrandingStore } from '@/store/branding';
import { useNetworkStatus } from '@/hooks/useNetworkStatus';

const Layout: React.FC = () => {
  const { t } = useTranslation();
  const { footerCopyright, footerIcpNumber, footerIcpUrl, loadFromBackend, isLoaded } = useBrandingStore();
  const { isOnline, isSlowConnection } = useNetworkStatus();

  useEffect(() => {
    if (!isLoaded) {
      loadFromBackend();
    }
  }, [isLoaded, loadFromBackend]);

  const copyrightText = footerCopyright.replace('{year}', String(new Date().getFullYear()));

  return (
    <div className="flex h-screen bg-background">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Top bar with controls */}
        <div className="flex-shrink-0 flex items-center justify-end px-4 py-2 bg-card border-b border-border">
          <HeaderControls />
        </div>
        <main className="flex-1 overflow-auto">
          {!isOnline && (
            <div className="bg-red-500 text-white text-center py-2 text-sm font-medium">
              {t('layout.offlineWarning')}
            </div>
          )}
          {isOnline && isSlowConnection && (
            <div className="bg-yellow-500 text-white text-center py-2 text-sm font-medium">
              {t('layout.slowConnectionWarning')}
            </div>
          )}
          <Suspense fallback={
            <div className="flex items-center justify-center h-full min-h-[50vh]">
              <div className="h-6 w-6 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
            </div>
          }>
            <Outlet />
          </Suspense>
        </main>
        <footer className="flex-shrink-0 border-t border-border bg-card px-6 py-3">
          <div className="flex flex-col sm:flex-row items-center justify-between gap-1 text-xs text-muted-foreground">
            <div className="flex items-center gap-3">
              <span>{copyrightText}</span>
            </div>
            <div className="flex items-center gap-3">
              {footerIcpNumber && (
                <a
                  href={footerIcpUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:text-foreground transition-colors"
                >
                  {footerIcpNumber}
                </a>
              )}
            </div>
          </div>
        </footer>
      </div>
    </div>
  );
};

export default Layout;
