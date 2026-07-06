/**
 * Branding Configuration
 *
 * This is the single source of truth for all customizable branding elements.
 * Modify this file to adapt the application for different companies/deployments.
 *
 * For asset files (logo, favicon, background), place them in the `public/` directory
 * and reference them with absolute paths (e.g., "/logo.svg").
 */

interface BrandingConfig {
  appName: string;
  appShortName: string;
  appSubtitle: string;
  version: string;
  title: string;
  favicon: string;
  logo: {
    type: 'icon' | 'image';
    name: string;
    path: string;
    className: string;
  };
  login: {
    heading: string;
    subheading: string;
    footerText: string;
    background: {
      type: 'gradient' | 'image';
      gradientClass: string;
      imagePath: string;
    };
    buttonGradient: string;
    headerGradient: string;
  };
  footer: {
    copyright: string;
    icpNumber: string;
    icpUrl: string;
    links: { label: string; url: string }[];
  };
}

const branding: BrandingConfig = {
  /** Application name displayed in sidebar, login page, and browser title */
  appName: 'Terminal Access Manager',

  /** Short name used in sidebar when expanded */
  appShortName: 'Terminal Access',

  /** Subtitle shown below the app name in sidebar */
  appSubtitle: 'Manager',

  /** Version number displayed in footer */
  /** Note: Actual version is dynamically fetched from backend /health API at runtime */
  /** Build-time version is read from VERSION file via VITE_APP_VERSION */
  version: `v${import.meta.env.VITE_APP_VERSION || '3.6.3'}`,

  /** Browser tab title (used in index.html and dynamic title updates) */
  title: 'Terminal Access Manager',

  /** Favicon path - place your favicon file in the `public/` directory */
  favicon: '/favicon.svg',

  /**
   * Logo configuration for sidebar and login page.
   * - type: "icon" uses a Lucide icon component name
   * - type: "image" uses an image file from the `public/` directory
   */
  logo: {
    type: 'icon',
    name: 'Shield', // Lucide icon name (used when type is "icon")
    path: '/logo.svg', // Image path (used when type is "image")
    className: 'text-blue-500', // Tailwind classes for icon color
  },

  /** Login page configuration */
  login: {
    /** Heading text on the login page */
    heading: 'Terminal Access Manager',
    /** Subheading text below the heading */
    subheading: 'Sign in to your account',
    /** Footer text at the bottom of the login card */
    footerText: 'Secure authentication · Session-based access control',
    /**
     * Background style for the login page.
     * - type: "gradient" uses Tailwind gradient classes
     * - type: "image" uses a background image from the `public/` directory
     */
    background: {
      type: 'gradient',
      gradientClass: 'bg-gradient-to-br from-gray-50 via-blue-50 to-indigo-100',
      imagePath: '/login-bg.jpg', // Used when type is "image"
    },
    /** Primary button gradient classes */
    buttonGradient: 'from-blue-600 to-indigo-600',
    /** Header band gradient classes */
    headerGradient: 'from-blue-600 to-indigo-600',
  },

  /** Footer configuration */
  footer: {
    /** Copyright text. {year} will be replaced with current year */
    copyright: '© {year} TerminalAccessManager (TAM)',
    /** ICP filing number (leave empty string to hide) */
    icpNumber: '京ICP备XXXXXXXX号',
    /** ICP filing URL */
    icpUrl: 'https://beian.miit.gov.cn/',
    /** Additional footer links */
    links: [] as { label: string; url: string }[],
  },
};

export default branding;

/**
 * HELPER: To use a custom logo image instead of the default icon:
 *
 * 1. Place your logo file (e.g., "company-logo.svg") in the `public/` directory
 * 2. Update the logo config:
 *    logo: {
 *      type: 'image',
 *      name: 'Shield',
 *      path: '/company-logo.svg',
 *      className: 'text-blue-500',
 *    }
 *
 * HELPER: To use a custom login background image:
 *
 * 1. Place your background image (e.g., "login-bg.jpg") in the `public/` directory
 * 2. Update the login.background config:
 *    background: {
 *      type: 'image',
 *      gradientClass: 'bg-gradient-to-br from-gray-50 via-blue-50 to-indigo-100',
 *      imagePath: '/login-bg.jpg',
 *    }
 *
 * HELPER: To update favicon:
 *
 * 1. Place your favicon file (e.g., "favicon.ico") in the `public/` directory
 * 2. Update the favicon config:
 *    favicon: '/favicon.ico'
 * 3. Also update the <link> tag in index.html to match
 */
