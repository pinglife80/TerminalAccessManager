import React, { useState } from 'react';
import { NavLink } from 'react-router-dom';
import {
  Shield,
  LayoutDashboard,
  Network,
  List,
  ShieldOff,
  FileText,
  Users,
  Database,
  LogOut,
  UserCircle,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '@/store/auth';
import { useBrandingStore } from '@/store/branding';
import { NAV_ITEMS } from '@/lib/constants';
import { pagePreloadMap } from '@/App';

// Map icon names from NAV_ITEMS to Lucide components
const iconMap: Record<string, React.ComponentType<{ className?: string }>> = {
  LayoutDashboard,
  Network,
  List,
  ShieldOff,
  FileText,
  Database,
  Users,
};

// Map NAV_ITEMS label to i18n key
const navLabelKeyMap: Record<string, string> = {
  'Dashboard': 'nav.dashboard',
  'Terminals': 'nav.terminals',
  'Whitelist': 'nav.whitelist',
  'Blocked': 'nav.blacklist',
  'Audit Logs': 'nav.auditLogs',
  'Data Sources': 'nav.dataSources',
  'Users': 'nav.users',
};

const Sidebar: React.FC = () => {
  const { t } = useTranslation();
  const { user, logout } = useAuthStore();
  const { appShortName, appSubtitle } = useBrandingStore();
  const [collapsed, setCollapsed] = useState(false);

  const navItems = NAV_ITEMS
    .filter((item) => !item.adminOnly || user?.is_superuser)
    .map((item) => ({
      path: item.path,
      label: navLabelKeyMap[item.label] ? t(navLabelKeyMap[item.label]) : item.label,
      icon: iconMap[item.iconName] || Shield,
    }));

  const handleNavHover = (path: string) => {
    pagePreloadMap[path]?.();
  };

  return (
    <aside
      className={`${
        collapsed ? 'w-[4.5rem]' : 'w-64'
      } bg-gray-900 text-white flex flex-col h-full transition-all duration-300 ease-in-out relative`}
    >
      {/* Logo / Brand */}
      <div className={`p-4 border-b border-gray-800 ${collapsed ? 'px-3' : ''}`}>
        <div className={`flex items-center h-10 ${collapsed ? 'justify-center' : 'space-x-3'}`}>
          <Shield className="h-8 w-8 flex-shrink-0 text-blue-500" />
          {!collapsed && (
            <div className="overflow-hidden">
              <span className="text-lg font-bold whitespace-nowrap">{appShortName}</span>
              <span className="block text-xs text-gray-400 whitespace-nowrap">{appSubtitle}</span>
            </div>
          )}
        </div>
      </div>

      {/* Collapse Toggle Button */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="absolute -right-3 top-20 z-10 w-6 h-6 bg-gray-700 hover:bg-gray-600 border border-gray-600 rounded-full flex items-center justify-center text-gray-300 hover:text-white shadow-md transition-colors"
        title={collapsed ? t('sidebar.expandSidebar') : t('sidebar.collapseSidebar')}
        aria-label={collapsed ? t('sidebar.expandSidebar') : t('sidebar.collapseSidebar')}
      >
        {collapsed ? (
          <ChevronRight className="h-3.5 w-3.5" />
        ) : (
          <ChevronLeft className="h-3.5 w-3.5" />
        )}
      </button>

      {/* Navigation */}
      <nav className="flex-1 py-4 overflow-y-auto overflow-x-hidden">
        <ul className="space-y-1 px-3">
          {navItems.map((item) => (
            <li key={item.path}>
              <NavLink
                to={item.path}
                onMouseEnter={() => handleNavHover(item.path)}
                className={({ isActive }) =>
                  `flex items-center ${collapsed ? 'justify-center' : 'space-x-3'} px-3 py-2.5 rounded-lg transition-colors group ${
                    isActive
                      ? 'bg-blue-600 text-white'
                      : 'text-gray-300 hover:bg-gray-800 hover:text-white'
                  }`
                }
                title={collapsed ? item.label : undefined}
              >
                <item.icon className="h-5 w-5 flex-shrink-0" />
                {!collapsed && (
                  <span className="text-sm font-medium whitespace-nowrap">{item.label}</span>
                )}
                {/* Tooltip for collapsed state */}
                {collapsed && (
                  <div className="absolute left-full ml-2 px-2 py-1 bg-gray-800 text-white text-xs rounded-md opacity-0 group-hover:opacity-100 pointer-events-none whitespace-nowrap z-50 shadow-lg transition-opacity">
                    {item.label}
                  </div>
                )}
              </NavLink>
            </li>
          ))}
        </ul>
      </nav>

      {/* User info */}
      <div className={`p-3 border-t border-gray-800 ${collapsed ? 'px-2' : ''}`}>
        <div className={`flex items-center ${collapsed ? 'justify-center' : 'justify-between'}`}>
          <div className={`flex items-center ${collapsed ? '' : 'space-x-3'}`}>
            <div className="h-9 w-9 rounded-full bg-blue-600 flex items-center justify-center flex-shrink-0">
              <span className="text-sm font-medium">
                {user?.username?.charAt(0).toUpperCase()}
              </span>
            </div>
            {!collapsed && (
              <div className="overflow-hidden">
                <p className="text-sm font-medium truncate">{user?.username}</p>
                <p className="text-xs text-gray-400 truncate">
                  {user?.is_superuser ? t('users.administrator') : t('users.userRole')}
                </p>
              </div>
            )}
          </div>
          {!collapsed && (
            <div className="flex items-center gap-1">
              <NavLink
                to="/profile"
                className="p-2 text-gray-400 hover:text-white hover:bg-gray-800 rounded-lg transition-colors flex-shrink-0"
                title={t('sidebar.profile')}
              >
                <UserCircle className="h-4 w-4" />
              </NavLink>
              <button
                onClick={logout}
                className="p-2 text-gray-400 hover:text-white hover:bg-gray-800 rounded-lg transition-colors flex-shrink-0"
                title={t('nav.logout')}
              >
                <LogOut className="h-4 w-4" />
              </button>
            </div>
          )}
        </div>
        {collapsed && (
          <div className="mt-2 flex items-center justify-center gap-1">
            <button
              onClick={logout}
              className="p-2 text-gray-400 hover:text-white hover:bg-gray-800 rounded-lg transition-colors"
              title={t('nav.logout')}
            >
              <LogOut className="h-4 w-4" />
            </button>
          </div>
        )}
      </div>
    </aside>
  );
};

export default Sidebar;
