import React, { useState, useRef, useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import { Sun, Moon, Monitor, Globe, ChevronDown } from 'lucide-react';
import { useThemeStore } from '@/store/theme';

const LANGUAGES = [
  { code: 'en', label: 'English' },
  { code: 'zh', label: '中文' },
  { code: 'ja', label: '日本語' },
];

const HeaderControls: React.FC = () => {
  const { t, i18n } = useTranslation();
  const { theme, setTheme } = useThemeStore();
  const [langOpen, setLangOpen] = useState(false);
  const langRef = useRef<HTMLDivElement>(null);

  const currentLang = LANGUAGES.find((l) => l.code === (i18n.language?.split('-')[0] || 'en')) || LANGUAGES[0];

  // Close dropdown on outside click
  useEffect(() => {
    const handleClick = (e: MouseEvent) => {
      if (langRef.current && !langRef.current.contains(e.target as Node)) {
        setLangOpen(false);
      }
    };
    if (langOpen) {
      document.addEventListener('mousedown', handleClick);
    }
    return () => document.removeEventListener('mousedown', handleClick);
  }, [langOpen]);

  const themeOptions = [
    { value: 'light' as const, icon: Sun, label: t('settings.light') },
    { value: 'dark' as const, icon: Moon, label: t('settings.dark') },
    { value: 'system' as const, icon: Monitor, label: t('settings.system') },
  ];

  return (
    <div className="flex items-center gap-2">
      {/* Theme toggle - 3 options side by side */}
      <div className="flex items-center bg-black/10 dark:bg-white/10 rounded-lg p-0.5">
        {themeOptions.map((opt) => {
          const Icon = opt.icon;
          const isActive = theme === opt.value;
          return (
            <button
              key={opt.value}
              onClick={() => setTheme(opt.value)}
              className={`flex items-center gap-1 px-2.5 py-1.5 rounded-md text-xs font-medium transition-all ${
                isActive
                  ? 'bg-white dark:bg-gray-700 text-blue-600 dark:text-blue-400 shadow-sm'
                  : 'text-gray-500 dark:text-gray-400 hover:text-gray-700 dark:hover:text-gray-200'
              }`}
              title={opt.label}
            >
              <Icon className="h-3.5 w-3.5" />
              <span className="hidden sm:inline">{opt.label}</span>
            </button>
          );
        })}
      </div>

      {/* Language dropdown */}
      <div className="relative" ref={langRef}>
        <button
          onClick={() => setLangOpen(!langOpen)}
          className="flex items-center gap-1.5 px-2.5 py-1.5 bg-black/10 dark:bg-white/10 rounded-lg text-xs font-medium text-gray-600 dark:text-gray-300 hover:text-gray-800 dark:hover:text-white transition-colors"
        >
          <Globe className="h-3.5 w-3.5" />
          <span>{currentLang.label}</span>
          <ChevronDown className={`h-3 w-3 transition-transform ${langOpen ? 'rotate-180' : ''}`} />
        </button>
        {langOpen && (
          <div className="absolute right-0 mt-1 w-32 bg-card border border-border rounded-lg shadow-lg py-1 z-50">
            {LANGUAGES.map((lang) => (
              <button
                key={lang.code}
                onClick={() => {
                  i18n.changeLanguage(lang.code);
                  setLangOpen(false);
                }}
                className={`w-full text-left px-3 py-2 text-sm transition-colors ${
                  currentLang.code === lang.code
                    ? 'text-blue-600 dark:text-blue-400 bg-blue-50 dark:bg-blue-900/20 font-medium'
                    : 'text-foreground hover:bg-muted'
                }`}
              >
                {lang.label}
              </button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
};

export default HeaderControls;
