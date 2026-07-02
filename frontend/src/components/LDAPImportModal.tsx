import React, { useState, useEffect } from 'react';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { apiClient } from '@/lib/api';
import { API_ENDPOINTS } from '@/lib/constants';
import { getErrorMessage } from '@/lib/utils';
import { Search, Download, CheckSquare, Square, ChevronDown, ChevronUp, Users, Filter, AlertCircle } from 'lucide-react';
import { toast } from 'sonner';
import PrimaryButton from '@/components/Button';
import { Modal } from '@/components/Modal';

interface LDAPUser {
  dn: string;
  cn: string;
  username: string;
  email: string;
  givenName?: string;
  sn?: string;
}

interface LDAPOU {
  dn: string;
  name: string;
  description?: string;
}

interface LDAPImportModalProps {
  isOpen: boolean;
  onClose: () => void;
  onImportSuccess: () => void;
}

interface SearchFormData {
  searchBase: string;
  searchFilter: string;
  username: string;
  group: string;
}

const LDAPImportModal: React.FC<LDAPImportModalProps> = ({ isOpen, onClose, onImportSuccess }) => {
  const { t } = useTranslation();
  const [users, setUsers] = useState<LDAPUser[]>([]);
  const [ous, setOus] = useState<LDAPOU[]>([]);
  const [selectedUsers, setSelectedUsers] = useState<string[]>([]);
  const [selectedRole, setSelectedRole] = useState<number | null>(null);
  const [roles, setRoles] = useState<{ id: number; name: string }[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [isImporting, setIsImporting] = useState(false);
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [pageNumber, setPageNumber] = useState(1);
  const [totalUsers, setTotalUsers] = useState(0);
  const [importPreview, setImportPreview] = useState(false);

  const { register, handleSubmit, reset } = useForm<SearchFormData>({
    defaultValues: {
      searchBase: '',
      searchFilter: '',
      username: '',
      group: '',
    },
  });

  useEffect(() => {
    if (isOpen) {
      loadRoles();
      loadOus();
    } else {
      reset();
      setUsers([]);
      setSelectedUsers([]);
      setSelectedRole(null);
      setPageNumber(1);
      setImportPreview(false);
    }
  }, [isOpen, reset]);

  const loadRoles = async () => {
    try {
      const response = await apiClient.get(API_ENDPOINTS.ROLES);
      setRoles(response.data
        .map((r: any) => ({ id: r.id, name: r.name }))
        .filter((r: any) => r.name.toLowerCase() !== 'superadmin')
      );
    } catch (err) {
      toast.error(getErrorMessage(err, t('common.errorLoadingData')));
    }
  };

  const loadOus = async () => {
    try {
      const response = await apiClient.get('/ldap/ous');
      setOus(response.data);
    } catch (err) {
    }
  };

  const onSearch = async (data: SearchFormData) => {
    setIsLoading(true);
    setPageNumber(1);
    setSelectedUsers([]);
    try {
      let search_filter = '';
      if (data.group) {
        search_filter = `(memberOf=${data.group})`;
      } else if (data.searchFilter) {
        search_filter = data.searchFilter;
      }

      const response = await apiClient.post('/ldap/search', {
        search_base: data.searchBase || undefined,
        search_filter: search_filter || undefined,
        username: data.username || undefined,
        page_size: 50,
        page_number: 1,
      });
      setUsers(response.data.users);
      setTotalUsers(response.data.total);
    } catch (err) {
      toast.error(getErrorMessage(err, t('users.failedToSearchLDAP')));
    } finally {
      setIsLoading(false);
    }
  };

  const loadMore = async () => {
    if (users.length >= totalUsers) return;
    setIsLoading(true);
    try {
      const response = await apiClient.post('/ldap/search', {
        page_size: 50,
        page_number: pageNumber + 1,
      });
      setUsers(prev => [...prev, ...response.data.users]);
      setPageNumber(prev => prev + 1);
    } catch (err) {
      toast.error(getErrorMessage(err, t('users.failedToSearchLDAP')));
    } finally {
      setIsLoading(false);
    }
  };

  const toggleUserSelection = (dn: string) => {
    setSelectedUsers(prev =>
      prev.includes(dn) ? prev.filter(d => d !== dn) : [...prev, dn]
    );
  };

  const toggleAllUsers = () => {
    if (selectedUsers.length === users.length) {
      setSelectedUsers([]);
    } else {
      setSelectedUsers(users.map(u => u.dn));
    }
  };

  const selectRole = (roleId: number) => {
    setSelectedRole(prev => prev === roleId ? null : roleId);
  };

  const handleImport = async () => {
    if (selectedUsers.length === 0) {
      toast.warning(t('users.selectUsersToImport'));
      return;
    }

    setImportPreview(true);
  };

  const confirmImport = async () => {
    setIsImporting(true);
    try {
      const response = await apiClient.post('/ldap/import', {
        user_dns: selectedUsers,
        role_ids: selectedRole ? [selectedRole] : [],
      });
      toast.success(response.data.message);
      onImportSuccess();
      onClose();
    } catch (err) {
      toast.error(getErrorMessage(err, t('users.failedToImportUsers')));
    } finally {
      setIsImporting(false);
      setImportPreview(false);
    }
  };

  return (
    <Modal isOpen={isOpen} onClose={onClose} title={t('users.importLDAPUsers')} size="xl">
      <div className="space-y-4">
        {!importPreview ? (
          <>
            <form onSubmit={handleSubmit(onSearch)} className="space-y-4">
              <div className="relative">
                <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-muted-foreground" />
                <input
                  {...register('username')}
                  type="text"
                  placeholder={t('users.searchUsername')}
                  className="w-full pl-10 pr-4 py-2 border border-border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none bg-background"
                />
              </div>

              <button
                type="button"
                onClick={() => setShowAdvanced(!showAdvanced)}
                className="text-sm text-blue-600 hover:text-blue-700 flex items-center gap-1"
              >
                <Filter className="h-4 w-4" />
                {showAdvanced ? t('users.hideAdvanced') : t('users.showAdvanced')}
                {showAdvanced ? (
                  <ChevronUp className="h-4 w-4" />
                ) : (
                  <ChevronDown className="h-4 w-4" />
                )}
              </button>

              {showAdvanced && (
                <div className="space-y-3 bg-gray-50 p-4 rounded-lg">
                  <div>
                    <label className="block text-sm font-medium text-muted-foreground mb-1">
                      {t('users.searchBase')}
                    </label>
                    <select
                      {...register('searchBase')}
                      className="w-full px-4 py-2 border border-border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none bg-background"
                    >
                      <option value="">{t('users.defaultSearchBase')}</option>
                      {ous.map(ou => (
                        <option key={ou.dn} value={ou.dn}>
                          {ou.name}
                          {ou.description && ` - ${ou.description}`}
                        </option>
                      ))}
                    </select>
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-muted-foreground mb-1">
                      {t('users.group')}
                    </label>
                    <input
                      {...register('group')}
                      type="text"
                      placeholder="CN=Developers,OU=Groups..."
                      className="w-full px-4 py-2 border border-border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none bg-background"
                    />
                  </div>
                  <div>
                    <label className="block text-sm font-medium text-muted-foreground mb-1">
                      {t('users.searchFilter')}
                    </label>
                    <input
                      {...register('searchFilter')}
                      type="text"
                      placeholder={t('users.searchFilterPlaceholder')}
                      className="w-full px-4 py-2 border border-border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none bg-background"
                    />
                  </div>
                </div>
              )}

              <PrimaryButton
                type="submit"
                label={t('users.search')}
                loading={isLoading}
                icon={Search}
              />
            </form>

            {users.length > 0 && (
              <div className="space-y-4">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-4">
                    <span className="text-sm text-muted-foreground">
                      {t('users.foundUsers', { count: totalUsers })}
                    </span>
                    <span className="text-sm text-muted-foreground">
                      {t('users.selectedCount', { count: selectedUsers.length })}
                    </span>
                  </div>
                  <button
                    onClick={toggleAllUsers}
                    className="text-sm text-blue-600 hover:text-blue-700"
                  >
                    {selectedUsers.length === users.length
                      ? t('users.deselectAll')
                      : t('users.selectAll')}
                  </button>
                </div>

                <div className="max-h-72 overflow-y-auto border border-border rounded-lg">
                  <table className="w-full">
                    <thead className="bg-gray-50 sticky top-0">
                      <tr>
                        <th className="px-4 py-2 text-left text-xs font-medium text-muted-foreground w-12">
                          <input
                            type="checkbox"
                            checked={selectedUsers.length === users.length && users.length > 0}
                            onChange={toggleAllUsers}
                            className="rounded border-border text-blue-600 focus:ring-blue-500"
                          />
                        </th>
                        <th className="px-4 py-2 text-left text-xs font-medium text-muted-foreground">
                          {t('users.username')}
                        </th>
                        <th className="px-4 py-2 text-left text-xs font-medium text-muted-foreground">
                          {t('users.displayName')}
                        </th>
                        <th className="px-4 py-2 text-left text-xs font-medium text-muted-foreground">
                          {t('common.email')}
                        </th>
                      </tr>
                    </thead>
                    <tbody>
                      {users.map(user => (
                        <tr
                          key={user.dn}
                          className={`border-t hover:bg-gray-50 ${
                            selectedUsers.includes(user.dn) ? 'bg-blue-50' : ''
                          }`}
                        >
                          <td className="px-4 py-2">
                            <button
                              onClick={() => toggleUserSelection(user.dn)}
                              className="focus:outline-none"
                            >
                              {selectedUsers.includes(user.dn) ? (
                                <CheckSquare className="h-4 w-4 text-blue-600" />
                              ) : (
                                <Square className="h-4 w-4 text-muted-foreground" />
                              )}
                            </button>
                          </td>
                          <td className="px-4 py-2 text-sm text-foreground font-medium">
                            {user.username}
                          </td>
                          <td className="px-4 py-2 text-sm text-foreground">
                            {user.cn || user.givenName}
                          </td>
                          <td className="px-4 py-2 text-sm text-muted-foreground">
                            {user.email || '-'}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>

                {users.length < totalUsers && (
                  <div className="text-center">
                    <button
                      onClick={loadMore}
                      disabled={isLoading}
                      className="text-sm text-blue-600 hover:text-blue-700 disabled:text-muted-foreground"
                    >
                      {isLoading ? t('common.loading') : t('users.loadMore')}
                    </button>
                  </div>
                )}

                <div className="space-y-3">
                  <label className="block text-sm font-medium text-muted-foreground">
                    {t('users.assignRole')}
                  </label>
                  <div className="flex flex-wrap gap-2">
                    {roles.map(role => (
                      <button
                        key={role.id}
                        onClick={() => selectRole(role.id)}
                        className={`px-3 py-1 rounded-full text-sm font-medium transition-all ${
                          selectedRole === role.id
                            ? 'bg-blue-100 text-blue-700 border border-blue-200 ring-2 ring-blue-500'
                            : 'bg-gray-100 text-gray-700 border border-gray-200 hover:bg-gray-200'
                        }`}
                      >
                        {role.name}
                      </button>
                    ))}
                  </div>
                </div>

                <div className="flex gap-3">
                  <PrimaryButton
                    label={t('common.cancel')}
                    onClick={onClose}
                    variant="secondary"
                  />
                  <PrimaryButton
                    label={t('users.import')}
                    loading={isImporting}
                    icon={Download}
                    onClick={handleImport}
                    disabled={selectedUsers.length === 0}
                  />
                </div>
              </div>
            )}

            {users.length === 0 && !isLoading && (
              <div className="text-center py-8">
                <Users className="h-12 w-12 text-muted-foreground mx-auto mb-4" />
                <p className="text-muted-foreground">{t('users.noUsersFound')}</p>
                <p className="text-xs text-muted-foreground mt-1">
                  {t('users.useSearchToFind')}
                </p>
              </div>
            )}
          </>
        ) : (
          <div className="space-y-4">
            <div className="bg-blue-50 border border-blue-200 rounded-lg p-4">
              <h3 className="font-medium text-blue-800 flex items-center gap-2">
                <AlertCircle className="h-5 w-5" />
                {t('users.confirmImport')}
              </h3>
              <p className="text-sm text-blue-700 mt-2">
                {t('users.aboutToImport', { count: selectedUsers.length })}
              </p>
            </div>

            <div className="border border-border rounded-lg overflow-hidden">
              <div className="bg-gray-50 px-4 py-2">
                <span className="text-sm font-medium text-muted-foreground">
                  {t('users.selectedUsers')} ({selectedUsers.length})
                </span>
              </div>
              <div className="max-h-48 overflow-y-auto">
                <table className="w-full">
                  <tbody>
                    {users.filter(u => selectedUsers.includes(u.dn)).map(user => (
                      <tr key={user.dn} className="border-t">
                        <td className="px-4 py-2 text-sm text-foreground">{user.username}</td>
                        <td className="px-4 py-2 text-sm text-muted-foreground">{user.email || '-'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>

            {selectedRole !== null && (
              <div className="bg-gray-50 border border-border rounded-lg p-3">
                <span className="text-sm text-muted-foreground">{t('users.roleToAssign')}:</span>
                <div className="flex flex-wrap gap-2 mt-2">
                  {(() => {
                    const role = roles.find(r => r.id === selectedRole);
                    return role ? (
                      <span
                        key={selectedRole}
                        className="px-2 py-1 bg-blue-100 text-blue-700 rounded text-xs"
                      >
                        {role.name}
                      </span>
                    ) : null;
                  })()}
                </div>
              </div>
            )}

            <div className="flex gap-3">
              <PrimaryButton
                label={t('common.back')}
                onClick={() => setImportPreview(false)}
                variant="secondary"
              />
              <PrimaryButton
                label={t('users.confirm')}
                loading={isImporting}
                icon={Download}
                onClick={confirmImport}
              />
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
};

export default LDAPImportModal;