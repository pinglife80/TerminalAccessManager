import React from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuthStore } from '@/store/auth';

interface ProtectedRouteProps {
  children: React.ReactNode;
  requireSuperuser?: boolean;
  requiredPermission?: string;
  /** Multiple permissions where having any one is sufficient for access */
  requiredAnyPermissions?: string[];
}

const ProtectedRoute: React.FC<ProtectedRouteProps> = ({
  children,
  requireSuperuser = false,
  requiredPermission,
  requiredAnyPermissions,
}) => {
  const { isAuthenticated, user, isInitializing } = useAuthStore();
  const location = useLocation();

  if (isInitializing) {
    return (
      <div className="h-screen w-screen flex items-center justify-center bg-background">
        <div className="h-8 w-8 border-2 border-blue-600 border-t-transparent rounded-full animate-spin" />
      </div>
    );
  }

  if (!isAuthenticated) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  // Superuser check (backward compatible)
  if (requireSuperuser && !user?.is_superuser) {
    return <Navigate to="/403" state={{ from: location }} replace />;
  }

  // Single permission check
  if (requiredPermission) {
    const hasPermission = user?.is_superuser || user?.permissions?.includes(requiredPermission);
    if (!hasPermission) {
      return <Navigate to="/403" state={{ from: location }} replace />;
    }
  }

  // Multiple permissions check (any one is sufficient)
  if (requiredAnyPermissions && requiredAnyPermissions.length > 0) {
    const hasAnyPermission =
      user?.is_superuser || requiredAnyPermissions.some((p) => user?.permissions?.includes(p));
    if (!hasAnyPermission) {
      return <Navigate to="/403" state={{ from: location }} replace />;
    }
  }

  return <>{children}</>;
};

export default ProtectedRoute;
