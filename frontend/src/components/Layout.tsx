import React from 'react';
import { Outlet } from 'react-router-dom';
import Sidebar from './Sidebar';
import branding from '@/config/branding';

const Layout: React.FC = () => {
  const copyrightText = branding.footer.copyright.replace('{year}', String(new Date().getFullYear()));

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
              <span className="hidden sm:inline">|</span>
              <span className="hidden sm:inline">{branding.version}</span>
            </div>
            <div className="flex items-center gap-3">
              {branding.footer.icpNumber && (
                <a
                  href={branding.footer.icpUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:text-gray-600 transition-colors"
                >
                  {branding.footer.icpNumber}
                </a>
              )}
              {branding.footer.links.map((link, index) => (
                <a
                  key={index}
                  href={link.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="hover:text-gray-600 transition-colors"
                >
                  {link.label}
                </a>
              ))}
            </div>
          </div>
        </footer>
      </div>
    </div>
  );
};

export default Layout;
