import React, { useState, useEffect, useRef } from 'react';
import { useForm } from 'react-hook-form';
import { useNavigate, useLocation } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';
import { apiClient } from '@/lib/api';
import { useAuthStore } from '@/store/auth';
import { Shield, Lock, User, AlertCircle, AlertTriangle, X, Eye, EyeOff } from 'lucide-react';
import branding from '@/config/branding';

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

const generateCaptcha = (): { question: string; answer: number } => {
  const a = Math.floor(Math.random() * 20) + 1;
  const b = Math.floor(Math.random() * 20) + 1;
  const isAdd = Math.random() > 0.5;
  return {
    question: isAdd ? `${a} + ${b}` : `${Math.max(a, b)} - ${Math.min(a, b)}`,
    answer: isAdd ? a + b : Math.max(a, b) - Math.min(a, b),
  };
};

const Login: React.FC = () => {
  const navigate = useNavigate();
  const location = useLocation();
  const { login } = useAuthStore();

  const [backendError, setBackendError] = useState('');
  const [captcha, setCaptcha] = useState<{ question: string; answer: number } | null>(null);
  const [captchaRequired, setCaptchaRequired] = useState(false);
  const [isLocked, setIsLocked] = useState(false);
  const [lockRemaining, setLockRemaining] = useState(0);
  const [showError, setShowError] = useState(false);
  const [showPassword, setShowPassword] = useState(false);
  const [loginBgUrl, setLoginBgUrl] = useState('');
  const errorTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const { register, handleSubmit, formState: { errors }, watch } = useForm<LoginFormData>();
  const usernameValue = watch('username');

  // Load branding config (background image, favicon) on mount
  useEffect(() => {
    const loadBranding = async () => {
      try {
        const response = await apiClient.get('/settings/branding');
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
      } catch {
        // Silently use defaults
      }
    };
    loadBranding();
  }, []);

  // Check login status from backend when username changes
  useEffect(() => {
    if (!usernameValue || usernameValue.length < 2) {
      setCaptchaRequired(false);
      setIsLocked(false);
      setCaptcha(null);
      return;
    }

    const timer = setTimeout(async () => {
      try {
        const response = await apiClient.get('/auth/login-status', {
          params: { username: usernameValue },
        });
        const { captcha_required, locked, lock_remaining_seconds } = response.data;

        setCaptchaRequired(captcha_required);
        if (captcha_required && !captcha) {
          setCaptcha(generateCaptcha());
        } else if (!captcha_required) {
          setCaptcha(null);
        }

        if (locked) {
          setIsLocked(true);
          setLockRemaining(lock_remaining_seconds || 900);
        } else {
          setIsLocked(false);
        }
      } catch {
        // Silently ignore - login-status is optional
      }
    }, 500);

    return () => clearTimeout(timer);
  }, [usernameValue]);

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

      // Pass captcha answer to backend if required
      const params: Record<string, string> = {};
      if (captcha && data.captcha) {
        params.captcha = data.captcha;
      }

      const response = await apiClient.post('/auth/login', formData.toString(), {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
        params,
      });

      const { access_token, refresh_token } = response.data;

      sessionStorage.setItem('access_token', access_token);
      sessionStorage.setItem('refresh_token', refresh_token);

      const userResponse = await apiClient.get('/auth/me', {
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

      const from = (location.state as any)?.from?.pathname || '/dashboard';
      navigate(from, { replace: true });
    },
    onError: (error: any) => {
      const response = error.response;
      const statusCode = response?.status;
      const serverMessage = response?.data?.detail || '';

      // Map backend error details to user-friendly messages
      let friendlyMessage: string;
      if (statusCode === 401) {
        // Distinguish between username not found and wrong password
        if (serverMessage === 'Username does not exist') {
          friendlyMessage = 'Username does not exist';
        } else if (serverMessage === 'Incorrect password') {
          friendlyMessage = 'Incorrect password';
        } else {
          friendlyMessage = serverMessage || 'Authentication failed';
        }
      } else if (statusCode === 423) {
        friendlyMessage = serverMessage || 'Account is temporarily locked';
      } else if (statusCode === 400) {
        friendlyMessage = serverMessage || 'Invalid request';
      } else if (statusCode === 403) {
        friendlyMessage = 'Account is disabled';
      } else if (statusCode === 429) {
        friendlyMessage = 'Too many requests, please try again later';
      } else {
        friendlyMessage = serverMessage || 'Login failed';
      }

      setBackendError(friendlyMessage);
      setShowError(true);

      // Update captcha/lock state from backend response headers
      const headers = response?.headers || {};
      const captchaRequiredHeader = headers['x-captcha-required'];
      const lockedHeader = headers['x-account-locked'];
      const lockRemainingHeader = headers['x-lock-remaining'];

      if (captchaRequiredHeader === 'true') {
        setCaptchaRequired(true);
        if (!captcha) {
          setCaptcha(generateCaptcha());
        } else {
          // Refresh captcha on failure
          setCaptcha(generateCaptcha());
        }
      }

      if (lockedHeader === 'true') {
        setIsLocked(true);
        setLockRemaining(parseInt(lockRemainingHeader || '900', 10));
      }

      // Handle 423 locked status
      if (response?.status === 423) {
        setIsLocked(true);
        setLockRemaining(parseInt(lockRemainingHeader || '900', 10));
      }

      // Handle 400 captcha required
      if (response?.status === 400) {
        setCaptchaRequired(true);
        if (!captcha) {
          setCaptcha(generateCaptcha());
        }
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

    // Validate captcha locally before sending to backend
    if (captcha && captchaRequired) {
      const userAnswer = parseInt(data.captcha || '', 10);
      if (isNaN(userAnswer) || userAnswer !== captcha.answer) {
        setBackendError('Incorrect captcha answer. Please try again.');
        setShowError(true);
        setCaptcha(generateCaptcha());
        return;
      }
    }

    loginMutation.mutate(data);
  };

  return (
    <div className={`min-h-screen flex items-center justify-center p-4 ${
      loginBgUrl ? 'bg-cover bg-center bg-no-repeat' : branding.login.background.gradientClass
    }`}
    style={loginBgUrl ? {
      backgroundImage: `url(${loginBgUrl})`,
    } : branding.login.background.type === 'image' ? {
      backgroundImage: `url(${branding.login.background.imagePath})`,
    } : undefined}
    >
      <div className="w-full max-w-md">
        <div className="bg-white rounded-2xl shadow-2xl overflow-hidden">
          {/* Header with colored band */}
          <div className={`bg-gradient-to-r ${branding.login.headerGradient} px-8 pt-8 pb-12 text-center`}>
            <div className="w-20 h-20 bg-white/20 backdrop-blur rounded-full flex items-center justify-center mx-auto mb-4 ring-4 ring-white/10">
              {branding.logo.type === 'image' ? (
                <img src={branding.logo.path} alt={branding.appName} className="h-10 w-10" />
              ) : (
                (() => {
                  const IconComponent = iconMap[branding.logo.name] || Shield;
                  return <IconComponent className="h-10 w-10 text-white" />;
                })()
              )}
            </div>
            <h2 className="text-2xl font-bold text-white">{branding.login.heading}</h2>
            <p className="text-blue-100 mt-2">{branding.login.subheading}</p>
          </div>

          {/* Content area */}
          <div className="px-8 py-8 -mt-6">
            {/* Lock Warning - Shows above error, persistent */}
            {isLocked && (
              <div className="mb-6 bg-gradient-to-r from-orange-50 to-amber-50 border-2 border-orange-300 rounded-xl p-5 shadow-sm transition-all duration-300">
                <div className="flex items-start gap-3">
                  <div className="flex-shrink-0 w-10 h-10 bg-orange-100 rounded-lg flex items-center justify-center">
                    <AlertTriangle className="h-5 w-5 text-orange-600" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold text-orange-900">Account Temporarily Locked</p>
                    <p className="text-sm text-orange-700 mt-1">
                      Too many failed login attempts. Please wait
                    </p>
                    <div className="mt-3 flex items-center gap-2">
                      <div className="flex-1 h-2 bg-orange-200 rounded-full overflow-hidden">
                        <div
                          className="h-full bg-orange-500 rounded-full transition-all duration-1000"
                          style={{ width: `${Math.max(0, (lockRemaining / 900) * 100)}%` }}
                        />
                      </div>
                      <span className="text-sm font-mono font-semibold text-orange-900 whitespace-nowrap">
                        {formatTime(lockRemaining)}
                      </span>
                    </div>
                  </div>
                </div>
              </div>
            )}

            {/* Backend Error Alert - Persistent, with dismiss button */}
            {showError && backendError && (
              <div className="mb-6 bg-gradient-to-r from-red-50 to-rose-50 border-2 border-red-300 rounded-xl p-5 shadow-sm transition-all duration-300">
                <div className="flex items-start gap-3">
                  <div className="flex-shrink-0 w-10 h-10 bg-red-100 rounded-lg flex items-center justify-center">
                    <AlertCircle className="h-5 w-5 text-red-600" />
                  </div>
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-semibold text-red-900">Login Failed</p>
                    <p className="text-sm text-red-700 mt-1 break-words">{backendError}</p>
                  </div>
                  <button
                    type="button"
                    onClick={() => setShowError(false)}
                    className="flex-shrink-0 p-1 text-red-400 hover:text-red-600 hover:bg-red-100 rounded-lg transition-colors"
                    aria-label="Dismiss error"
                  >
                    <X className="h-4 w-4" />
                  </button>
                </div>
              </div>
            )}

            <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">
              <div>
                <label className="block text-sm font-semibold text-gray-700 mb-2">
                  Username
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                    <User className="h-5 w-5 text-gray-400" />
                  </div>
                  <input
                    {...register('username', {
                      required: 'Username is required',
                      minLength: { value: 3, message: 'Username must be at least 3 characters' },
                      maxLength: { value: 50, message: 'Username must be at most 50 characters' },
                    })}
                    type="text"
                    disabled={isLocked}
                    autoFocus
                    className={`w-full pl-10 pr-4 py-3 border-2 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-all text-gray-900 placeholder-gray-400 ${
                      errors.username ? 'border-red-400 bg-red-50' : 'border-gray-200 bg-gray-50 focus:bg-white'
                    } ${isLocked ? 'bg-gray-100 cursor-not-allowed opacity-60' : ''}`}
                    placeholder="Enter your username"
                  />
                </div>
                {errors.username && (
                  <div className="flex items-center gap-1.5 mt-2">
                    <AlertCircle className="h-3.5 w-3.5 text-red-500 flex-shrink-0" />
                    <p className="text-xs text-red-600">{errors.username.message}</p>
                  </div>
                )}
              </div>

              <div>
                <label className="block text-sm font-semibold text-gray-700 mb-2">
                  Password
                </label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                    <Lock className="h-5 w-5 text-gray-400" />
                  </div>
                  <input
                    {...register('password', {
                      required: 'Password is required',
                    })}
                    type={showPassword ? 'text' : 'password'}
                    disabled={isLocked}
                    className={`w-full pl-10 pr-12 py-3 border-2 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-all text-gray-900 placeholder-gray-400 ${
                      errors.password ? 'border-red-400 bg-red-50' : 'border-gray-200 bg-gray-50 focus:bg-white'
                    } ${isLocked ? 'bg-gray-100 cursor-not-allowed opacity-60' : ''}`}
                    placeholder="Enter your password"
                  />
                  <button
                    type="button"
                    onClick={() => setShowPassword(!showPassword)}
                    className="absolute inset-y-0 right-0 pr-3 flex items-center text-gray-400 hover:text-gray-600 transition-colors"
                    tabIndex={-1}
                  >
                    {showPassword ? <EyeOff className="h-5 w-5" /> : <Eye className="h-5 w-5" />}
                  </button>
                </div>
                {errors.password && (
                  <div className="flex items-center gap-1.5 mt-2">
                    <AlertCircle className="h-3.5 w-3.5 text-red-500 flex-shrink-0" />
                    <p className="text-xs text-red-600">{errors.password.message}</p>
                  </div>
                )}
              </div>

              {/* Captcha Field - Only shown when backend requires it */}
              {captcha && captchaRequired && !isLocked && (
                <div className="bg-gradient-to-r from-blue-50 to-indigo-50 border-2 border-blue-200 rounded-xl p-5">
                  <label className="block text-sm font-semibold text-blue-900 mb-3 flex items-center gap-2">
                    <Shield className="h-4 w-4" />
                    Security Verification
                  </label>
                  <div className="flex items-center gap-3">
                    <div className="bg-white border-2 border-blue-300 rounded-xl px-5 py-3 text-xl font-mono font-bold text-blue-900 shadow-inner select-none">
                      {captcha.question} = ?
                    </div>
                    <input
                      {...register('captcha', { required: captchaRequired ? 'Please answer' : false })}
                      type="number"
                      className="w-24 px-4 py-3 border-2 border-gray-200 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none text-center text-xl font-mono bg-gray-50 focus:bg-white transition-all"
                      placeholder="?"
                      autoComplete="off"
                    />
                  </div>
                  {errors.captcha && (
                    <div className="flex items-center gap-1.5 mt-2">
                      <AlertCircle className="h-3.5 w-3.5 text-red-500 flex-shrink-0" />
                      <p className="text-xs text-red-600">{errors.captcha.message}</p>
                    </div>
                  )}
                  <p className="text-xs text-blue-700 mt-3 flex items-center gap-1.5">
                    <AlertTriangle className="h-3.5 w-3.5" />
                    Multiple failed attempts detected. Please solve the problem above to continue.
                  </p>
                </div>
              )}

              <button
                type="submit"
                disabled={loginMutation.isPending || isLocked}
                className={`w-full bg-gradient-to-r ${branding.login.buttonGradient} text-white py-3.5 px-4 rounded-xl font-semibold text-sm shadow-lg hover:shadow-xl focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed disabled:hover:shadow-lg transition-all transform hover:-translate-y-0.5 active:translate-y-0`}
              >
                {loginMutation.isPending ? (
                  <span className="flex items-center justify-center gap-2">
                    <svg className="animate-spin h-4 w-4" viewBox="0 0 24 24">
                      <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" fill="none" />
                      <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                    </svg>
                    Signing in...
                  </span>
                ) : isLocked ? (
                  <span className="flex items-center justify-center gap-2">
                    <Lock className="h-4 w-4" />
                    Locked ({formatTime(lockRemaining)})
                  </span>
                ) : (
                  'Sign In'
                )}
              </button>
            </form>

            {/* Captcha/Lock status indicator */}
            {captchaRequired && !isLocked && (
              <div className="mt-6 bg-blue-50 border border-blue-200 rounded-lg p-3">
                <div className="flex items-center gap-2 text-xs text-blue-700">
                  <Shield className="h-3.5 w-3.5" />
                  <span>Security verification is active for this account</span>
                </div>
              </div>
            )}
          </div>
        </div>

        {/* Footer text */}
        <p className="text-center text-xs text-gray-500 mt-6">
          {branding.login.footerText}
        </p>
        {/* Footer info */}
        <div className="flex flex-col sm:flex-row items-center justify-center gap-2 text-xs text-gray-400 mt-3">
          <span>{branding.footer.copyright.replace('{year}', String(new Date().getFullYear()))}</span>
          <span className="hidden sm:inline">|</span>
          <span>{branding.version}</span>
          {branding.footer.icpNumber && (
            <>
              <span className="hidden sm:inline">|</span>
              <a
                href={branding.footer.icpUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="hover:text-gray-600 transition-colors"
              >
                {branding.footer.icpNumber}
              </a>
            </>
          )}
        </div>
      </div>
    </div>
  );
};

export default Login;
