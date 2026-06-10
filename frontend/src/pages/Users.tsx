import React, { useState, useMemo, useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { useQueryClient } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { useUsers, UserItem } from '@/hooks/useTerminalData';
import { useAuthStore } from '@/store/auth';
import { usePermission } from '@/hooks/usePermission';
import { apiClient } from '@/lib/api';
import { API_ENDPOINTS } from '@/lib/constants';
import { getErrorMessage, useDebounce } from '@/lib/utils';
import { Search, Plus, Edit2, Trash2, Unlock, Shield, ShieldCheck, Eye, EyeOff, KeyRound, Users as UsersIcon, RefreshCw, ChevronDown } from 'lucide-react';
import { toast } from 'sonner';
import { PrimaryButton, IconButton, ButtonGroup } from '@/components/Button';
import { Pagination } from '@/components/Pagination';
import { EmptyState } from '@/components/StateDisplay';
import { PageSkeleton } from '@/components/Skeleton';
import { Modal } from '@/components/Modal';

interface RoleOption {
  id: number;
  name: string;
  description: string | null;
  is_default: boolean;
}

interface UserFormData {
  username: string;
  email: string;
  password: string;
  is_active: boolean;
  is_superuser: boolean;
  role_id: number | null;
}

const Users: React.FC = () => {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const { user: currentUser } = useAuthStore();
  const { hasPermission } = usePermission();
  const [searchTerm, setSearchTerm] = useState('');
  const debouncedSearch = useDebounce(searchTerm, 500);
  const { data: users, isLoading } = useUsers(debouncedSearch || undefined);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [editingUser, setEditingUser] = useState<UserItem | null>(null);
  const [resetPasswordUser, setResetPasswordUser] = useState<UserItem | null>(null);
  const [showPassword, setShowPassword] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [filterCollapsed, setFilterCollapsed] = useState(false);
  const [roles, setRoles] = useState<RoleOption[]>([]);

  // Fetch roles for the form
  useEffect(() => {
    const fetchRoles = async () => {
      try {
        const res = await apiClient.get(API_ENDPOINTS.ROLES);
        setRoles(res.data);
      } catch {
        // silent
      }
    };
    fetchRoles();
  }, []);

  const { register, handleSubmit, formState: { errors }, reset } = useForm<UserFormData>({
    defaultValues: { is_active: true, is_superuser: false, role_id: null },
  });

  const filteredUsers = users || [];

  const totalPages = useMemo(() => Math.ceil(filteredUsers.length / pageSize), [filteredUsers, pageSize]);
  const paginatedUsers = useMemo(() => {
    const start = (currentPage - 1) * pageSize;
    const end = start + pageSize;
    return filteredUsers.slice(start, end);
  }, [filteredUsers, currentPage, pageSize]);

  const handlePageChange = (page: number) => {
    setCurrentPage(page);
  };

  const handlePageSizeChange = (size: number) => {
    setPageSize(size);
    setCurrentPage(1);
  };

  const handleReset = () => {
    setSearchTerm('');
    setCurrentPage(1);
  };

  // Create user
  const onCreateSubmit = async (data: UserFormData) => {
    try {
      const payload = {
        username: data.username,
        email: data.email || null,
        password: data.password,
        is_active: data.is_active,
        is_superuser: data.is_superuser,
        role_id: data.role_id || undefined,
      };
      await apiClient.post(API_ENDPOINTS.AUTH_USERS, payload);
      toast.success(t('users.userCreated', { username: data.username }));
      setShowCreateModal(false);
      reset();
      queryClient.invalidateQueries({ queryKey: ['users'] });
    } catch (err: unknown) {
      toast.error(getErrorMessage(err, t('users.failedToCreateUser')));
    }
  };

  // Update user
  const handleUpdateUser = async (userId: number, updates: Partial<UserItem> & { role_id?: number | null }) => {
    try {
      const payload: Record<string, unknown> = {};
      if (updates.email !== undefined) payload.email = updates.email;
      if (updates.is_active !== undefined) payload.is_active = updates.is_active;
      if (updates.role_id !== undefined) payload.role_id = updates.role_id;
      await apiClient.put(`${API_ENDPOINTS.AUTH_USERS}${userId}`, payload);
      toast.success(t('users.userUpdated'));
      setEditingUser(null);
      queryClient.invalidateQueries({ queryKey: ['users'] });
    } catch (err: unknown) {
      toast.error(getErrorMessage(err, t('users.failedToUpdateUser')));
    }
  };

  // Delete user
  const handleDeleteUser = async (user: UserItem) => {
    if (!confirm(t('users.areYouSureDeleteUser'))) return;
    try {
      await apiClient.delete(`${API_ENDPOINTS.AUTH_USERS}${user.id}`);
      toast.success(t('users.userDeleted', { username: user.username }));
      queryClient.invalidateQueries({ queryKey: ['users'] });
    } catch (err: unknown) {
      toast.error(getErrorMessage(err, t('users.failedToDeleteUser')));
    }
  };

  // Toggle active status
  const handleToggleActive = async (user: UserItem) => {
    await handleUpdateUser(user.id, { is_active: !user.is_active });
  };

  // Unlock user
  const handleUnlock = async (user: UserItem) => {
    try {
      await apiClient.post(`${API_ENDPOINTS.AUTH_USERS}${user.id}/unlock`);
      toast.success(t('users.accountUnlocked', { username: user.username }));
    } catch (err: unknown) {
      toast.error(getErrorMessage(err, t('users.failedToUnlock')));
    }
  };

  // Reset password
  const handleResetPassword = async (userId: number, newPassword: string) => {
    try {
      await apiClient.put(`${API_ENDPOINTS.AUTH_USERS}${userId}/password`, { new_password: newPassword });
      toast.success(t('users.passwordResetSuccess'));
      setResetPasswordUser(null);
      setShowPassword(false);
    } catch (err: unknown) {
      toast.error(getErrorMessage(err, t('users.failedToResetPassword')));
    }
  };

  const isSelf = (user: UserItem) => currentUser?.id === user.id;

  return (
    <div className="min-h-full bg-background p-4 sm:p-6 lg:p-8">
      {isLoading && !users ? (
        <PageSkeleton />
      ) : (
      <>
      {/* Page Header */}
      <div className="mb-6 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-foreground">{t('users.title')}</h1>
          <p className="text-muted-foreground mt-1">{t('users.manageAccounts')}</p>
        </div>
        {hasPermission('user:write') && (
        <PrimaryButton
          icon={Plus}
          label={t('users.newUser')}
          variant="primary"
          onClick={() => { reset({ username: '', email: '', password: '', is_active: true, is_superuser: false, role_id: null }); setShowCreateModal(true); }}
        />
        )}
      </div>

      {/* Search and Filter */}
      <div className="bg-card rounded-2xl border border-border shadow-sm overflow-hidden mb-6">
        {/* Section Header - Clickable */}
        <button
          onClick={() => setFilterCollapsed(!filterCollapsed)}
          className={`w-full px-5 py-4 flex items-center justify-between hover:bg-background/50 transition-colors ${!filterCollapsed ? 'border-b border-border' : ''}`}
        >
          <div className="flex items-center gap-2">
            <Search className="h-5 w-5 text-muted-foreground" />
            <h2 className="text-base font-semibold text-foreground">{t('terminal.searchAndFilter')}</h2>
          </div>
          <ChevronDown className={`h-4 w-4 text-muted-foreground transition-transform duration-200 ${filterCollapsed ? '' : 'rotate-180'}`} />
        </button>
        {!filterCollapsed && (
        <>
        <div className="p-4 sm:p-5">
          <div className="flex flex-col xl:flex-row gap-4">
            {/* Search Input */}
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-5 w-5 text-muted-foreground" />
              <input
                type="text"
                placeholder={t('users.searchByUsernameOrEmail')}
                value={searchTerm}
                onChange={(e) => {
                  setSearchTerm(e.target.value);
                  setCurrentPage(1);
                }}
                className="w-full pl-10 pr-4 py-2.5 border border-border rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm transition-all"
              />
            </div>

            {/* Filters */}
            <div className="flex flex-wrap items-center gap-2">
              {/* Reset Button */}
              <PrimaryButton
                icon={RefreshCw}
                label={t('common.reset')}
                variant="secondary"
                size="sm"
                onClick={handleReset}
              />
            </div>
          </div>
        </div>

        {/* Top Pagination - Info Row */}
        {totalPages > 1 && (
          <div className="px-4 sm:px-5 py-3 bg-background border-t border-border">
            <Pagination
              currentPage={currentPage}
              totalPages={totalPages}
              onPageChange={handlePageChange}
              pageSize={pageSize}
              onPageSizeChange={handlePageSizeChange}
              totalItems={filteredUsers.length}
              variant="top"
              showPageSizeSelector={false}
            />
          </div>
        )}
        </>
        )}
      </div>

      {/* Table */}
      <div className="bg-card rounded-2xl border border-border shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-border">
            <thead className="bg-background">
              <tr>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  {t('auditLogs.user')}
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  {t('users.email')}
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-center text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  {t('users.role')}
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-center text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  {t('common.status')}
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  {t('users.created')}
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-center text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  {t('common.actions')}
                </th>
              </tr>
            </thead>
            <tbody className="bg-card divide-y divide-border">
              {filteredUsers.length === 0 ? (
                <tr>
                  <td colSpan={6}>
                    <EmptyState
                      icon={UsersIcon}
                      title={t('users.noUsersFound')}
                      description={t('users.createNewUserDescription')}
                      action={{
                        label: t('users.newUser'),
                        onClick: () => { reset({ username: '', email: '', password: '', is_active: true, is_superuser: false }); setShowCreateModal(true); }
                      }}
                    />
                  </td>
                </tr>
              ) : (
                (paginatedUsers || []).map((user) => (
                  <tr key={user.id} className="hover:bg-blue-50/30 transition-colors">
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center gap-3">
                        <div className="w-9 h-9 rounded-full bg-blue-600 flex items-center justify-center flex-shrink-0">
                          <span className="text-sm font-medium text-white">{user.username.charAt(0).toUpperCase()}</span>
                        </div>
                        <div>
                          <p className="font-medium text-foreground">{user.username}</p>
                          {isSelf(user) && <span className="text-xs text-blue-600">({t('users.you')})</span>}
                        </div>
                      </div>
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap text-sm text-muted-foreground">{user.email || '—'}</td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap text-center">
                      <div className="flex items-center justify-center gap-1 flex-wrap">
                        {user.roles && user.roles.length > 0 ? (
                          user.roles.map((roleName) => (
                            <span
                              key={roleName}
                              className={`inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium ${
                                roleName === 'superadmin'
                                  ? 'bg-purple-100 text-purple-800'
                                  : roleName === 'admin'
                                  ? 'bg-blue-100 text-blue-800'
                                  : 'bg-gray-100 text-gray-700'
                              }`}
                            >
                              {roleName === 'superadmin' && <ShieldCheck className="h-3 w-3" />}
                              {roleName === 'admin' && <Shield className="h-3 w-3" />}
                              {t(`roles.${roleName}`, roleName)}
                            </span>
                          ))
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-muted text-foreground">
                            <Shield className="h-3 w-3" /> {t('users.userRole')}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap text-center">
                      <button
                        onClick={() => !isSelf(user) && hasPermission('user:write') && handleToggleActive(user)}
                        disabled={isSelf(user) || !hasPermission('user:write')}
                        className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium cursor-pointer disabled:cursor-not-allowed ${
                          user.is_active ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                        }`}
                      >
                        {user.is_active ? t('common.active') : t('common.inactive')}
                      </button>
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap text-sm text-muted-foreground">
                      {user.created_at ? new Date(user.created_at).toLocaleDateString() : '—'}
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center justify-center">
                        <ButtonGroup>
                          {hasPermission('user:unlock') && (
                          <IconButton
                            icon={Unlock}
                            variant="success"
                            size="md"
                            title={t('users.unlockAccount')}
                            onClick={() => handleUnlock(user)}
                          />
                          )}
                          {hasPermission('user:password') && (
                          <IconButton
                            icon={KeyRound}
                            variant="primary"
                            size="md"
                            title={t('users.resetPassword')}
                            onClick={() => setResetPasswordUser(user)}
                          />
                          )}
                          {hasPermission('user:write') && (
                          <IconButton
                            icon={Edit2}
                            variant="primary"
                            size="md"
                            title={t('users.editUser')}
                            onClick={() => setEditingUser(user)}
                          />
                          )}
                          {!isSelf(user) && hasPermission('user:delete') && (
                            <IconButton
                              icon={Trash2}
                              variant="danger"
                              size="md"
                              title={t('users.deleteUser')}
                              onClick={() => handleDeleteUser(user)}
                            />
                          )}
                        </ButtonGroup>
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>

        {/* Bottom Pagination - Full Features */}
        <Pagination
          currentPage={currentPage}
          totalPages={totalPages}
          onPageChange={handlePageChange}
          pageSize={pageSize}
          onPageSizeChange={handlePageSizeChange}
          totalItems={filteredUsers.length}
          variant="bottom"
        />
      </div>

      {/* Create User Modal */}
      <Modal isOpen={showCreateModal} onClose={() => setShowCreateModal(false)} title={t('users.createNewUser')} size="md">
        <form onSubmit={handleSubmit(onCreateSubmit)} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-muted-foreground mb-1">{t('users.username')}</label>
            <input
              {...register('username', {
                required: t('users.required'),
                minLength: { value: 3, message: t('users.min3Characters') },
                pattern: { value: /^[a-zA-Z0-9_]+$/, message: t('users.lettersNumbersUnderscores') },
              })}
              className="w-full px-3 py-2 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
              placeholder="e.g. john_doe"
            />
            {errors.username && <p className="text-xs text-red-600 mt-1">{errors.username.message}</p>}
          </div>
          <div>
            <label className="block text-sm font-medium text-muted-foreground mb-1">{t('users.email')}</label>
            <input
              {...register('email', { pattern: { value: /^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$/i, message: t('users.invalidEmail') } })}
              type="email"
              className="w-full px-3 py-2 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
              placeholder="john@example.com"
            />
            {errors.email && <p className="text-xs text-red-600 mt-1">{errors.email.message}</p>}
          </div>
          <div>
            <label className="block text-sm font-medium text-muted-foreground mb-1">{t('users.passwordLabel')}</label>
            <input
              {...register('password', {
                required: t('users.required'),
                minLength: { value: 8, message: t('users.min8Characters') },
                pattern: { value: /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}$/, message: t('users.mustContainUpperLowerDigit') },
              })}
              type="password"
              className="w-full px-3 py-2 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
              placeholder={t('users.min8CharsUpperLowerDigit')}
            />
            {errors.password && <p className="text-xs text-red-600 mt-1">{errors.password.message}</p>}
          </div>
          <div>
            <label className="block text-sm font-medium text-muted-foreground mb-2">{t('users.role')}</label>
            <select
              {...register('role_id', { valueAsNumber: true })}
              className="w-full px-3 py-2 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
            >
              <option value="">{t('users.selectRole', 'Select a role')}</option>
              {roles.filter((r) => r.name !== 'superadmin').map((role) => (
                <option key={role.id} value={role.id}>
                  {t(`roles.${role.name}`, role.name)}
                </option>
              ))}
            </select>
          </div>
          <div className="flex items-center gap-6">
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" {...register('is_active')} className="rounded" />
              {t('users.activeLabel')}
            </label>
          </div>
          <div className="flex gap-3 pt-2">
            <PrimaryButton
              label={t('common.cancel')}
              variant="secondary"
              onClick={() => setShowCreateModal(false)}
              className="flex-1"
            />
            <PrimaryButton
              label={t('common.create')}
              variant="primary"
              type="submit"
              className="flex-1"
            />
          </div>
        </form>
      </Modal>

      {/* Edit User Modal */}
      {editingUser && (
        <EditUserModal
          user={editingUser}
          isSelf={isSelf(editingUser)}
          onSave={handleUpdateUser}
          onClose={() => setEditingUser(null)}
          roles={roles}
        />
      )}

      {/* Reset Password Modal */}
      {resetPasswordUser && (
        <ResetPasswordModal
          user={resetPasswordUser}
          onSave={handleResetPassword}
          onClose={() => { setResetPasswordUser(null); setShowPassword(false); }}
          showPassword={showPassword}
          setShowPassword={setShowPassword}
        />
      )}
      </>
      )}
    </div>
  );
};

// Edit User Modal Component
const EditUserModal: React.FC<{
  user: UserItem;
  isSelf: boolean;
  onSave: (userId: number, updates: Partial<UserItem>) => Promise<void>;
  onClose: () => void;
  roles: RoleOption[];
}> = ({ user, isSelf, onSave, onClose, roles }) => {
  const { t } = useTranslation();
  const [email, setEmail] = useState(user.email || '');
  const [isActive, setIsActive] = useState(user.is_active);
  const [selectedRoleId, setSelectedRoleId] = useState<number | null>(() => {
    // Map user's role name to role ID
    const matched = roles.find((r) => user.roles?.includes(r.name));
    return matched ? matched.id : null;
  });
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    await onSave(user.id, { email, is_active: isActive, role_id: selectedRoleId } as unknown as Partial<UserItem>);
    setSaving(false);
  };

  return (
    <Modal isOpen={true} onClose={onClose} title={`${t('users.editUser')}: ${user.username}`} size="md">
      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-muted-foreground mb-1">{t('users.email')}</label>
          <input
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full px-3 py-2 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
          />
        </div>
        {!(isSelf || user.is_superuser) && (
        <div>
          <label className="block text-sm font-medium text-muted-foreground mb-2">{t('users.role')}</label>
          <select
            value={selectedRoleId ?? ''}
            onChange={(e) => setSelectedRoleId(e.target.value ? Number(e.target.value) : null)}
            className="w-full px-3 py-2 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
          >
            <option value="">{t('users.selectRole', 'Select a role')}</option>
            {roles.filter((r) => r.name !== 'superadmin').map((role) => (
              <option key={role.id} value={role.id}>
                {t(`roles.${role.name}`, role.name)}
              </option>
            ))}
          </select>
        </div>
        )}
        {(isSelf || user.is_superuser) && (
          <div>
            <label className="block text-sm font-medium text-muted-foreground mb-1">{t('users.role')}</label>
            <p className="text-sm text-foreground">{user.roles?.map((r) => t(`roles.${r}`, r)).join(', ') || '—'}</p>
            {user.is_superuser && <p className="text-xs text-amber-600 mt-1">{t('users.superadminRoleFixed')}</p>}
          </div>
        )}
        <div className="flex items-center gap-6">
          <label className="flex items-center gap-2 text-sm">
            <input type="checkbox" checked={isActive} onChange={(e) => setIsActive(e.target.checked)} disabled={isSelf} className="rounded" />
            {t('users.activeLabel')}
          </label>
        </div>
        {isSelf && <p className="text-xs text-amber-600">{t('users.cannotModifyOwnRole')}</p>}
        <div className="flex gap-3 pt-2">
          <PrimaryButton
            label={t('common.cancel')}
            variant="secondary"
            onClick={onClose}
            className="flex-1"
          />
          <PrimaryButton
            label={t('common.save')}
            variant="primary"
            onClick={handleSave}
            loading={saving}
            className="flex-1"
          />
        </div>
      </div>
    </Modal>
  );
};

// Reset Password Modal Component
const ResetPasswordModal: React.FC<{
  user: UserItem;
  onSave: (userId: number, newPassword: string) => Promise<void>;
  onClose: () => void;
  showPassword: boolean;
  setShowPassword: (v: boolean) => void;
}> = ({ user, onSave, onClose, showPassword, setShowPassword }) => {
  const { t } = useTranslation();
  const [newPassword, setNewPassword] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const handleSave = async () => {
    if (newPassword.length < 8) { setError(t('users.min8Characters')); return; }
    if (!/[A-Z]/.test(newPassword)) { setError(t('users.mustContainUppercase')); return; }
    if (!/[a-z]/.test(newPassword)) { setError(t('users.mustContainLowercase')); return; }
    if (!/\d/.test(newPassword)) { setError(t('users.mustContainNumber')); return; }
    setError('');
    setSaving(true);
    await onSave(user.id, newPassword);
    setSaving(false);
  };

  return (
    <Modal isOpen={true} onClose={onClose} title={`${t('users.resetPasswordTitle')}: ${user.username}`} size="md">
      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-muted-foreground mb-1">{t('users.newPassword')}</label>
          <div className="relative">
            <input
              type={showPassword ? 'text' : 'password'}
              value={newPassword}
              onChange={(e) => { setNewPassword(e.target.value); setError(''); }}
              className="w-full px-3 py-2 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm pr-10"
              placeholder={t('users.min8CharsUpperLowerDigit')}
            />
            <button
              type="button"
              onClick={() => setShowPassword(!showPassword)}
              className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-muted-foreground"
            >
              {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
            </button>
          </div>
          {error && <p className="text-xs text-red-600 mt-1">{error}</p>}
        </div>
        <div className="flex gap-3 pt-2">
          <PrimaryButton
            label={t('common.cancel')}
            variant="secondary"
            onClick={onClose}
            className="flex-1"
          />
          <PrimaryButton
            label={t('users.resetPassword')}
            variant="primary"
            onClick={handleSave}
            loading={saving}
            className="flex-1"
          />
        </div>
      </div>
    </Modal>
  );
};

export default Users;
