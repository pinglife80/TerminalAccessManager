import { describe, it, expect, beforeEach } from 'vitest'
import { usePermission } from '../usePermission'
import { useAuthStore } from '@/store/auth'

describe('usePermission', () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: null,
      isAuthenticated: false,
      isInitializing: true,
    })
  })

  describe('hasPermission', () => {
    it('should return true for superuser regardless of permission', () => {
      useAuthStore.setState({
        user: {
          id: 1,
          username: 'admin',
          email: null,
          is_active: true,
          is_superuser: true,
          roles: ['superadmin'],
          permissions: [],
        },
        isAuthenticated: true,
      })

      const { hasPermission } = usePermission()
      expect(hasPermission('any:permission')).toBe(true)
      expect(hasPermission('role:write')).toBe(true)
    })

    it('should return true when user has the specific permission', () => {
      useAuthStore.setState({
        user: {
          id: 2,
          username: 'operator',
          email: null,
          is_active: true,
          is_superuser: false,
          roles: ['operator'],
          permissions: ['terminal:read', 'terminal:write', 'whitelist:read'],
        },
        isAuthenticated: true,
      })

      const { hasPermission } = usePermission()
      expect(hasPermission('terminal:read')).toBe(true)
      expect(hasPermission('terminal:write')).toBe(true)
    })

    it('should return false when user lacks the permission', () => {
      useAuthStore.setState({
        user: {
          id: 3,
          username: 'viewer',
          email: null,
          is_active: true,
          is_superuser: false,
          roles: ['viewer'],
          permissions: ['terminal:read'],
        },
        isAuthenticated: true,
      })

      const { hasPermission } = usePermission()
      expect(hasPermission('terminal:write')).toBe(false)
      expect(hasPermission('role:write')).toBe(false)
    })

    it('should return false when user is null', () => {
      useAuthStore.setState({ user: null, isAuthenticated: false })

      const { hasPermission } = usePermission()
      expect(hasPermission('terminal:read')).toBe(false)
    })
  })

  describe('hasAnyPermission', () => {
    it('should return true for superuser', () => {
      useAuthStore.setState({
        user: {
          id: 1,
          username: 'admin',
          email: null,
          is_active: true,
          is_superuser: true,
          roles: ['superadmin'],
          permissions: [],
        },
        isAuthenticated: true,
      })

      const { hasAnyPermission } = usePermission()
      expect(hasAnyPermission(['role:write', 'user:delete'])).toBe(true)
    })

    it('should return true when user has at least one of the permissions', () => {
      useAuthStore.setState({
        user: {
          id: 2,
          username: 'operator',
          email: null,
          is_active: true,
          is_superuser: false,
          roles: ['operator'],
          permissions: ['terminal:read'],
        },
        isAuthenticated: true,
      })

      const { hasAnyPermission } = usePermission()
      expect(hasAnyPermission(['terminal:write', 'terminal:read'])).toBe(true)
    })

    it('should return false when user has none of the permissions', () => {
      useAuthStore.setState({
        user: {
          id: 3,
          username: 'viewer',
          email: null,
          is_active: true,
          is_superuser: false,
          roles: ['viewer'],
          permissions: ['terminal:read'],
        },
        isAuthenticated: true,
      })

      const { hasAnyPermission } = usePermission()
      expect(hasAnyPermission(['role:write', 'user:delete'])).toBe(false)
    })
  })

  describe('hasAllPermissions', () => {
    it('should return true for superuser', () => {
      useAuthStore.setState({
        user: {
          id: 1,
          username: 'admin',
          email: null,
          is_active: true,
          is_superuser: true,
          roles: ['superadmin'],
          permissions: [],
        },
        isAuthenticated: true,
      })

      const { hasAllPermissions } = usePermission()
      expect(hasAllPermissions(['terminal:read', 'terminal:write'])).toBe(true)
    })

    it('should return true when user has all permissions', () => {
      useAuthStore.setState({
        user: {
          id: 2,
          username: 'operator',
          email: null,
          is_active: true,
          is_superuser: false,
          roles: ['operator'],
          permissions: ['terminal:read', 'terminal:write', 'whitelist:read'],
        },
        isAuthenticated: true,
      })

      const { hasAllPermissions } = usePermission()
      expect(hasAllPermissions(['terminal:read', 'terminal:write'])).toBe(true)
    })

    it('should return false when user is missing some permissions', () => {
      useAuthStore.setState({
        user: {
          id: 3,
          username: 'viewer',
          email: null,
          is_active: true,
          is_superuser: false,
          roles: ['viewer'],
          permissions: ['terminal:read'],
        },
        isAuthenticated: true,
      })

      const { hasAllPermissions } = usePermission()
      expect(hasAllPermissions(['terminal:read', 'terminal:write'])).toBe(false)
    })
  })

  describe('hasRole', () => {
    it('should return true for superuser regardless of role name', () => {
      useAuthStore.setState({
        user: {
          id: 1,
          username: 'admin',
          email: null,
          is_active: true,
          is_superuser: true,
          roles: ['superadmin'],
          permissions: [],
        },
        isAuthenticated: true,
      })

      const { hasRole } = usePermission()
      expect(hasRole('any_role')).toBe(true)
    })

    it('should return true when user has the role', () => {
      useAuthStore.setState({
        user: {
          id: 2,
          username: 'operator',
          email: null,
          is_active: true,
          is_superuser: false,
          roles: ['operator'],
          permissions: ['terminal:read'],
        },
        isAuthenticated: true,
      })

      const { hasRole } = usePermission()
      expect(hasRole('operator')).toBe(true)
    })

    it('should return false when user does not have the role', () => {
      useAuthStore.setState({
        user: {
          id: 3,
          username: 'viewer',
          email: null,
          is_active: true,
          is_superuser: false,
          roles: ['viewer'],
          permissions: ['terminal:read'],
        },
        isAuthenticated: true,
      })

      const { hasRole } = usePermission()
      expect(hasRole('admin')).toBe(false)
    })

    it('should return false when user is null', () => {
      useAuthStore.setState({ user: null, isAuthenticated: false })

      const { hasRole } = usePermission()
      expect(hasRole('operator')).toBe(false)
    })
  })
})
