import React, { useState } from 'react';
import { useForm } from 'react-hook-form';
import { useNavigate, useLocation } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { apiClient } from '@/lib/api';
import { Shield, Mail, Lock, AlertCircle, ArrowLeft, Eye, EyeOff, User } from 'lucide-react';
import { toast } from 'sonner';
import branding from '@/config/branding';
import HeaderControls from '@/components/HeaderControls';

type ResetStep = 'request' | 'verify';

interface RequestFormData {
  username: string;
}

interface VerifyFormData {
  username: string;
  email: string;
  code: string;
  new_password: string;
}

const maskEmail = (email: string): string => {
  const parts = email.split('@');
  if (parts.length !== 2) return email;
  const local = parts[0];
  const domain = parts[1];
  if (local.length <= 2) return email;
  return `${local.slice(0, 2)}***@${domain}`;
};

const PasswordReset: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const [step, setStep] = useState<ResetStep>('request');
  const [showPassword, setShowPassword] = useState(false);
  const [requestUsername, setRequestUsername] = useState('');
  const [requestEmail, setRequestEmail] = useState('');
  const [countdown, setCountdown] = useState(0);

  const usernameFromUrl = new URLSearchParams(location.search).get('username') || '';

  const requestForm = useForm<RequestFormData>({
    defaultValues: {
      username: usernameFromUrl,
    },
  });

  const verifyForm = useForm<VerifyFormData>({
    defaultValues: {
      username: '',
      email: '',
    },
  });

  const requestMutation = useMutation({
    mutationFn: async (data: RequestFormData) => {
      const response = await apiClient.post('/auth/password-reset/request', data);
      return response.data;
    },
    onSuccess: (response) => {
      const username = requestForm.getValues('username');
      const email = response.email || '';
      setRequestUsername(username);
      setRequestEmail(email);
      verifyForm.reset({
        username,
        email,
        code: '',
        new_password: '',
      });
      setStep('verify');
      setCountdown(60);
    },
    onError: (error: unknown) => {
      const axiosError = error as { response?: { data?: { detail?: string } } };
      const message = axiosError.response?.data?.detail || t('auth.passwordResetFailed');
      requestForm.setError('username', { message });
    },
  });

  const verifyMutation = useMutation({
    mutationFn: async (data: VerifyFormData) => {
      await apiClient.post('/auth/password-reset/verify', {
        username: data.username,
        email: data.email,
        code: data.code,
        new_password: data.new_password,
      });
    },
    onSuccess: () => {
      toast.success(t('auth.passwordResetSuccess'));
      setTimeout(() => {
        navigate('/login');
      }, 2000);
    },
    onError: (error: unknown) => {
      const axiosError = error as { response?: { data?: { detail?: string } } };
      const message = axiosError.response?.data?.detail || t('auth.passwordResetFailed');
      verifyForm.setError('code', { message });
    },
  });

  React.useEffect(() => {
    if (countdown <= 0) return;
    const timer = setInterval(() => {
      setCountdown((prev) => {
        if (prev <= 1) {
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [countdown]);

  const handleRequestSubmit = (data: RequestFormData) => {
    requestMutation.mutate(data);
  };

  const handleVerifySubmit = (data: VerifyFormData) => {
    verifyMutation.mutate(data);
  };

  const handleResendCode = () => {
    requestMutation.mutate({ username: requestUsername });
  };

  return (
    <div className="relative min-h-screen bg-background">
      <div className="absolute top-4 right-4 z-10">
        <HeaderControls />
      </div>
      <div className={`min-h-screen flex items-center justify-center p-4 ${
        branding.login.background.type === 'image' ? 'bg-cover bg-center bg-no-repeat' : ''
      }`}
        style={branding.login.background.type === 'image' ? {
          backgroundImage: `url(${branding.login.background.imagePath})`,
        } : undefined}
      >
        <div className="w-full max-w-md">
          <div className="bg-card rounded-2xl shadow-2xl overflow-hidden border border-border">
            <div className={`bg-gradient-to-r ${branding.login.headerGradient} px-8 pt-8 pb-12 text-center`}>
              <div className="w-20 h-20 bg-card/20 backdrop-blur rounded-full flex items-center justify-center mx-auto mb-4 ring-4 ring-white/10">
                <Lock className="h-10 w-10 text-white" />
              </div>
              <h2 className="text-2xl font-bold text-white">
                {step === 'request' ? t('auth.forgotPassword') : t('auth.resetPassword')}
              </h2>
              <p className="text-blue-100 mt-2">
                {step === 'request' ? t('auth.enterUsernameToReset') : t('auth.enterCodeAndNewPassword')}
              </p>
            </div>

            <div className="px-8 py-8 -mt-6">
              {step === 'verify' && requestEmail && (
                <div className="mb-6 p-4 bg-green-50 border border-green-200 rounded-xl flex items-start gap-3">
                  <Mail className="h-5 w-5 text-green-600 flex-shrink-0 mt-0.5" />
                  <div>
                    <p className="text-sm font-semibold text-green-800">
                      {t('auth.verificationCodeSent')}
                    </p>
                    <p className="text-xs text-green-600 mt-1">
                      {t('auth.checkEmail', { email: maskEmail(requestEmail) })}
                    </p>
                  </div>
                </div>
              )}

              {step === 'request' && (
                <form onSubmit={requestForm.handleSubmit(handleRequestSubmit)} className="space-y-5">
                  <div>
                    <label className="block text-sm font-semibold text-muted-foreground mb-2">
                      {t('auth.username')}
                    </label>
                    <div className="relative">
                      <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                        <User className="h-5 w-5 text-muted-foreground" />
                      </div>
                      <input
                        {...requestForm.register('username', {
                          required: t('auth.usernameRequired'),
                        })}
                        type="text"
                        className={`w-full pl-10 pr-4 py-3 border-2 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-all text-foreground bg-background placeholder-muted-foreground ${
                          requestForm.formState.errors.username ? 'border-red-400 bg-red-50' : 'border-border focus:bg-card'
                        }`}
                        placeholder={t('auth.enterUsername')}
                        autoFocus
                      />
                    </div>
                    {requestForm.formState.errors.username && (
                      <div className="flex items-center gap-1.5 mt-2">
                        <AlertCircle className="h-3.5 w-3.5 text-red-500" />
                        <p className="text-xs text-red-600">{requestForm.formState.errors.username.message}</p>
                      </div>
                    )}
                  </div>

                  <button
                    type="submit"
                    disabled={requestMutation.isPending}
                    className={`w-full bg-gradient-to-r ${branding.login.buttonGradient} text-white py-3.5 px-4 rounded-xl font-semibold text-sm shadow-lg hover:shadow-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-all transform hover:-translate-y-0.5 active:translate-y-0`}
                  >
                    {requestMutation.isPending ? (
                      <span className="flex items-center justify-center gap-2">
                        <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                        </svg>
                        {t('auth.sending')}
                      </span>
                    ) : (
                      t('auth.sendVerificationCode')
                    )}
                  </button>

                  <button
                    type="button"
                    onClick={() => navigate('/login')}
                    className="w-full flex items-center justify-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
                  >
                    <ArrowLeft className="h-4 w-4" />
                    {t('auth.backToLogin')}
                  </button>
                </form>
              )}

              {step === 'verify' && (
                <form onSubmit={verifyForm.handleSubmit(handleVerifySubmit)} className="space-y-5">
                  <div>
                    <label className="block text-sm font-semibold text-muted-foreground mb-2">
                      {t('auth.email')}
                    </label>
                    <div className="relative">
                      <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                        <Mail className="h-5 w-5 text-muted-foreground" />
                      </div>
                      <input
                        {...verifyForm.register('email')}
                        type="email"
                        readOnly
                        className="w-full pl-10 pr-4 py-3 border-2 border-border rounded-xl text-foreground bg-muted/30 placeholder-muted-foreground cursor-not-allowed"
                        placeholder={t('auth.enterEmail')}
                      />
                    </div>
                  </div>

                  <div>
                    <label className="block text-sm font-semibold text-muted-foreground mb-2">
                      {t('auth.verificationCode')}
                    </label>
                    <div className="relative">
                      <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                        <Shield className="h-5 w-5 text-muted-foreground" />
                      </div>
                      <input
                        {...verifyForm.register('code', {
                          required: t('auth.codeRequired'),
                          minLength: { value: 6, message: t('auth.codeMinLength') },
                          maxLength: { value: 6, message: t('auth.codeMaxLength') },
                        })}
                        type="text"
                        inputMode="numeric"
                        className={`w-full pl-10 pr-4 py-3 border-2 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-all text-foreground bg-background placeholder-muted-foreground font-mono text-center text-lg tracking-wider ${
                          verifyForm.formState.errors.code ? 'border-red-400 bg-red-50' : 'border-border focus:bg-card'
                        }`}
                        placeholder="000000"
                        autoFocus
                      />
                    </div>
                    {verifyForm.formState.errors.code && (
                      <div className="flex items-center gap-1.5 mt-2">
                        <AlertCircle className="h-3.5 w-3.5 text-red-500" />
                        <p className="text-xs text-red-600">{verifyForm.formState.errors.code.message}</p>
                      </div>
                    )}
                    <button
                      type="button"
                      onClick={handleResendCode}
                      disabled={countdown > 0 || requestMutation.isPending}
                      className="mt-3 text-sm text-blue-600 hover:text-blue-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      {countdown > 0 ? (
                        <span>{t('auth.resendCodeIn', { seconds: countdown })}</span>
                      ) : requestMutation.isPending ? (
                        <span>{t('auth.sending')}</span>
                      ) : (
                        <span>{t('auth.resendCode')}</span>
                      )}
                    </button>
                  </div>

                  <div>
                    <label className="block text-sm font-semibold text-muted-foreground mb-2">
                      {t('auth.newPassword')}
                    </label>
                    <div className="relative">
                      <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                        <Lock className="h-5 w-5 text-muted-foreground" />
                      </div>
                      <input
                        {...verifyForm.register('new_password', {
                          required: t('auth.passwordRequired'),
                          minLength: { value: 8, message: t('auth.passwordMinLength') },
                          pattern: {
                            value: /^(?=.*[A-Z])(?=.*[a-z])(?=.*\d)[^\s]{8,}$/,
                            message: t('auth.passwordComplexity'),
                          },
                        })}
                        type={showPassword ? 'text' : 'password'}
                        className={`w-full pl-10 pr-12 py-3 border-2 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-all text-foreground bg-background placeholder-muted-foreground ${
                          verifyForm.formState.errors.new_password ? 'border-red-400 bg-red-50' : 'border-border focus:bg-card'
                        }`}
                        placeholder={t('auth.enterNewPassword')}
                      />
                      <button
                        type="button"
                        onClick={() => setShowPassword(!showPassword)}
                        className="absolute inset-y-0 right-0 pr-3 flex items-center"
                      >
                        {showPassword ? (
                          <EyeOff className="h-5 w-5 text-muted-foreground hover:text-foreground" />
                        ) : (
                          <Eye className="h-5 w-5 text-muted-foreground hover:text-foreground" />
                        )}
                      </button>
                    </div>
                    {verifyForm.formState.errors.new_password && (
                      <div className="flex items-center gap-1.5 mt-2">
                        <AlertCircle className="h-3.5 w-3.5 text-red-500" />
                        <p className="text-xs text-red-600">{verifyForm.formState.errors.new_password.message}</p>
                      </div>
                    )}
                  </div>

                  <button
                    type="submit"
                    disabled={verifyMutation.isPending}
                    className={`w-full bg-gradient-to-r ${branding.login.buttonGradient} text-white py-3.5 px-4 rounded-xl font-semibold text-sm shadow-lg hover:shadow-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-all transform hover:-translate-y-0.5 active:translate-y-0`}
                  >
                    {verifyMutation.isPending ? (
                      <span className="flex items-center justify-center gap-2">
                        <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                          <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                        </svg>
                        {t('auth.resetting')}
                      </span>
                    ) : (
                      t('auth.resetPassword')
                    )}
                  </button>

                  <button
                    type="button"
                    onClick={() => {
                      setStep('request');
                      setCountdown(0);
                    }}
                    className="w-full flex items-center justify-center gap-2 text-sm text-muted-foreground hover:text-foreground transition-colors"
                  >
                    <ArrowLeft className="h-4 w-4" />
                    {t('auth.backToUsername')}
                  </button>
                </form>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default PasswordReset;