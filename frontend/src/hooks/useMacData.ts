import { useQuery } from '@tanstack/react-query';
import { apiClient } from '@/lib/api';

export interface MacAddress {
  id: number;
  ip_address: string;
  mac_address: string;
  status: string;
  comments: string;
  timestamp: string;
  source: string;
}

export interface WhitelistEntry {
  id: number;
  mac_address: string;
  ip_address: string;
  comments: string;
  added_by: string;
  created_at: string;
}

export interface BlacklistEntry {
  id: number;
  ip_address: string;
  mac_address: string;
  reason: string;
  blocked_at: string;
  expires_at: string;
  blocked_by: string;
}

export const useMacAddresses = () => {
  return useQuery({
    queryKey: ['macAddresses'],
    queryFn: async () => {
      const response = await apiClient.get('/mac/search');
      return response.data as MacAddress[];
    },
  });
};

export const useInvalidMacAddresses = () => {
  return useQuery({
    queryKey: ['invalidMacAddresses'],
    queryFn: async () => {
      const response = await apiClient.get('/mac/');
      return response.data as MacAddress[];
    },
  });
};

export const useWhitelist = () => {
  return useQuery({
    queryKey: ['whitelist'],
    queryFn: async () => {
      const response = await apiClient.get('/whitelist/');
      return response.data as WhitelistEntry[];
    },
  });
};

export const useStats = () => {
  return useQuery({
    queryKey: ['stats'],
    queryFn: async () => {
      const [macs, whitelist] = await Promise.all([
        apiClient.get('/mac/search'),
        apiClient.get('/whitelist/'),
      ]);
      
      const macList = macs.data as MacAddress[];
      const whitelistList = whitelist.data as WhitelistEntry[];
      
      const blockedCount = macList.filter(m => m.status === 'frozen').length;
      const activeCount = macList.filter(m => m.status === 'unfrozen').length;
      
      return {
        total: macList.length,
        whitelisted: whitelistList.length,
        blocked: blockedCount,
        active: activeCount,
      };
    },
  });
};