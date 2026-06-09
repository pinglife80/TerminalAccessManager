import { useAuthStore } from '@/store/auth';

export function usePermission() {
  const { user } = useAuthStore();

  const hasPermission = (code: string): boolean => {
    if (user?.is_superuser) return true;
    return user?.permissions?.includes(code) ?? false;
  };

  const hasAnyPermission = (codes: string[]): boolean => {
    if (user?.is_superuser) return true;
    return codes.some((code) => user?.permissions?.includes(code));
  };

  const hasAllPermissions = (codes: string[]): boolean => {
    if (user?.is_superuser) return true;
    return codes.every((code) => user?.permissions?.includes(code));
  };

  const hasRole = (roleName: string): boolean => {
    if (user?.is_superuser) return true;
    return user?.roles?.includes(roleName) ?? false;
  };

  return { hasPermission, hasAnyPermission, hasAllPermissions, hasRole };
}
