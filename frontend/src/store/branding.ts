import { create } from 'zustand';
import { apiClient } from '@/lib/api';
import branding from '@/config/branding';

interface BrandingState {
  appName: string;
  appShortName: string;
  appSubtitle: string;
  loginHeading: string;
  loginSubheading: string;
  loginFooterText: string;
  loginBgUrl: string;
  faviconUrl: string;
  footerCopyright: string;
  footerIcpNumber: string;
  footerIcpUrl: string;
  isLoaded: boolean;
  loadFromBackend: () => Promise<void>;
}

export const useBrandingStore = create<BrandingState>((set) => ({
  appName: branding.appName,
  appShortName: branding.appShortName,
  appSubtitle: branding.appSubtitle,
  loginHeading: branding.login.heading,
  loginSubheading: branding.login.subheading,
  loginFooterText: branding.login.footerText,
  loginBgUrl: '',
  faviconUrl: '',
  footerCopyright: branding.footer.copyright,
  footerIcpNumber: branding.footer.icpNumber,
  footerIcpUrl: branding.footer.icpUrl,
  isLoaded: false,

  loadFromBackend: async () => {
    try {
      const token = sessionStorage.getItem('access_token');
      if (!token) return;

      const response = await apiClient.get('/settings/');
      const { branding: cfg } = response.data;

      if (cfg) {
        const updates: Partial<BrandingState> = {
          appName: cfg.app_name || branding.appName,
          appShortName: cfg.app_short_name || branding.appShortName,
          appSubtitle: cfg.app_subtitle || branding.appSubtitle,
          loginHeading: cfg.login_heading || branding.login.heading,
          loginSubheading: cfg.login_subheading || branding.login.subheading,
          loginFooterText: cfg.login_footer_text || branding.login.footerText,
          loginBgUrl: cfg.login_bg_url || '',
          faviconUrl: cfg.favicon_url || '',
          footerCopyright: cfg.footer_copyright || branding.footer.copyright,
          footerIcpNumber: cfg.footer_icp_number ?? branding.footer.icpNumber,
          footerIcpUrl: cfg.footer_icp_url || branding.footer.icpUrl,
          isLoaded: true,
        };
        set(updates);

        // Update document title dynamically
        document.title = cfg.app_name || branding.title;

        // Update favicon dynamically
        if (cfg.favicon_url) {
          let link = document.querySelector("link[rel~='icon']") as HTMLLinkElement;
          if (!link) {
            link = document.createElement('link');
            link.rel = 'icon';
            document.head.appendChild(link);
          }
          link.href = cfg.favicon_url;
        }
      }
    } catch {
      set({ isLoaded: true });
    }
  },
}));
