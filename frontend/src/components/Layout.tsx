import React, { useEffect } from 'react';
import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';
import { useBrandingStore } from '@/store/branding';

const Layout: React.FC = () => {
  const { footerCopyright, footerIcpNumber, footerIcpUrl, loadFromBackend, isLoaded } = useBrandingStore();

  useEffect(() => {
    if (!isLoaded) {
      loadFromBackend();
    }
  }, [isLoaded, loadFromBackend]);

  const copyrightText = footerCopyright.replace('{year}', String(new Date().getFullYear()));

  return (
    <div className="flex h-screen bg-gray-100">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <main className="flex-1 overflow-auto">
          <Outlet />
        </main>
        <footer className="flex-shrink-0 border-t border-gray-200 bg-white px-6 py-3">
          <div className="flex flex-col sm:flex-row items-center justify-between gap-1 text-xs text-gray-400">
            <div className="flex items-center gap-3">
              <span>{copyrightText}</span>
            </div>
            <div className="flex items-center gap-3">
              {footerIcpNumber && (
                <a
                  href={footerIcpUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:text-gray-600 transition-colors"
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
