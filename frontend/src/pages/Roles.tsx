import React, { useState, useMemo } from 'react';
import { useTranslation } from 'react-i18next';
import { Shield, Plus, Edit2, Trash2, CheckCircle, Users as UsersIcon, Eye } from 'lucide-react';
import { apiClient } from '@/lib/api';
import { API_ENDPOINTS } from '@/lib/constants';
import { getErrorMessage } from '@/lib/utils';
import { toast } from 'sonner';
import { PrimaryButton, IconButton } from '@/components/Button';
import { EmptyState } from '@/components/StateDisplay';
import { PageSkeleton } from '@/components/Skeleton';
import { Modal } from '@/components/Modal';
import { usePermission } from '@/hooks/usePermission';
import { useAuthStore } from '@/store/auth';

interface Permission {
  id: number;
  code: string;
  name: string;
  module: string;
  description: string | null;
}

interface RoleItem {
  id: number;
  name: string;
  description: string | null;
  is_default: boolean;
  permissions: string[];
  user_count: number;
  created_at: string | null;
  updated_at: string | null;
}

interface RoleFormData {
  name: string;
  description: string;
  permission_ids: number[];
}

const BUILT_IN_ROLES = ['superadmin', 'admin', 'operator', 'auditor', 'viewer'];

const Roles: React.FC = () => {
  const { t } = useTranslation();
  const { hasPermission } = usePermission();
  const { user: currentUser } = useAuthStore();
  const isSuperadmin = currentUser?.is_superuser ?? false;
  const [roles, setRoles] = useState<RoleItem[]>([]);
  const [permissions, setPermissions] = useState<Permission[]>([]);
  const [loading, setLoading] = useState(true);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [editingRole, setEditingRole] = useState<RoleItem | null>(null);
  const [viewingRole, setViewingRole] = useState<RoleItem | null>(null);
  const [viewingRoleUsers, setViewingRoleUsers] = useState<RoleItem | null>(null);
  const [roleUsers, setRoleUsers] = useState<{ id: number; username: string; email: string | null; is_active: boolean; is_superuser: boolean }[]>([]);

  // Fetch roles and permissions
  React.useEffect(() => {
    const fetchData = async () => {
      try {
        const [rolesRes, permsRes] = await Promise.all([
          apiClient.get(API_ENDPOINTS.ROLES),
          apiClient.get(API_ENDPOINTS.ROLES_PERMISSIONS),
        ]);
        setRoles(rolesRes.data);
        setPermissions(permsRes.data);
      } catch (err) {
        toast.error(getErrorMessage(err, t('roles.failedToCreateRole')));
      } finally {
        setLoading(false);
      }
    };
    fetchData();
  }, [t]);

  const refreshRoles = async () => {
    try {
      const res = await apiClient.get(API_ENDPOINTS.ROLES);
      setRoles(res.data);
    } catch {
      // silent
    }
  };

  // Group permissions by module
  const permissionsByModule = useMemo(() => {
    const grouped: Record<string, Permission[]> = {};
    for (const perm of permissions) {
      if (!grouped[perm.module]) grouped[perm.module] = [];
      grouped[perm.module].push(perm);
    }
    return grouped;
  }, [permissions]);

  const handleDeleteRole = async (role: RoleItem) => {
    if (BUILT_IN_ROLES.includes(role.name)) {
      toast.error(t('roles.cannotDeleteBuiltInRole'));
      return;
    }
    if (!confirm(t('roles.areYouSureDeleteRole'))) return;
    try {
      await apiClient.delete(`${API_ENDPOINTS.ROLES}${role.id}`);
      toast.success(t('roles.roleDeleted'));
      refreshRoles();
    } catch (err: unknown) {
      toast.error(getErrorMessage(err, t('roles.failedToDeleteRole')));
    }
  };

  if (loading) return <PageSkeleton />;

  return (
    <div className="min-h-full bg-background p-4 sm:p-6 lg:p-8">
      {/* Page Header */}
      <div className="mb-6 flex flex-col md:flex-row md:items-center md:justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold text-foreground">{t('roles.title')}</h1>
          <p className="text-muted-foreground mt-1">{t('roles.manageRoles')}</p>
        </div>
        {hasPermission('role:write') && (
        <PrimaryButton
          icon={Plus}
          label={t('roles.createRole')}
          variant="primary"
          onClick={() => setShowCreateModal(true)}
        />
        )}
      </div>

      {/* Table */}
      <div className="bg-card rounded-2xl border border-border shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table className="min-w-full divide-y divide-border">
            <thead className="bg-background">
              <tr>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  {t('roles.roleName')}
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-left text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  {t('roles.description')}
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-center text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  {t('roles.permissions')}
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-center text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  {t('roles.userCount')}
                </th>
                <th className="px-4 sm:px-6 py-3.5 text-center text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  {t('common.actions')}
                </th>
              </tr>
            </thead>
            <tbody className="bg-card divide-y divide-border">
              {roles.length === 0 ? (
                <tr>
                  <td colSpan={5}>
                    <EmptyState
                      icon={Shield}
                      title={t('roles.noRolesFound')}
                      description={t('roles.createNewRoleDescription')}
                      action={{
                        label: t('roles.createRole'),
                        onClick: () => setShowCreateModal(true),
                      }}
                    />
                  </td>
                </tr>
              ) : (
                roles.map((role) => (
                  <tr key={role.id} className="hover:bg-blue-50/30 transition-colors">
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center gap-2">
                        <Shield className={`h-4 w-4 ${role.name === 'superadmin' ? 'text-purple-600' : 'text-blue-600'}`} />
                        <span className="font-medium text-foreground">{t(`roles.${role.name}`, role.name)}</span>
                        {role.is_default && (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-green-100 text-green-800">
                            {t('roles.isDefault')}
                          </span>
                        )}
                        {BUILT_IN_ROLES.includes(role.name) && (
                          <span className="inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium bg-gray-100 text-gray-600">
                            {t('roles.builtIn')}
                          </span>
                        )}
                      </div>
                    </td>
                    <td className="px-4 sm:px-6 py-4 text-sm text-muted-foreground">
                      {role.description || '—'}
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap text-center">
                      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium bg-blue-100 text-blue-800">
                        {role.name === 'superadmin' ? t('common.all') : role.permissions.length}
                      </span>
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap text-center text-sm text-muted-foreground">
                      <div className="flex items-center justify-center gap-1">
                        <UsersIcon className="h-3.5 w-3.5" />
                        {role.user_count}
                      </div>
                    </td>
                    <td className="px-4 sm:px-6 py-4 whitespace-nowrap">
                      <div className="flex items-center justify-center gap-1">
                        {(role.name !== 'superadmin' || isSuperadmin) && (
                        <IconButton
                          icon={Eye}
                          variant="primary"
                          size="md"
                          title={t('roles.viewPermissions')}
                          onClick={() => setViewingRole(role)}
                        />
                        )}
                        {(role.name !== 'superadmin' || isSuperadmin) && (
                        <IconButton
                          icon={UsersIcon}
                          variant="primary"
                          size="md"
                          title={t('roles.viewUsers')}
                          onClick={async () => {
                            try {
                              const res = await apiClient.get(`${API_ENDPOINTS.ROLES}${role.id}/users`);
                              setRoleUsers(res.data);
                              setViewingRoleUsers(role);
                            } catch (err: unknown) {
                              toast.error(getErrorMessage(err, t('roles.failedToLoadUsers')));
                            }
                          }}
                        />
                        )}
                        {hasPermission('role:write') && role.name !== 'superadmin' && (
                        <IconButton
                          icon={Edit2}
                          variant="primary"
                          size="md"
                          title={t('roles.editRole')}
                          onClick={() => setEditingRole(role)}
                        />
                        )}
                        {!BUILT_IN_ROLES.includes(role.name) && hasPermission('role:delete') && (
                          <IconButton
                            icon={Trash2}
                            variant="danger"
                            size="md"
                            title={t('roles.deleteRole')}
                            onClick={() => handleDeleteRole(role)}
                          />
                        )}
                      </div>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Create Role Modal */}
      {showCreateModal && (
        <RoleFormModal
          permissions={permissions}
          permissionsByModule={permissionsByModule}
          onSave={async (data) => {
            try {
              await apiClient.post(API_ENDPOINTS.ROLES, data);
              toast.success(t('roles.roleCreated'));
              setShowCreateModal(false);
              refreshRoles();
            } catch (err: unknown) {
              toast.error(getErrorMessage(err, t('roles.failedToCreateRole')));
            }
          }}
          onClose={() => setShowCreateModal(false)}
          title={t('roles.createRole')}
        />
      )}

      {/* Edit Role Modal */}
      {editingRole && (
        <RoleFormModal
          role={editingRole}
          permissions={permissions}
          permissionsByModule={permissionsByModule}
          onSave={async (data) => {
            try {
              await apiClient.put(`${API_ENDPOINTS.ROLES}${editingRole.id}`, data);
              toast.success(t('roles.roleUpdated'));
              setEditingRole(null);
              refreshRoles();
            } catch (err: unknown) {
              toast.error(getErrorMessage(err, t('roles.failedToUpdateRole')));
            }
          }}
          onClose={() => setEditingRole(null)}
          title={`${t('roles.editRole')}: ${t(`roles.${editingRole.name}`, editingRole.name)}`}
        />
      )}

      {/* View Permissions Modal */}
      {viewingRole && (
        <Modal isOpen={true} onClose={() => setViewingRole(null)} title={`${t('roles.viewPermissions')}: ${t(`roles.${viewingRole.name}`, viewingRole.name)}`} size="lg">
          <div className="space-y-3 max-h-[70vh] overflow-y-auto">
            <div className="mb-3">
              <span className="text-sm text-muted-foreground">{t('roles.description')}: </span>
              <span className="text-sm text-foreground">{viewingRole.description || '—'}</span>
            </div>
            {viewingRole.name === 'superadmin' ? (
              <div className="p-3 bg-purple-50 border border-purple-200 rounded-lg">
                <p className="text-sm font-medium text-purple-800">{t('roles.cannotModifySuperadmin')}</p>
                <p className="text-xs text-purple-600 mt-1">{t('roles.superadminHasAllPermissions')}</p>
              </div>
            ) : (
              Object.entries(permissionsByModule).map(([module, modulePerms]) => {
                const modulePermCodes = modulePerms.map((p) => p.code);
                const assigned = modulePermCodes.filter((code) => viewingRole.permissions.includes(code));
                if (assigned.length === 0) return null;
                return (
                  <div key={module} className="border border-border rounded-lg overflow-hidden">
                    <div className="px-4 py-2.5 bg-blue-50 text-blue-800 text-sm font-medium flex items-center justify-between">
                      <span>{t(`roles.permissionModules.${module}`, module)}</span>
                      <span className="text-xs">{assigned.length}/{modulePermCodes.length}</span>
                    </div>
                    <div className="px-4 py-2 grid grid-cols-2 gap-2 bg-card">
                      {modulePerms.map((perm) => (
                        <div key={perm.id} className="flex items-center gap-2 text-sm">
                          {viewingRole.permissions.includes(perm.code) ? (
                            <CheckCircle className="h-4 w-4 text-green-600 flex-shrink-0" />
                          ) : (
                            <div className="h-4 w-4 rounded border border-gray-300 flex-shrink-0" />
                          )}
                          <span className={viewingRole.permissions.includes(perm.code) ? 'text-foreground' : 'text-muted-foreground'}>
                            {perm.name}
                          </span>
                        </div>
                      ))}
                    </div>
                  </div>
                );
              })
            )}
            <div className="flex gap-3 pt-2">
              <PrimaryButton
                label={t('common.close')}
                variant="secondary"
                onClick={() => setViewingRole(null)}
                className="flex-1"
              />
            </div>
          </div>
        </Modal>
      )}

      {/* View Role Users Modal */}
      {viewingRoleUsers && (
        <Modal isOpen={true} onClose={() => { setViewingRoleUsers(null); setRoleUsers([]); }} title={`${t('roles.viewUsers')}: ${t(`roles.${viewingRoleUsers.name}`, viewingRoleUsers.name)}`} size="md">
          <div className="space-y-3 max-h-[70vh] overflow-y-auto">
            {roleUsers.length === 0 ? (
              <p className="text-sm text-muted-foreground text-center py-4">{t('roles.noUsersInRole')}</p>
            ) : (
              <table className="min-w-full divide-y divide-border">
                <thead className="bg-background">
                  <tr>
                    <th className="px-4 py-2.5 text-left text-xs font-semibold text-muted-foreground uppercase">{t('auditLogs.user')}</th>
                    <th className="px-4 py-2.5 text-left text-xs font-semibold text-muted-foreground uppercase">{t('users.email')}</th>
                    <th className="px-4 py-2.5 text-center text-xs font-semibold text-muted-foreground uppercase">{t('common.status')}</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-border">
                  {roleUsers.map((u) => (
                    <tr key={u.id} className="hover:bg-blue-50/30">
                      <td className="px-4 py-2.5 text-sm">
                        <div className="flex items-center gap-2">
                          <div className="w-7 h-7 rounded-full bg-blue-600 flex items-center justify-center flex-shrink-0">
                            <span className="text-xs font-medium text-white">{u.username.charAt(0).toUpperCase()}</span>
                          </div>
                          <span className="font-medium text-foreground">{u.username}</span>
                          {u.is_superuser && <span className="text-xs text-purple-600">({t('users.admin')})</span>}
                        </div>
                      </td>
                      <td className="px-4 py-2.5 text-sm text-muted-foreground">{u.email || '—'}</td>
                      <td className="px-4 py-2.5 text-center">
                        <span className={`inline-flex items-center px-2 py-0.5 rounded-full text-xs font-medium ${
                          u.is_active ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                        }`}>
                          {u.is_active ? t('common.active') : t('common.inactive')}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
            <div className="flex gap-3 pt-2">
              <PrimaryButton
                label={t('common.close')}
                variant="secondary"
                onClick={() => { setViewingRoleUsers(null); setRoleUsers([]); }}
                className="flex-1"
              />
            </div>
          </div>
        </Modal>
      )}
    </div>
  );
};

// Role Form Modal Component
const RoleFormModal: React.FC<{
  role?: RoleItem | null;
  permissions: Permission[];
  permissionsByModule: Record<string, Permission[]>;
  onSave: (data: RoleFormData) => Promise<void>;
  onClose: () => void;
  title: string;
}> = ({ role, permissions, permissionsByModule, onSave, onClose, title }) => {
  const { t } = useTranslation();
  const [name, setName] = useState(role?.name || '');
  const [description, setDescription] = useState(role?.description || '');
  const [selectedPermIds, setSelectedPermIds] = useState<number[]>(() => {
    if (!role) return [];
    return permissions.filter((p) => role.permissions.includes(p.code)).map((p) => p.id);
  });
  const [saving, setSaving] = useState(false);
  const isBuiltIn = role ? BUILT_IN_ROLES.includes(role.name) : false;

  const togglePermission = (permId: number) => {
    setSelectedPermIds((prev) =>
      prev.includes(permId) ? prev.filter((id) => id !== permId) : [...prev, permId]
    );
  };

  const toggleModule = (_module: string, modulePerms: Permission[]) => {
    const modulePermIds = modulePerms.map((p) => p.id);
    const allSelected = modulePermIds.every((id) => selectedPermIds.includes(id));
    if (allSelected) {
      setSelectedPermIds((prev) => prev.filter((id) => !modulePermIds.includes(id)));
    } else {
      setSelectedPermIds((prev) => [...new Set([...prev, ...modulePermIds])]);
    }
  };

  const handleSave = async () => {
    if (!name.trim()) {
      toast.error(t('roles.roleName') + ' ' + t('common.required').toLowerCase());
      return;
    }
    // Validate role name format: lowercase letters, digits, underscores, must start with a letter
    if (!/^[a-z][a-z0-9_]*$/.test(name.trim())) {
      toast.error(t('roles.invalidRoleNameFormat', 'Role name must start with a lowercase letter and contain only lowercase letters, digits, and underscores'));
      return;
    }
    setSaving(true);
    const data: RoleFormData = {
      name: name.trim(),
      description: description.trim(),
      permission_ids: selectedPermIds,
    };
    if (role) {
      // Update: only send description and permission_ids
      await onSave({ name: role.name, description: description.trim(), permission_ids: selectedPermIds });
    } else {
      await onSave(data);
    }
    setSaving(false);
  };

  return (
    <Modal isOpen={true} onClose={onClose} title={title} size="lg">
      <div className="space-y-4 max-h-[70vh] overflow-y-auto">
        {/* Role Name */}
        <div>
          <label className="block text-sm font-medium text-muted-foreground mb-1">{t('roles.roleName')}</label>
          <input
            type="text"
            value={name}
            onChange={(e) => setName(e.target.value)}
            disabled={isBuiltIn}
            className="w-full px-3 py-2 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm disabled:bg-muted disabled:cursor-not-allowed"
            placeholder="e.g. custom_role"
          />
        </div>

        {/* Description */}
        <div>
          <label className="block text-sm font-medium text-muted-foreground mb-1">{t('roles.description')}</label>
          <input
            type="text"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className="w-full px-3 py-2 border border-border rounded-lg focus:outline-none focus:ring-2 focus:ring-blue-500 text-sm"
            placeholder={t('roles.description')}
          />
        </div>

        {/* Permissions */}
        <div>
          <label className="block text-sm font-medium text-muted-foreground mb-2">{t('roles.assignPermissions')}</label>
          <div className="space-y-3">
            {Object.entries(permissionsByModule).map(([module, modulePerms]) => {
              const allSelected = modulePerms.every((p) => selectedPermIds.includes(p.id));
              const someSelected = modulePerms.some((p) => selectedPermIds.includes(p.id));

              return (
                <div key={module} className="border border-border rounded-lg overflow-hidden">
                  <button
                    type="button"
                    onClick={() => toggleModule(module, modulePerms)}
                    className={`w-full px-4 py-2.5 flex items-center justify-between text-sm font-medium transition-colors ${
                      someSelected ? 'bg-blue-50 text-blue-800' : 'bg-background text-foreground'
                    }`}
                  >
                    <div className="flex items-center gap-2">
                      {allSelected ? (
                        <CheckCircle className="h-4 w-4 text-blue-600" />
                      ) : someSelected ? (
                        <div className="h-4 w-4 rounded border-2 border-blue-400 bg-blue-100 flex items-center justify-center">
                          <div className="h-1.5 w-3 bg-blue-600 rounded-sm" />
                        </div>
                      ) : (
                        <div className="h-4 w-4 rounded border-2 border-gray-300" />
                      )}
                      {t(`roles.permissionModules.${module}`, module)}
                    </div>
                    <span className="text-xs text-muted-foreground">
                      {modulePerms.filter((p) => selectedPermIds.includes(p.id)).length}/{modulePerms.length}
                    </span>
                  </button>
                  <div className="px-4 py-2 grid grid-cols-2 gap-2 bg-card">
                    {modulePerms.map((perm) => (
                      <label key={perm.id} className="flex items-center gap-2 text-sm cursor-pointer">
                        <input
                          type="checkbox"
                          checked={selectedPermIds.includes(perm.id)}
                          onChange={() => togglePermission(perm.id)}
                          className="rounded"
                        />
                        <span className="text-foreground">{perm.name}</span>
                      </label>
                    ))}
                  </div>
                </div>
              );
            })}
          </div>
        </div>

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

export default Roles;
