import React, { useState } from 'react';
import { useForm } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { useAuthStore } from '@/store/auth';
import { apiClient } from '@/lib/api';
import { API_ENDPOINTS } from '@/lib/constants';
import { getErrorMessage } from '@/lib/utils';
import { Mail, Lock, Eye, EyeOff, AlertCircle } from 'lucide-react';
import { toast } from 'sonner';
import { PrimaryButton } from '@/components/Button';

interface ProfileFormData {
  email: string;
}

interface PasswordFormData {
  current_password: string;
  new_password: string;
  confirm_password: string;
}

const Profile: React.FC = () => {
  const { t } = useTranslation();
  const { user, setUser } = useAuthStore();
  const [showCurrentPassword, setShowCurrentPassword] = useState(false);
  const [showNewPassword, setShowNewPassword] = useState(false);
  const [savingProfile, setSavingProfile] = useState(false);
  const [savingPassword, setSavingPassword] = useState(false);

  const { register: registerProfile, handleSubmit: handleProfileSubmit, formState: { errors: profileErrors } } = useForm<ProfileFormData>({
    defaultValues: { email: user?.email || '' },
  });

  const { register: registerPassword, handleSubmit: handlePasswordSubmit, formState: { errors: passwordErrors }, watch, reset: resetPassword } = useForm<PasswordFormData>();

  const newPassword = watch('new_password');

  const onProfileSubmit = async (data: ProfileFormData) => {
    setSavingProfile(true);
    try {
      const response = await apiClient.put(API_ENDPOINTS.AUTH_ME_PROFILE, { email: data.email });
      setUser(response.data);
      toast.success(t('profile.profileUpdated'));
    } catch (err: unknown) {
      toast.error(getErrorMessage(err, t('profile.failedToUpdateProfile')));
    } finally {
      setSavingProfile(false);
    }
  };

  const onPasswordSubmit = async (data: PasswordFormData) => {
    if (data.new_password !== data.confirm_password) {
      toast.error(t('profile.newPasswordsDoNotMatch'));
      return;
    }
    setSavingPassword(true);
    try {
      await apiClient.put(API_ENDPOINTS.AUTH_ME_PASSWORD, {
        current_password: data.current_password,
        new_password: data.new_password,
      });
      toast.success(t('profile.passwordChanged'));
      resetPassword();
    } catch (err: unknown) {
      toast.error(getErrorMessage(err, t('profile.failedToChangePassword')));
    } finally {
      setSavingPassword(false);
    }
  };

  const getPasswordStrength = (pw: string) => {
    if (!pw) return { level: 0, text: '', color: '' };
    let score = 0;
    if (pw.length >= 8) score++;
    if (/[A-Z]/.test(pw)) score++;
    if (/[a-z]/.test(pw)) score++;
    if (/\d/.test(pw)) score++;
    if (/[^A-Za-z0-9]/.test(pw)) score++;
    if (score <= 2) return { level: 1, text: t('profile.strengthWeak'), color: 'bg-red-500' };
    if (score <= 3) return { level: 2, text: t('profile.strengthMedium'), color: 'bg-yellow-500' };
    return { level: 3, text: t('profile.strengthStrong'), color: 'bg-green-500' };
  };

  const strength = getPasswordStrength(newPassword || '');

  return (
    <div className="min-h-full bg-background p-4 sm:p-6 lg:p-8">
      <div className="max-w-2xl mx-auto">
        {/* Page Header */}
        <div className="mb-6">
          <h1 className="text-2xl sm:text-3xl font-bold text-foreground">{t('profile.title')}</h1>
          <p className="text-muted-foreground mt-1">{t('profile.manageAccountInfo')}</p>
        </div>

        <div className="space-y-6">
          {/* Account Info Card */}
          <div className="bg-card rounded-2xl border border-border shadow-sm p-6">
            <h2 className="text-lg font-semibold text-foreground mb-4">{t('profile.accountInformation')}</h2>
            <div className="space-y-4">
              <div className="flex items-center gap-4 py-3 border-b border-border">
                <div className="w-12 h-12 rounded-full bg-blue-600 flex items-center justify-center">
                  <span className="text-lg font-bold text-white">{user?.username?.charAt(0).toUpperCase()}</span>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">{t('profile.username')}</p>
                  <p className="font-medium text-foreground">{user?.username}</p>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-4">
                <div>
                  <p className="text-sm text-muted-foreground">{t('profile.role')}</p>
                  <p className="font-medium text-foreground">
                    {user?.roles && user.roles.length > 0
                      ? user.roles.map((r) => t(`roles.${r}`, r)).join(', ')
                      : user?.is_superuser ? t('profile.administrator') : t('profile.user')}
                  </p>
                </div>
                <div>
                  <p className="text-sm text-muted-foreground">{t('profile.status')}</p>
                  <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium ${
                    user?.is_active ? 'bg-green-100 text-green-800' : 'bg-red-100 text-red-800'
                  }`}>
                    {user?.is_active ? t('common.active') : t('common.inactive')}
                  </span>
                </div>
              </div>
            </div>
          </div>

          {/* Email Update Card */}
          <div className="bg-card rounded-2xl border border-border shadow-sm p-6">
            <h2 className="text-lg font-semibold text-foreground mb-4 flex items-center gap-2">
              <Mail className="h-5 w-5 text-muted-foreground" />
              {t('profile.emailAddress')}
            </h2>
            <form onSubmit={handleProfileSubmit(onProfileSubmit)} className="space-y-4">
              <div>
                <input
                  {...registerProfile('email', {
                    pattern: {
                      value: /^[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}$/i,
                      message: t('profile.invalidEmailAddress'),
                    },
                  })}
                  type="email"
                  className="w-full px-4 py-2.5 border border-border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none bg-background focus:bg-card transition-all"
                  placeholder={t('profile.enterEmail')}
                />
                {profileErrors.email && (
                  <p className="text-xs text-red-600 mt-1">{profileErrors.email.message}</p>
                )}
              </div>
              <PrimaryButton
                type="submit"
                label={t('profile.updateEmail')}
                loading={savingProfile}
              />
            </form>
          </div>

          {/* Password Change Card */}
          <div className="bg-card rounded-2xl border border-border shadow-sm p-6">
            <h2 className="text-lg font-semibold text-foreground mb-4 flex items-center gap-2">
              <Lock className="h-5 w-5 text-muted-foreground" />
              {t('profile.changePassword')}
            </h2>
            <form onSubmit={handlePasswordSubmit(onPasswordSubmit)} className="space-y-4">
              <div>
                <label className="block text-sm font-medium text-muted-foreground mb-1">{t('profile.currentPassword')}</label>
                <div className="relative">
                  <input
                    {...registerPassword('current_password', { required: t('profile.currentPasswordRequired') })}
                    type={showCurrentPassword ? 'text' : 'password'}
                    className="w-full px-4 py-2.5 border border-border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none bg-background focus:bg-card pr-10 transition-all"
                    placeholder={t('profile.enterCurrentPassword')}
                  />
                  <button
                    type="button"
                    onClick={() => setShowCurrentPassword(!showCurrentPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-muted-foreground"
                  >
                    {showCurrentPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
                {passwordErrors.current_password && (
                  <p className="text-xs text-red-600 mt-1">{passwordErrors.current_password.message}</p>
                )}
              </div>

              <div>
                <label className="block text-sm font-medium text-muted-foreground mb-1">{t('profile.newPassword')}</label>
                <div className="relative">
                  <input
                    {...registerPassword('new_password', {
                      required: t('profile.newPasswordRequired'),
                      minLength: { value: 8, message: t('profile.atLeast8Characters') },
                      pattern: {
                        value: /^(?=.*[a-z])(?=.*[A-Z])(?=.*\d).{8,}$/,
                        message: t('profile.mustContainUpperLowerDigit'),
                      },
                    })}
                    type={showNewPassword ? 'text' : 'password'}
                    className="w-full px-4 py-2.5 border border-border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none bg-background focus:bg-card pr-10 transition-all"
                    placeholder={t('profile.enterNewPassword')}
                  />
                  <button
                    type="button"
                    onClick={() => setShowNewPassword(!showNewPassword)}
                    className="absolute right-3 top-1/2 -translate-y-1/2 text-muted-foreground hover:text-muted-foreground"
                  >
                    {showNewPassword ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
                  </button>
                </div>
                {passwordErrors.new_password && (
                  <p className="text-xs text-red-600 mt-1">{passwordErrors.new_password.message}</p>
                )}
                {/* Password strength indicator */}
                {newPassword && (
                  <div className="mt-2">
                    <div className="flex gap-1 mb-1">
                      {[1, 2, 3].map((i) => (
                        <div key={i} className={`h-1 flex-1 rounded-full ${i <= strength.level ? strength.color : 'bg-muted'}`} />
                      ))}
                    </div>
                    <p className="text-xs text-muted-foreground">{t('profile.strength')}: {strength.text}</p>
                  </div>
                )}
              </div>

              <div>
                <label className="block text-sm font-medium text-muted-foreground mb-1">{t('profile.confirmNewPassword')}</label>
                <input
                  {...registerPassword('confirm_password', {
                    required: t('profile.pleaseConfirmPassword'),
                    validate: (value) => value === newPassword || t('profile.passwordsDoNotMatch'),
                  })}
                  type="password"
                  className="w-full px-4 py-2.5 border border-border rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none bg-background focus:bg-card transition-all"
                  placeholder={t('profile.confirmNewPasswordPlaceholder')}
                />
                {passwordErrors.confirm_password && (
                  <p className="text-xs text-red-600 mt-1">{passwordErrors.confirm_password.message}</p>
                )}
              </div>

              <div className="bg-blue-50 border border-blue-200 rounded-lg p-3 flex items-start gap-2">
                <AlertCircle className="h-4 w-4 text-blue-600 flex-shrink-0 mt-0.5" />
                <p className="text-xs text-blue-700">{t('profile.passwordRequirements')}</p>
              </div>

              <PrimaryButton
                type="submit"
                label={t('profile.changePassword')}
                loading={savingPassword}
              />
            </form>
          </div>
        </div>
      </div>
    </div>
  );
};

export default Profile;
