import { useState, useEffect } from 'react';

interface NetworkStatus {
  isOnline: boolean;
  isSlowConnection: boolean;
}

export function useNetworkStatus(): NetworkStatus {
  const [isOnline, setIsOnline] = useState(navigator.onLine);
  const [isSlowConnection, setIsSlowConnection] = useState(false);

  useEffect(() => {
    const handleOnline = () => setIsOnline(true);
    const handleOffline = () => setIsOnline(false);

    window.addEventListener('online', handleOnline);
    window.addEventListener('offline', handleOffline);

    // Check effective connection type if available
    // eslint-disable-next-line @typescript-eslint/no-explicit-any -- Navigator connection API has no standard type
    const connection = (navigator as any).connection;
    if (connection) {
      const updateConnection = () => {
        const type = connection.effectiveType;
        setIsSlowConnection(type === '2g' || type === 'slow-2g');
      };
      updateConnection();
      connection.addEventListener('change', updateConnection);
      return () => {
        window.removeEventListener('online', handleOnline);
        window.removeEventListener('offline', handleOffline);
        connection.removeEventListener('change', updateConnection);
      };
    }

    return () => {
      window.removeEventListener('online', handleOnline);
      window.removeEventListener('offline', handleOffline);
    };
  }, []);

  return { isOnline, isSlowConnection };
}
