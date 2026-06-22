import { useState, useEffect } from 'react';

export const formatDate = (dateString: string | null | undefined): string => {
  if (!dateString) return '-';
  try {
    const date = new Date(dateString);
    if (isNaN(date.getTime())) {
      return dateString;
    }
    return date.toLocaleString('en-US', {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    });
  } catch {
    return dateString;
  }
};

export const formatDateTime = (dateString: string | null | undefined): string => {
  if (!dateString) return '-';
  try {
    const date = new Date(dateString);
    if (isNaN(date.getTime())) {
      return dateString;
    }
    return date.toISOString().replace('T', ' ').slice(0, 19);
  } catch {
    return dateString;
  }
};

export const downloadCSV = (headers: string[], rows: (string | number | boolean | null | undefined)[][], filename: string): void => {
  const escapedRows = rows.map((row) =>
    row.map((cell) => {
      if (typeof cell === 'string') {
        return `"${cell.replace(/"/g, '""')}"`;
      }
      return String(cell);
    })
  );

  const csvContent = [headers.join(','), ...escapedRows.map((row) => row.join(','))].join('\n');

  const blob = new Blob([`\uFEFF${csvContent}`], { type: 'text/csv;charset=utf-8;' });
  const url = window.URL.createObjectURL(blob);
  const link = document.createElement('a');

  link.href = url;
  link.download = `${filename}-${new Date().toISOString().split('T')[0]}.csv`;
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  window.URL.revokeObjectURL(url);
};

export const validateMACAddress = (mac: string): boolean => {
  const macRegex = /^([0-9A-Fa-f]{2}[:-]){5}([0-9A-Fa-f]{2})$/;
  return macRegex.test(mac);
};

export const validateIPAddress = (ip: string): boolean => {
  const ipRegex = /^((25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)$/;
  return ipRegex.test(ip);
};

export const generateId = (): string => {
  return Math.random().toString(36).substring(2) + Date.now().toString(36);
};

export const truncateText = (text: string, maxLength: number): string => {
  if (!text) return '';
  if (text.length <= maxLength) return text;
  return text.substring(0, maxLength) + '...';
};

export const capitalize = (str: string): string => {
  if (!str) return str;
  return str.charAt(0).toUpperCase() + str.slice(1);
};

export const debounce = <T extends (...args: Parameters<T>) => void>(
  func: T,
  wait: number
): ((...args: Parameters<T>) => void) => {
  let timeout: ReturnType<typeof setTimeout> | null = null;
  return (...args: Parameters<T>) => {
    if (timeout) clearTimeout(timeout);
    timeout = setTimeout(() => func(...args), wait);
  };
};

export const throttle = <T extends (...args: Parameters<T>) => void>(
  func: T,
  limit: number
): ((...args: Parameters<T>) => void) => {
  let inThrottle = false;
  return (...args: Parameters<T>) => {
    if (!inThrottle) {
      func(...args);
      inThrottle = true;
      setTimeout(() => (inThrottle = false), limit);
    }
  };
};

export const normalizeMacAddress = (mac: string): string => {
  const cleaned = mac.replace(/[-:.]/g, '').toUpperCase();
  if (cleaned.length !== 12) {
    throw new Error('Invalid MAC address format');
  }
  return cleaned.match(/.{1,2}/g)?.join('-') || mac;
};

export const isValidMacAddress = (mac: string): boolean => {
  const cleaned = mac.replace(/[-:.]/g, '').toUpperCase();
  return cleaned.length === 12 && /^[0-9A-F]+$/.test(cleaned);
};

export const isValidIpAddress = (ip: string): boolean => {
  const parts = ip.split('.');
  if (parts.length !== 4) return false;
  return parts.every(
    (part) =>
      !isNaN(parseInt(part, 10)) &&
      parseInt(part, 10) >= 0 &&
      parseInt(part, 10) <= 255
  );
};

export const isValidCidrOrRange = (input: string): boolean => {
  if (!input) return false;

  const cidrPattern = /^\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\/\d{1,2}$/;
  const rangePattern = /^(\d{1,3}\.\d{1,3}\.\d{1,3})\.(\d+)-(\d+)(\/\d{1,2})?$/;

  if (cidrPattern.test(input)) {
    const [ipPart, subnet] = input.split('/');
    if (!isValidIpAddress(ipPart)) return false;
    const subnetNum = parseInt(subnet, 10);
    return subnetNum >= 0 && subnetNum <= 32;
  }

  const rangeMatch = input.match(rangePattern);
  if (rangeMatch) {
    const startNum = parseInt(rangeMatch[2], 10);
    const endNum = parseInt(rangeMatch[3], 10);

    if (isNaN(startNum) || isNaN(endNum)) return false;
    if (startNum > endNum) return false;
    if (endNum > 255) return false;

    return true;
  }

  return isValidIpAddress(input);
};

export function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState(value);
  useEffect(() => {
    const timer = setTimeout(() => setDebouncedValue(value), delay);
    return () => clearTimeout(timer);
  }, [value, delay]);
  return debouncedValue;
}

/**
 * Extract a user-friendly error message from an unknown error.
 * Handles Axios-style errors with response.data.detail, standard Error instances,
 * and falls back to a provided default message.
 */
export function getErrorMessage(error: unknown, fallback = 'An error occurred'): string {
  if (error && typeof error === 'object') {
    const axiosError = error as { response?: { data?: { detail?: unknown; message?: string } } };
    const detail = axiosError.response?.data?.detail;
    if (detail) {
      // detail may be a string or an object like {message, error_id}
      if (typeof detail === 'string') return detail;
      if (typeof detail === 'object' && detail !== null) {
        const obj = detail as Record<string, unknown>;
        if (typeof obj.message === 'string') return obj.message;
        try { return JSON.stringify(detail); } catch { /* fall through */ }
      }
    }
    if (axiosError.response?.data?.message) {
      return axiosError.response.data.message;
    }
  }
  if (error instanceof Error) {
    return error.message;
  }
  return fallback;
}
