import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/lib/api';
import { API_ENDPOINTS } from '@/lib/constants';

export interface ComplianceScope {
  id: number;
  scope_type: 'ip_cidr' | 'ip_range' | 'mac_prefix';
  scope_value: string;
  description: string | null;
  is_active: boolean;
  created_by: string;
  created_at: string;
  updated_at: string | null;
}

export interface ComplianceScopeCreate {
  scope_type: 'ip_cidr' | 'ip_range' | 'mac_prefix';
  scope_value: string;
  description?: string;
}

export interface ComplianceScopeUpdate {
  scope_type?: 'ip_cidr' | 'ip_range' | 'mac_prefix';
  scope_value?: string;
  description?: string;
  is_active?: boolean;
}

export interface ComplianceScopeListResponse {
  items: ComplianceScope[];
  total: number;
}

async function fetchScopes(is_active?: boolean): Promise<ComplianceScopeListResponse> {
  const params = is_active !== undefined ? `?is_active=${is_active}` : '';
  const response = await apiClient.get(`${API_ENDPOINTS.COMPLIANCE_SCOPE}${params}`);
  return response.data;
}

export function useComplianceScopes(is_active?: boolean) {
  return useQuery({
    queryKey: ['compliance-scopes', is_active],
    queryFn: () => fetchScopes(is_active),
  });
}

export function useCreateComplianceScope() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: ComplianceScopeCreate) =>
      apiClient.post(API_ENDPOINTS.COMPLIANCE_SCOPE, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['compliance-scopes'] });
    },
  });
}

export function useUpdateComplianceScope() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: ComplianceScopeUpdate }) =>
      apiClient.put(`${API_ENDPOINTS.COMPLIANCE_SCOPE}${id}`, data),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['compliance-scopes'] });
    },
  });
}

export function useDeleteComplianceScope() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      apiClient.delete(`${API_ENDPOINTS.COMPLIANCE_SCOPE}${id}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['compliance-scopes'] });
    },
  });
}

export function useToggleComplianceScope() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      apiClient.post(`${API_ENDPOINTS.COMPLIANCE_SCOPE}${id}/toggle`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['compliance-scopes'] });
    },
  });
}
