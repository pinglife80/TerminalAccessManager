import React, { useState } from 'react';
import { NavLink } from 'react-router-dom';
import {
  Shield,
  LayoutDashboard,
  Network,
  List,
  ShieldOff,
  FileText,
  LogOut,
  ChevronLeft,
  ChevronRight,
} from 'lucide-react';
import { useAuthStore } from '@/store/auth';
import branding from '@/config/branding';

// Map icon names from branding config to Lucide components
const iconMap: Record<string, React.ComponentType<{ className?: string }>> = {
  Shield,
  LayoutDashboard,
  Network,
  List,
  ShieldOff,
  FileText,
};

const Sidebar: React.FC = () => {
  const { user, logout } = useAuthStore();
  const [collapsed, setCollapsed] = useState(false);

  const navItems = [
    { path: '/dashboard', label: 'Dashboard', icon: LayoutDashboard },
    { path: '/mac-addresses', label: 'Terminals', icon: Network },
    { path: '/whitelist', label: 'Whitelist', icon: List },
    { path: '/blacklist', label: 'Blocked', icon: ShieldOff },
    { path: '/audit-logs', label: 'Audit Logs', icon: FileText },
  ];

  return (
    <aside
      className={`${
        collapsed ? 'w-[4.5rem]' : 'w-64'
      } bg-gray-900 text-white flex flex-col h-full transition-all duration-300 ease-in-out relative`}
    >
      {/* Logo / Brand */}
      <div className={`p-4 border-b border-gray-800 ${collapsed ? 'px-3' : ''}`}>
        <div className={`flex items-center ${collapsed ? 'justify-center' : 'space-x-3'}`}>
          {branding.logo.type === 'image' ? (
            <img src={branding.logo.path} alt={branding.appName} className="h-8 w-8 flex-shrink-0" />
          ) : (
            (() => {
              const IconComponent = iconMap[branding.logo.name] || Shield;
              return <IconComponent className={`h-8 w-8 flex-shrink-0 ${branding.logo.className}`} />;
            })()
          )}
          {!collapsed && (
            <div className="overflow-hidden">
              <span className="text-lg font-bold whitespace-nowrap">{branding.appShortName}</span>
              <span className="block text-xs text-gray-400 whitespace-nowrap">{branding.appSubtitle}</span>
            </div>
          )}
        </div>
      </div>

      {/* Collapse Toggle Button */}
      <button
        onClick={() => setCollapsed(!collapsed)}
        className="absolute -right-3 top-20 z-10 w-6 h-6 bg-gray-700 hover:bg-gray-600 border border-gray-600 rounded-full flex items-center justify-center text-gray-300 hover:text-white shadow-md transition-colors"
        title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
        aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'}
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
                  {user?.is_superuser ? 'Administrator' : 'User'}
                </p>
              </div>
            )}
          </div>
          {!collapsed && (
            <button
              onClick={logout}
              className="p-2 text-gray-400 hover:text-white hover:bg-gray-800 rounded-lg transition-colors flex-shrink-0"
              title="Logout"
            >
              <LogOut className="h-4 w-4" />
            </button>
          )}
        </div>
        {collapsed && (
          <button
            onClick={logout}
            className="mt-2 p-2 text-gray-400 hover:text-white hover:bg-gray-800 rounded-lg transition-colors w-full flex items-center justify-center"
            title="Logout"
          >
            <LogOut className="h-4 w-4" />
          </button>
        )}
      </div>
    </aside>
  );
};

export default Sidebar;
