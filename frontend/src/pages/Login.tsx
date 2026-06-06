import React, { useState, useEffect, useRef } from 'react';
import { useForm } from 'react-hook-form';
import { useNavigate, useLocation } from 'react-router-dom';
import { useMutation } from '@tanstack/react-query';
import { apiClient } from '@/lib/api';
import { useAuthStore } from '@/store/auth';
import { Shield, Lock, User, AlertCircle, AlertTriangle, X } from 'lucide-react';
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

const LOCK_DURATION = 15 * 60 * 1000; // 15 minutes
const CAPTCHA_THRESHOLD = 3;
const LOCK_THRESHOLD = 5;

const getFailCount = (): number => {
  return parseInt(sessionStorage.getItem('login_fail_count') || '0', 10);
};

const setFailCount = (count: number) => {
  sessionStorage.setItem('login_fail_count', String(count));
};

const getLockUntil = (): number => {
  return parseInt(sessionStorage.getItem('login_lock_until') || '0', 10);
};

const setLockUntil = (timestamp: number) => {
  sessionStorage.setItem('login_lock_until', String(timestamp));
};

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
  const [isLocked, setIsLocked] = useState(false);
  const [lockRemaining, setLockRemaining] = useState(0);
  const [showError, setShowError] = useState(false);
  const errorTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const { register, handleSubmit, formState: { errors } } = useForm<LoginFormData>();

  // Check lock status on mount and periodically
  useEffect(() => {
    const checkLock = () => {
      const lockUntil = getLockUntil();
      const now = Date.now();
      if (lockUntil > now) {
        setIsLocked(true);
        setLockRemaining(Math.ceil((lockUntil - now) / 1000));
      } else {
        setIsLocked(false);
        const failCount = getFailCount();
        if (failCount >= CAPTCHA_THRESHOLD && !captcha) {
          setCaptcha(generateCaptcha());
        }
      }
    };

    checkLock();
    const interval = setInterval(checkLock, 1000);
    return () => clearInterval(interval);
  }, []);

  // Countdown timer
  useEffect(() => {
    if (!isLocked) return;
    const timer = setInterval(() => {
      const lockUntil = getLockUntil();
      const remaining = Math.ceil((lockUntil - Date.now()) / 1000);
      if (remaining <= 0) {
        setIsLocked(false);
        setFailCount(0);
        setCaptcha(null);
        setLockRemaining(0);
        clearInterval(timer);
      } else {
        setLockRemaining(remaining);
      }
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

      const response = await apiClient.post('/auth/login', formData.toString(), {
        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
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
      // Reset fail count on success
      setFailCount(0);
      sessionStorage.removeItem('login_lock_until');
      login(data.user, data.access_token, data.refresh_token);

      const from = (location.state as any)?.from?.pathname || '/dashboard';
      navigate(from, { replace: true });
    },
    onError: (error: any) => {
      const newFailCount = getFailCount() + 1;
      setFailCount(newFailCount);

      const message = error.response?.data?.detail || 'Login failed. Please check your credentials.';
      setBackendError(message);
      setShowError(true);

      // Show captcha after 3 failures
      if (newFailCount >= CAPTCHA_THRESHOLD && !captcha) {
        setCaptcha(generateCaptcha());
      }

      // Lock after 5 failures
      if (newFailCount >= LOCK_THRESHOLD) {
        const lockUntil = Date.now() + LOCK_DURATION;
        setLockUntil(lockUntil);
        setIsLocked(true);
        setLockRemaining(Math.ceil(LOCK_DURATION / 1000));
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
    setBackendError('');
    setShowError(false);

    if (isLocked) return;

    // Validate captcha if required
    if (captcha) {
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

  const failCount = getFailCount();

  return (
    <div className={`min-h-screen flex items-center justify-center p-4 ${
      branding.login.background.type === 'image'
        ? 'bg-cover bg-center bg-no-repeat'
        : branding.login.background.gradientClass
    }`}
    style={branding.login.background.type === 'image' ? {
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
                          style={{ width: `${Math.max(0, (lockRemaining / (LOCK_DURATION / 1000)) * 100)}%` }}
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
                      minLength: { value: 6, message: 'Password must be at least 6 characters' },
                      maxLength: { value: 128, message: 'Password must be at most 128 characters' },
                    })}
                    type="password"
                    disabled={isLocked}
                    className={`w-full pl-10 pr-4 py-3 border-2 rounded-xl focus:ring-2 focus:ring-blue-500 focus:border-blue-500 outline-none transition-all text-gray-900 placeholder-gray-400 ${
                      errors.password ? 'border-red-400 bg-red-50' : 'border-gray-200 bg-gray-50 focus:bg-white'
                    } ${isLocked ? 'bg-gray-100 cursor-not-allowed opacity-60' : ''}`}
                    placeholder="Enter your password"
                  />
                </div>
                {errors.password && (
                  <div className="flex items-center gap-1.5 mt-2">
                    <AlertCircle className="h-3.5 w-3.5 text-red-500 flex-shrink-0" />
                    <p className="text-xs text-red-600">{errors.password.message}</p>
                  </div>
                )}
              </div>

              {/* Captcha Field - Only shown after multiple failed attempts */}
              {captcha && !isLocked && (
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
                      {...register('captcha', { required: captcha ? 'Please answer' : false })}
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

            {/* Failed attempts indicator - Shows current attempt count */}
            {failCount > 0 && !isLocked && (
              <div className="mt-6 bg-gray-50 border border-gray-200 rounded-lg p-3">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-gray-600">
                    Failed attempts
                  </span>
                  <div className="flex items-center gap-3">
                    <div className="flex gap-1">
                      {Array.from({ length: LOCK_THRESHOLD }).map((_, i) => (
                        <div
                          key={i}
                          className={`w-2 h-2 rounded-full transition-colors ${
                            i < failCount ? 'bg-red-400' : 'bg-gray-200'
                          }`}
                        />
                      ))}
                    </div>
                    <span className="font-mono text-gray-700 font-semibold">
                      {failCount}/{LOCK_THRESHOLD}
                    </span>
                  </div>
                </div>
                {failCount >= LOCK_THRESHOLD - 1 && (
                  <p className="text-xs text-orange-600 mt-2 text-center">
                    {LOCK_THRESHOLD - failCount} more failed attempt{LOCK_THRESHOLD - failCount > 1 ? 's' : ''} will lock your account.
                  </p>
                )}
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
