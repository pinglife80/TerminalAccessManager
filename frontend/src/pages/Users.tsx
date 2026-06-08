import React, { useState, useMemo } from 'react';
import { useForm } from 'react-hook-form';
import { useQueryClient } from '@tanstack/react-query';
import { useUsers, UserItem } from '@/hooks/useTerminalData';
import { useAuthStore } from '@/store/auth';
import { apiClient } from '@/lib/api';
import { Search, Plus, Edit2, Trash2, Unlock, Shield, ShieldCheck, Eye, EyeOff, X, KeyRound, Users as UsersIcon, RefreshCw, ChevronDown } from 'lucide-react';
import { toast } from 'sonner';
import { PrimaryButton, IconButton, ButtonGroup } from '@/components/Button';
import { Pagination } from '@/components/Pagination';
import { EmptyState, LoadingState } from '@/components/StateDisplay';

interface UserFormData {
  username: string;
  email: string;
  password: string;
  is_active: boolean;
  is_superuser: boolean;
}

const Users: React.FC = () => {
  const queryClient = useQueryClient();
  const { user: currentUser } = useAuthStore();
  const [searchTerm, setSearchTerm] = useState('');
  const { data: users, isLoading } = useUsers(searchTerm || undefined);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [editingUser, setEditingUser] = useState<UserItem | null>(null);
  const [resetPasswordUser, setResetPasswordUser] = useState<UserItem | null>(null);
  const [showPassword, setShowPassword] = useState(false);
  const [currentPage, setCurrentPage] = useState(1);
  const [pageSize, setPageSize] = useState(10);
  const [filterCollapsed, setFilterCollapsed] = useState(false);

  const { register, handleSubmit, formState: { errors }, reset } = useForm<UserFormData>({
    defaultValues: { is_active: true, is_superuser: false },
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
      await apiClient.post('/auth/users', data);
      toast.success(`User '${data.username}' created successfully`);
      setShowCreateModal(false);
      reset();
      queryClient.invalidateQueries({ queryKey: ['users'] });
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Failed to create user');
    }
  };

  // Update user
  const handleUpdateUser = async (userId: number, updates: Partial<UserItem>) => {
    try {
      await apiClient.put(`/auth/users/${userId}`, updates);
      toast.success('User updated successfully');
      setEditingUser(null);
      queryClient.invalidateQueries({ queryKey: ['users'] });
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Failed to update user');
    }
  };

  // Delete user
  const handleDeleteUser = async (user: UserItem) => {
    if (!confirm(`Are you sure you want to delete user '${user.username}'? This action cannot be undone.`)) return;
    try {
      await apiClient.delete(`/auth/users/${user.id}`);
      toast.success(`User '${user.username}' deleted`);
      queryClient.invalidateQueries({ queryKey: ['users'] });
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Failed to delete user');
    }
  };

  // Toggle active status
  const handleToggleActive = async (user: UserItem) => {
    await handleUpdateUser(user.id, { is_active: !user.is_active } as any);
  };

  // Unlock user
  const handleUnlock = async (user: UserItem) => {
    try {
      await apiClient.post(`/auth/users/${user.id}/unlock`);
      toast.success(`Account '${user.username}' unlocked`);
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Failed to unlock user');
    }
  };

  // Reset password
  const handleResetPassword = async (userId: number, newPassword: string) => {
    try {
      await apiClient.put(`/auth/users/${userId}/password`, { new_password: newPassword });
      toast.success('Password reset successfully');
      setResetPasswordUser(null);
      setShowPassword(false);
    } catch (err: any) {
      toast.error(err.response?.data?.detail || 'Failed to reset password');
    }
  };

  const isSelf = (user: UserItem) => currentUser?.id === user.id;

  return (
    <div className="min-h-full bg-gray-50 p-4 sm:p-6 lg:p-8">
      {/* Page Header */}
      <div className="mb-6 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-gray-900">User Management</h1>
          <p className="text-gray-600 mt-1">Manage user accounts, roles, and access</p>
        </div>
        <PrimaryButton
          icon={Plus}
          label="New User"
          variant="primary"
          onClick={() => { reset({ username: '', email: '', password: '', is_active: true, is_superuser: false }); setShowCreateModal(true); }}
        />
      </div>

      {/* Search and Filter */}
      <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden mb-6">
        {/* Section Header - Clickable */}
        <button
          onClick={() => setFilterCollapsed(!filterCollapsed)}
          className={`w-full px-5 py-4 flex items-center justify-between hover:bg-gray-50/50 transition-colors ${!filterCollapsed ? 'border-b border-gray-100' : ''}`}
        >
          <div className="flex items-center gap-2">
            <Search className="h-5 w-5 text-gray-500" />
            <h2 className="text-base font-semibold text-gray-900">Search & Filter</h2>
          </div>
          <ChevronDown className={`h-4 w-4 text-gray-500 transition-transform duration-200 ${filterCollapsed ? '' : 'rotate-180'}`} />
        </button>
        {!filterCollapsed && (
        <>
        <div className="p-4 sm:p-5">
          <div className="flex flex-col xl:flex-row gap-4">
            {/* Search Input */}
            <div className="flex-1 relative">
              <Search className="absolute left-3 top-1/2 transform -translate-y-1/2 h-5 w-5 text-gray-400" />
              <input
                type="text"
                placeholder="Search by username or email..."
                value={searchTerm}
                onChange={(e) => {
                  setSearchTerm(e.target.value);
                  setCurrentPage(1);
                }}
                className="w-full pl-10 pr-4 py-2.5 border border-gray-300 rounded-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:border-transparent text-sm transition-all"
              />
            </div>

            {/* Filters */}
            <div className="flex flex-wrap items-center gap-2">
              {/* Reset Button */}
              <PrimaryButton
                icon={RefreshCw}
                label="Reset"
                variant="secondary"
                size="sm"
                onClick={handleReset}
              />
            </div>
          </div>
        </div>

        {/* Top Pagination - Info Row */}
        {totalPages > 1 && (
          <div className="px-4 sm:px-5 py-3 bg-gray-50 border-t border-gray-200">
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
      <div className="bg-white rounded-2xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-gray-200">
            <thead className="bg-gray-50">
              <tr>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                  User
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                  Email
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-center text-xs font-semibold text-gray-600 uppercase tracking-wider">
                  Role
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-center text-xs font-semibold text-gray-600 uppercase tracking-wider">
                  Status
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">
                  Created
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-center text-xs font-semibold text-gray-600 uppercase tracking-wider">
                  Actions
                </th>
              </tr>
            </thead>
            <tbody className="bg-white divide-y divide-gray-200">
              {isLoading ? (
                <tr>
                  <td colSpan={6}>
                    <LoadingState message="Loading users..." />
                  </td>
                </tr>
              ) : filteredUsers.length === 0 ? (
                <tr>
                  <td colSpan={6}>
                    <EmptyState
                      icon={UsersIcon}
                      title="No Users Found"
                      description="Create a new user to get started"
                      action={{
                        label: "New User",
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
                          <p className="font-medium text-gray-900">{user.username}</p>
                          {isSelf(user) && <span className="text-xs text-blue-600">(you)</span>}
                        </div>
                      </div>
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap text-sm text-gray-600">{user.email || '—'}</td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap text-center">
                      {user.is_superuser ? (
                        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-purple-100 text-purple-800">
                          <ShieldCheck className="h-3 w-3" /> Admin
                        </span>
                      ) : (
                        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-800">
                          <Shield className="h-3 w-3" /> User
                        </span>
                      )}
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap text-center">
                      <button
                        onClick={() => !isSelf(user) && handleToggleActive(user)}
                        disabled={isSelf(user)}
                        className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium cursor-pointer disabled:cursor-not-allowed ${
                          user.is_active ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                        }`}
                      >
                        {user.is_active ? 'Active' : 'Inactive'}
                      </button>
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap text-sm text-gray-500">
                      {user.created_at ? new Date(user.created_at).toLocaleDateString() : '—'}
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center justify-center">
                        <ButtonGroup>
                          <IconButton
                            icon={Unlock}
                            variant="success"
                            size="md"
                            title="Unlock account"
                            onClick={() => handleUnlock(user)}
                          />
                          <IconButton
                            icon={KeyRound}
                            variant="primary"
                            size="md"
                            title="Reset password"
                            onClick={() => setResetPasswordUser(user)}
                          />
                          <IconButton
                            icon={Edit2}
                            variant="primary"
                            size="md"
                            title="Edit user"
                            onClick={() => setEditingUser(user)}
                          />
                          {!isSelf(user) && (
                            <IconButton
                              icon={Trash2}
                              variant="danger"
                              size="md"
                              title="Delete user"
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
      {showCreateModal && (
        <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
          <div className="bg-white rounded-xl shadow-xl max-w-md w-full p-6">
            <div className="flex items-center justify-between mb-4">
              <h3 className="text-lg font-semibold">Create New User</h3>
              <IconButton
                icon={X}
                variant="ghost"
                size="md"
                onClick={() => setShowCreateModal(false)}
              />
            </div>
            <form onSubmit={handleSubmit(onCreateSubmit)} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Username</label>
                <input
                  {...register('username', {
                    required: 'Required',
                    minLength: { value: 3, message: 'Min 3 characters' },
                    pattern: { value: /^[a-zA-Z0-9_]+$/, message: 'Letters, numbers, underscores only' },
                  })}
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                  placeholder="e.g. john_doe"
                />
                {errors.username && <p className="text-xs text-red-600 mt-1">{errors.username.message}</p>}
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
                <input
                  {...register('email', { pattern: { value: /^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$/i, message: 'Invalid email' } })}
                  type="email"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                  placeholder="john@example.com"
                />
                {errors.email && <p className="text-xs text-red-600 mt-1">{errors.email.message}</p>}
              </div>
              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Password</label>
                <input
                  {...register('password', {
                    required: 'Required',
                    minLength: { value: 8, message: 'Min 8 characters' },
                    pattern: { value: /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}$/, message: 'Must have uppercase, lowercase, and number' },
                  })}
                  type="password"
                  className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
                  placeholder="Min 8 chars, upper+lower+digit"
                />
                {errors.password && <p className="text-xs text-red-600 mt-1">{errors.password.message}</p>}
              </div>
              <div className="flex items-center gap-6">
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" {...register('is_active')} className="rounded" />
                  Active
                </label>
                <label className="flex items-center gap-2 text-sm">
                  <input type="checkbox" {...register('is_superuser')} className="rounded" />
                  Administrator
                </label>
              </div>
              <div className="flex gap-3 pt-2">
                <PrimaryButton
                  label="Cancel"
                  variant="secondary"
                  onClick={() => setShowCreateModal(false)}
                  className="flex-1"
                />
                <PrimaryButton
                  label="Create"
                  variant="primary"
                  type="submit"
                  className="flex-1"
                />
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Edit User Modal */}
      {editingUser && (
        <EditUserModal
          user={editingUser}
          isSelf={isSelf(editingUser)}
          onSave={handleUpdateUser}
          onClose={() => setEditingUser(null)}
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
    </div>
  );
};

// Edit User Modal Component
const EditUserModal: React.FC<{
  user: UserItem;
  isSelf: boolean;
  onSave: (userId: number, updates: Partial<UserItem>) => Promise<void>;
  onClose: () => void;
}> = ({ user, isSelf, onSave, onClose }) => {
  const [email, setEmail] = useState(user.email || '');
  const [isActive, setIsActive] = useState(user.is_active);
  const [isSuperuser, setIsSuperuser] = useState(user.is_superuser);
  const [saving, setSaving] = useState(false);

  const handleSave = async () => {
    setSaving(true);
    await onSave(user.id, { email, is_active: isActive, is_superuser: isSuperuser } as any);
    setSaving(false);
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl max-w-md w-full p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold">Edit User: {user.username}</h3>
          <IconButton
            icon={X}
            variant="ghost"
            size="md"
            onClick={onClose}
          />
        </div>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">Email</label>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
            />
          </div>
          <div className="flex items-center gap-6">
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={isActive} onChange={(e) => setIsActive(e.target.checked)} disabled={isSelf} className="rounded" />
              Active
            </label>
            <label className="flex items-center gap-2 text-sm">
              <input type="checkbox" checked={isSuperuser} onChange={(e) => setIsSuperuser(e.target.checked)} disabled={isSelf} className="rounded" />
              Administrator
            </label>
          </div>
          {isSelf && <p className="text-xs text-amber-600">You cannot modify your own role or status.</p>}
          <div className="flex gap-3 pt-2">
            <PrimaryButton
              label="Cancel"
              variant="secondary"
              onClick={onClose}
              className="flex-1"
            />
            <PrimaryButton
              label="Save"
              variant="primary"
              onClick={handleSave}
              loading={saving}
              className="flex-1"
            />
          </div>
        </div>
      </div>
    </div>
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
  const [newPassword, setNewPassword] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const handleSave = async () => {
    if (newPassword.length < 8) { setError('Min 8 characters'); return; }
    if (!/[A-Z]/.test(newPassword)) { setError('Must contain uppercase'); return; }
    if (!/[a-z]/.test(newPassword)) { setError('Must contain lowercase'); return; }
    if (!/\d/.test(newPassword)) { setError('Must contain a number'); return; }
    setError('');
    setSaving(true);
    await onSave(user.id, newPassword);
    setSaving(false);
  };

  return (
    <div className="fixed inset-0 bg-black bg-opacity-50 flex items-center justify-center z-50 p-4">
      <div className="bg-white rounded-xl shadow-xl max-w-md w-full p-6">
        <div className="flex items-center justify-between mb-4">
          <h3 className="text-lg font-semibold">Reset Password: {user.username}</h3>
          <IconButton
            icon={X}
            variant="ghost"
            size="md"
            onClick={onClose}
          />
        </div>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-1">New Password</label>
            <div className="relative">
              <input
                type={showPassword ? 'text' : 'password'}
                value={newPassword}
                onChange={(e) => { setNewPassword(e.target.value); setError(''); }}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm pr-10"
                placeholder="Min 8 chars, upper+lower+digit"
              />
              <button
                type="button"
                onClick={() => setShowPassword(!showPassword)}
                className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 hover:text-gray-600"
              >
                {showPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
              </button>
            </div>
            {error && <p className="text-xs text-red-600 mt-1">{error}</p>}
          </div>
          <div className="flex gap-3 pt-2">
            <PrimaryButton
              label="Cancel"
              variant="secondary"
              onClick={onClose}
              className="flex-1"
            />
            <PrimaryButton
              label="Reset Password"
              variant="primary"
              onClick={handleSave}
              loading={saving}
              className="flex-1"
            />
          </div>
        </div>
      </div>
    </div>
  );
};

export default Users;
