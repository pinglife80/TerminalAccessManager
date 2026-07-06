import React, { useState, useEffect, useRef } from 'react';
import { useForm } from 'react-hook-form';
import { useNavigate, useLocation } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { apiClient } from '@/lib/api';
import { useAuthStore } from '@/store/auth';
import { API_ENDPOINTS } from '@/lib/constants';
import { Shield, Lock, User, AlertCircle, AlertTriangle, X, Eye, EyeOff } from 'lucide-react';
import branding from '@/config/branding';
import HeaderControls from '@/components/HeaderControls';

// Map icon names from branding config to Lucide components
const iconMap: Record<string, React.ComponentType<{ className?: string }>> = {
  Shield,
  Lock,
  User,
};

interface LoginFormData {
  username: string;
  password: string;
  captcha?: string;
}

interface CaptchaData {
  captcha_id: string;
  question: string;
}

interface AuthProvider {
  id: string;
  name: string;
  provider_type: string;
  description: string;
  enabled: boolean;
}

const Login: React.FC = () => {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const location = useLocation();
  const { login } = useAuthStore();

  const [backendError, setBackendError] = useState('');
  const [captcha, setCaptcha] = useState<CaptchaData | null>(null);
  const [captchaRequired, setCaptchaRequired] = useState(false);
  const [isLocked, setIsLocked] = useState(false);
  const [lockRemaining, setLockRemaining] = useState(0);
  const [showError, setShowError] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [loginBgUrl, setLoginBgUrl] = useState('');
  const [appVersion, setAppVersion] = useState(branding.version);
  const [loginHeading, setLoginHeading] = useState(branding.login.heading);
  const [loginFooterText, setLoginFooterText] = useState(branding.login.footerText);
  const [footerCopyright, setFooterCopyright] = useState(branding.footer.copyright);
  const [footerIcpNumber, setFooterIcpNumber] = useState(branding.footer.icpNumber);
  const [footerIcpUrl, setFooterIcpUrl] = useState(branding.footer.icpUrl);
  const [authProviders, setAuthProviders] = useState<AuthProvider[]>([]);
  const [selectedProvider, setSelectedProvider] = useState('local');
  const errorTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const { register, handleSubmit, formState: { errors } } = useForm<LoginFormData>();

  // Fetch captcha from backend
  const fetchCaptcha = async () => {
    try {
      const response = await apiClient.get(API_ENDPOINTS.AUTH_CAPTCHA);
      setCaptcha({
        captcha_id: response.data.captcha_id,
        question: response.data.question,
      });
    } catch {
      // If captcha fetch fails, generate a fallback local captcha
      // This should not happen in normal operation
      setCaptcha(null);
    }
  };

  // Load branding config (background image, favicon, footer text, ICP info) and version on mount
  useEffect(() => {
    const loadBranding = async () => {
      try {
        const response = await apiClient.get(API_ENDPOINTS.SETTINGS_BRANDING);
        const cfg = response.data;
        if (cfg.login_bg_url) {
          setLoginBgUrl(cfg.login_bg_url);
        }
        if (cfg.favicon_url) {
          let link = document.querySelector("link[rel~='icon']") as HTMLLinkElement;
          if (!link) {
            link = document.createElement('link');
            link.rel = 'icon';
            document.head.appendChild(link);
          }
          link.href = cfg.favicon_url;
        }
        if (cfg.login_heading !== undefined) {
          setLoginHeading(cfg.login_heading || branding.login.heading);
        }
        if (cfg.login_footer_text !== undefined) {
          setLoginFooterText(cfg.login_footer_text || branding.login.footerText);
        }
        if (cfg.footer_copyright !== undefined) {
          setFooterCopyright(cfg.footer_copyright || branding.footer.copyright);
        }
        if (cfg.footer_icp_number !== undefined) {
          setFooterIcpNumber(cfg.footer_icp_number ?? branding.footer.icpNumber);
        }
        if (cfg.footer_icp_url !== undefined) {
          setFooterIcpUrl(cfg.footer_icp_url || branding.footer.icpUrl);
        }
      } catch {
        // Silently use defaults
      }
    };

    const loadVersion = async () => {
      try {
        const response = await apiClient.get('/health');
        if (response.data.version) {
          setAppVersion(`v${response.data.version}`);
        }
      } catch {
        // Silently use fallback version from branding config
      }
    };

    const loadAuthProviders = async () => {
      try {
        const response = await apiClient.get(`${API_ENDPOINTS.AUTH_PROVIDERS}available`);
        setAuthProviders(response.data);
      } catch {
        // Fallback to local provider only
        setAuthProviders([{
          id: 'local',
          name: 'Local',
          provider_type: 'local',
          description: 'Local account authentication',
          enabled: true,
        }]);
      }
    };

    loadBranding();
    loadVersion();
    loadAuthProviders();
  }, []);

  // Countdown timer for lock
  useEffect(() => {
    if (!isLocked) return;
    const timer = setInterval(() => {
      setLockRemaining((prev) => {
        if (prev <= 1) {
          setIsLocked(false);
          setCaptchaRequired(false);
          setCaptcha(null);
          return 0;
        }
        return prev - 1;
      });
    }, 1000);
    return () => clearInterval(timer);
  }, [isLocked]);

  const formatTime = (seconds: number): string => {
    const m = Math.floor(seconds / 60);
    const s = seconds % 60;
    return `${m}:${s.toString().padStart(2, '0')}`;
  };

  const loginMutation = useMutation({
    mutationFn: async (data: LoginFormData) => {
      const formData = new URLSearchParams();
      formData.append('username', data.username);
      formData.append('password', data.password);

      // Pass captcha_id and captcha answer to backend if required
      const params: Record<string, string> = {
        provider: selectedProvider,
      };
      if (captcha && data.captcha) {
        params.captcha_id = captcha.captcha_id;
        params.captcha = data.captcha;
      }

      const response = await apiClient.post(API_ENDPOINTS.AUTH_LOGIN, formData.toString(), {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        params,
      });

      const { access_token, refresh_token } = response.data;

      sessionStorage.setItem('access_token', access_token);
      sessionStorage.setItem('refresh_token', refresh_token);

      const userResponse = await apiClient.get(API_ENDPOINTS.AUTH_ME, {
        headers: { Authorization: `Bearer ${access_token}` }
      });

      return {
        user: userResponse.data,
        access_token,
        refresh_token,
      };
    },
    onSuccess: (data) => {
      // Reset captcha and lock state on success
      setCaptchaRequired(false);
      setCaptcha(null);
      setIsLocked(false);
      login(data.user, data.access_token, data.refresh_token);

      const from = (location.state as { from?: { pathname: string } } | null)?.from?.pathname || '/dashboard';
      navigate(from, { replace: true });
    },
    onError: async (error: unknown) => {
      const axiosError = error as { response?: { status?: number; data?: { detail?: string | { message?: string; captcha_required?: boolean; locked?: boolean; lock_remaining?: number } } } };
      const response = axiosError.response;
      const statusCode = response?.status;

      // Parse error detail - backend returns structured JSON in detail field
      const errorDetail = response?.data?.detail;
      const isStructuredError = typeof errorDetail === 'object' && errorDetail !== null;
      const serverMessage = isStructuredError ? (errorDetail as { message?: string }).message : (errorDetail as string) || '';
      const captchaRequiredFromError = isStructuredError ? (errorDetail as { captcha_required?: boolean }).captcha_required : false;
      const lockedFromError = isStructuredError ? (errorDetail as { locked?: boolean }).locked : false;
      const lockRemainingFromError = isStructuredError ? (errorDetail as { lock_remaining?: number }).lock_remaining : 0;

      // Map backend error details to user-friendly messages
      let friendlyMessage: string;
      if (statusCode === 401) {
        friendlyMessage = t('auth.authenticationFailed');
      } else if (statusCode === 423) {
        friendlyMessage = serverMessage || t('auth.accountTemporarilyLocked');
      } else if (statusCode === 400) {
        friendlyMessage = serverMessage || t('auth.invalidRequest');
      } else if (statusCode === 403) {
        friendlyMessage = t('auth.accountDisabled');
      } else if (statusCode === 429) {
        friendlyMessage = t('auth.tooManyRequests');
      } else {
        friendlyMessage = serverMessage || t('auth.loginFailed');
      }

      setBackendError(friendlyMessage);
      setShowError(true);

      // Update captcha/lock state from error response body
      if (captchaRequiredFromError) {
        setCaptchaRequired(true);
        await fetchCaptcha();
      }

      if (lockedFromError || statusCode === 423) {
        setIsLocked(true);
        setLockRemaining(lockRemainingFromError || 900);
      }

      // Handle 400 captcha required
      if (statusCode === 400) {
        setCaptchaRequired(true);
        await fetchCaptcha();
      }
    },
  });

  // Clean up timeout on unmount
  useEffect(() => {
    return () => {
      if (errorTimeoutRef.current) {
        clearTimeout(errorTimeoutRef.current);
      }
    };
  }, []);

  const onSubmit = (data: LoginFormData) => {
    // Only clear previous error when user submits again
    setBackendError('');
    setShowError(false);

    if (isLocked) return;

    // Captcha validation is done server-side
    // Just submit the form data with captcha_id + captcha answer
    loginMutation.mutate(data);
  };

  return (
    <div className="relative min-h-screen bg-background">
      {/* Top-right controls */}
      <div className="absolute top-4 right-4 z-10">
        <HeaderControls />
      </div>
      <div className={`min-h-screen flex items-center justify-center p-4 ${
        loginBgUrl ? 'bg-cover bg-center bg-no-repeat' : ''
      }`}
      style={loginBgUrl ? {
        backgroundImage: `url(${loginBgUrl})`,
      } : branding.login.background.type === 'image' ? {
        backgroundImage: `url(${branding.login.background.imagePath})`,
      } : undefined}
      >
      <div className="w-full max-w-md">
        <div className="bg-card rounded-2xl shadow-2xl overflow-hidden border border-border">
          {/* Header with colored band */}
          <div className={`bg-gradient-to-r ${branding.login.headerGradient} px-8 pt-8 pb-12 text-center`}>
            <div className="w-20 h-20 bg-card/20 backdrop-blur rounded-full flex items-center justify-center mx-auto mb-4 ring-4 ring-white/10">
              {branding.logo.type === 'image' ? (
                <img src={branding.logo.path} alt={branding.appName} className="h-10 w-10" />
              ) : (
                (() => {
                  const IconComponent = iconMap[branding.logo.name] || Shield;
                  return <IconComponent className="h-10 w-10 text-white" />;
                })()
              )}
            </div>
            <h2 className="text-2xl font-bold text-white">{loginHeading}</h2>
            <p className="text-blue-100 mt-2">{t('auth.signInToAccount')}</p>
          </div>

          {/* Content area */}
          <div className="px-8 py-8 -mt-6">
            {/* Lock Warning - Shows above error, persistent */}
            {isLocked && (
              <div className="mb-6 bg-amber-50 dark:bg-amber-900/20 border-2 border-amber-300 dark:border-amber-700 rounded-xl p-5 shadow-sm transition-all duration-300">
                <div className="flex items-start gap-3">
                  <div className="flex-shrink-0 w-10 h-10 bg-amber-100 dark:bg-amber-800/40 rounded-lg flex items-center justify-center">
                    <AlertTriangle className="h-5 w-5 text-amber-600 dark:text-amber-400" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold text-amber-900 dark:text-amber-200">{t('auth.accountTemporarilyLocked')}</p>
                    <p className="text-sm text-amber-700 dark:text-amber-300 mt-1">
                      {t('auth.tooManyFailedAttempts')}
                    </p>
                    <div className="mt-3 flex items-center gap-2">
                      <div className="flex-1 h-2 bg-amber-200 dark:bg-amber-800 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-amber-500 dark:bg-amber-400 rounded-full transition-all duration-1000"
                          style={{ width: `${Math.max(0, (lockRemaining / 900) * 100)}%` }}
                        />
                      </div>
                      <span className="text-sm font-mono font-semibold text-amber-900 dark:text-amber-200 whitespace-nowrap">
                        {formatTime(lockRemaining)}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Backend Error Alert - Persistent, with dismiss button */}
            {showError && backendError && (
              <div className="mb-6 bg-red-50 dark:bg-red-900/20 border-2 border-red-300 dark:border-red-700 rounded-xl p-5 shadow-sm transition-all duration-300">
                <div className="flex items-start gap-3">
                  <div className="flex-shrink-0 w-10 h-10 bg-red-100 dark:bg-red-800/40 rounded-lg flex items-center justify-center">
                    <AlertCircle className="h-5 w-5 text-red-600 dark:text-red-400" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold text-red-900 dark:text-red-200">{t('auth.loginFailed')}</p>
                    <p className="text-sm text-red-700 dark:text-red-300 mt-1 break-words">{backendError}</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setShowError(false)}
                    className="flex-shrink-0 p-1 text-red-400 hover:text-red-600 dark:hover:text-red-300 hover:bg-red-100 dark:hover:bg-red-800/40 rounded-lg transition-colors"
                    aria-label={t('common.dismissError')}
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
              </div>
            )}

            <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">
              {authProviders.length > 1 && (
                <div>
                  <label className="block text-sm font-semibold text-muted-foreground mb-2">
                    {t('auth.authMethod')}
                  </label>
                  <div className="relative">
                    <select
                      value={selectedProvider}
                      onChange={(e) => setSelectedProvider(e.target.value)}
                      disabled={isLocked}
                      className={`w-full px-4 py-3 border-2 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-all text-foreground bg-background ${
                        isLocked ? 'bg-muted cursor-not-allowed opacity-60' : 'border-border focus:bg-card'
                      }`}
                    >
                      {authProviders.map((provider) => (
                        <option key={provider.id} value={provider.provider_type}>
                          {provider.name}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              )}

              <div>
                <label className="block text-sm font-semibold text-muted-foreground mb-2">
                  {t('auth.username')}
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                    <User className="h-5 w-5 text-muted-foreground" />
                  </div>
                  <input
                    {...register('username', {
                      required: t('auth.usernameRequired'),
                      minLength: { value: 3, message: t('auth.usernameMinLength') },
                      maxLength: { value: 50, message: t('auth.usernameMaxLength') },
                    })}
                    type="text"
                    disabled={isLocked}
                    autoFocus
                    className={`w-full pl-10 pr-4 py-3 border-2 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-all text-foreground bg-background placeholder-muted-foreground ${
                      errors.username ? 'border-red-400 dark:border-red-500 bg-red-50 dark:bg-red-900/20' : 'border-border focus:bg-card'
                    } ${isLocked ? 'bg-muted cursor-not-allowed opacity-60' : ''}`}
                    placeholder={t('auth.enterUsername')}
                  />
                </div>
                {errors.username && (
                  <div className="flex items-center gap-1.5 mt-2">
                    <AlertCircle className="h-3.5 w-3.5 text-red-500 flex-shrink-0" />
                    <p className="text-xs text-red-600 dark:text-red-400">{errors.username.message}</p>
                  </div>
                )}
              </div>

              <div>
                <label className="block text-sm font-semibold text-muted-foreground mb-2">
                  {t('auth.password')}
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                    <Lock className="h-5 w-5 text-muted-foreground" />
                  </div>
                  <input
                    {...register('password', {
                      required: t('auth.passwordRequired'),
                    })}
                    type={showPassword ? 'text' : 'password'}
                    disabled={isLocked}
                    className={`w-full pl-10 pr-12 py-3 border-2 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-all text-foreground bg-background placeholder-muted-foreground ${
                      errors.password ? 'border-red-400 dark:border-red-500 bg-red-50 dark:bg-red-900/20' : 'border-border focus:bg-card'
                    } ${isLocked ? 'bg-muted cursor-not-allowed opacity-60' : ''}`}
                    placeholder={t('auth.enterPassword')}
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute inset-y-0 right-0 pr-3 flex items-center text-muted-foreground hover:text-foreground transition-colors"
                    tabIndex={-1}
                  >
                    {showPassword ? <EyeOff className="h-5 w-5" /> : <Eye className="h-5 w-5" />}
                  </button>
                </div>
                {errors.password && (
                  <div className="flex items-center gap-1.5 mt-2">
                    <AlertCircle className="h-3.5 w-3.5 text-red-500 flex-shrink-0" />
                    <p className="text-xs text-red-600 dark:text-red-400">{errors.password.message}</p>
                  </div>
                )}
              </div>

              {/* Captcha Field - Only shown when backend requires it */}
              {captcha && captchaRequired && !isLocked && (
                <div className="bg-blue-50 dark:bg-blue-900/20 border-2 border-blue-200 dark:border-blue-700 rounded-xl p-5">
                  <label className="block text-sm font-semibold text-blue-900 dark:text-blue-300 mb-3 flex items-center gap-2">
                    <Shield className="h-4 w-4" />
                    {t('auth.captchaVerification')}
                  </label>
                  <div className="flex items-center gap-3">
                    <div className="bg-card border-2 border-blue-300 dark:border-blue-600 rounded-xl px-5 py-3 text-xl font-mono font-bold text-blue-900 dark:text-blue-300 shadow-inner select-none">
                      {captcha.question} = ?
                    </div>
                    <input
                      {...register('captcha', { required: captchaRequired ? t('auth.captchaAnswer') : false })}
                      type="number"
                      className="w-24 px-4 py-3 border-2 border-border rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none text-center text-xl font-mono bg-background focus:bg-card transition-all"
                      placeholder="?"
                      autoComplete="off"
                    />
                  </div>
                  {errors.captcha && (
                    <div className="flex items-center gap-1.5 mt-2">
                      <AlertCircle className="h-3.5 w-3.5 text-red-500 flex-shrink-0" />
                      <p className="text-xs text-red-600 dark:text-red-400">{errors.captcha.message}</p>
                    </div>
                  )}
                  <p className="text-xs text-blue-700 dark:text-blue-400 mt-3 flex items-center gap-1.5">
                    <AlertTriangle className="h-3.5 w-3.5" />
                    {t('auth.multipleFailedAttempts')}
                  </p>
                </div>
              )}

              <button
                type="submit"
                disabled={loginMutation.isPending || isLocked}
                className={`w-full bg-gradient-to-r ${branding.login.buttonGradient} text-white py-3.5 px-4 rounded-xl font-semibold text-sm shadow-lg hover:shadow-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 focus:ring-offset-card disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:shadow-lg transition-all transform hover:-translate-y-0.5 active:translate-y-0`}
              >
                {loginMutation.isPending ? (
                  <span className="flex items-center justify-center gap-2">
                    <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                    </svg>
                    {t('auth.signingIn')}
                  </span>
                ) : isLocked ? (
                  <span className="flex items-center justify-center gap-2">
                    <Lock className="h-4 w-4" />
                    {t('auth.locked')} ({formatTime(lockRemaining)})
                  </span>
                ) : (
                  t('auth.signIn')
                )}
              </button>

              {selectedProvider === 'local' && (isLocked || captchaRequired) && (
                <div className="mt-4 text-center">
                  <button
                    type="button"
                    onClick={() => {
                      const usernameInput = document.querySelector('input[name="username"]') as HTMLInputElement | null;
                      const username = usernameInput?.value || '';
                      navigate(username ? `/password-reset?username=${encodeURIComponent(username)}` : '/password-reset');
                    }}
                    className="text-sm text-blue-600 hover:text-blue-700 transition-colors"
                  >
                    {t('auth.forgotPassword')}
                  </button>
                </div>
              )}
            </form>

            {/* Captcha/Lock status indicator */}
            {captchaRequired && !isLocked && (
              <div className="mt-6 bg-blue-50 dark:bg-blue-900/20 border border-blue-200 dark:border-blue-700 rounded-lg p-3">
                <div className="flex items-center gap-2 text-xs text-blue-700 dark:text-blue-400">
                  <Shield className="h-3.5 w-3.5" />
                  <span>{t('auth.securityVerificationActive')}</span>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Footer text */}
        <p className="text-center text-xs text-muted-foreground mt-6">
          {loginFooterText || t('auth.secureAuthFooter')}
        </p>
        {/* Footer info */}
        <div className="flex flex-col sm:flex-row items-center justify-center gap-2 text-xs text-muted-foreground mt-3">
          <span>{footerCopyright.replace('{year}', String(new Date().getFullYear()))}</span>
          <span className="hidden sm:inline">|</span>
          <span>{appVersion}</span>
          {footerIcpNumber && (
            <>
              <span className="hidden sm:inline">|</span>
              <a
                href={footerIcpUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="hover:text-foreground transition-colors"
              >
                {footerIcpNumber}
              </a>
            </>
          )}
        </div>
      </div>
    </div>
    </div>
  );
};

export default Login;
