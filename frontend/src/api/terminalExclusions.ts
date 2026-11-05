import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { apiClient } from '@/lib/api';
import { API_ENDPOINTS } from '@/lib/constants';

export type IpPatternType = 'single_ip' | 'cidr' | 'ip_range';
export type MacPatternType = 'mac' | 'mac_prefix';

export interface TerminalExclusion {
  id: number;
  ip_type: IpPatternType | null;
  ip_value: string | null;
  mac_type: MacPatternType | null;
  mac_value: string | null;
  comments: string | null;
  is_active: boolean;
  created_by: string;
  created_at: string;
  updated_at: string | null;
}

export interface TerminalExclusionCondition {
  ip_type?: IpPatternType | null;
  ip_value?: string | null;
  mac_type?: MacPatternType | null;
  mac_value?: string | null;
}

export interface TerminalExclusionCreate extends TerminalExclusionCondition {
  comments: string;
}

export interface TerminalExclusionUpdate extends TerminalExclusionCondition {
  comments?: string;
  is_active?: boolean;
}

export interface ExclusionSample {
  ip_address: string;
  mac_address: string;
  status: string;
  reason: string;
}

export interface ExclusionImpact {
  matched: number;
  purgeable: number;
  retained: number;
  samples: ExclusionSample[];
}

export interface TerminalExclusionWithImpact {
  rule: TerminalExclusion;
  impact: ExclusionImpact;
}

export interface TerminalExclusionListResponse {
  items: TerminalExclusion[];
  total: number;
}

const invalidateRelated = (queryClient: ReturnType<typeof useQueryClient>) => {
  queryClient.invalidateQueries({ queryKey: ['terminal-exclusions'] });
  queryClient.invalidateQueries({ queryKey: ['terminals'] });
  queryClient.invalidateQueries({ queryKey: ['stats'] });
};

async function fetchExclusions(is_active?: boolean): Promise<TerminalExclusionListResponse> {
  const params = is_active !== undefined ? `?is_active=${is_active}` : '';
  const response = await apiClient.get(`${API_ENDPOINTS.TERMINAL_EXCLUSIONS}${params}`);
  return response.data;
}

export function useTerminalExclusions(is_active?: boolean) {
  return useQuery({
    queryKey: ['terminal-exclusions', is_active],
    queryFn: () => fetchExclusions(is_active),
  });
}

export function usePreviewTerminalExclusion() {
  return useMutation({
    mutationFn: (data: TerminalExclusionCondition): Promise<ExclusionImpact> =>
      apiClient
        .post(API_ENDPOINTS.TERMINAL_EXCLUSIONS_PREVIEW, data)
        .then((response) => response.data),
  });
}

export function useCreateTerminalExclusion() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (data: TerminalExclusionCreate): Promise<TerminalExclusionWithImpact> =>
      apiClient
        .post(API_ENDPOINTS.TERMINAL_EXCLUSIONS, data)
        .then((response) => response.data),
    onSuccess: () => invalidateRelated(queryClient),
  });
}

export function useUpdateTerminalExclusion() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, data }: { id: number; data: TerminalExclusionUpdate }) =>
      apiClient
        .put(`${API_ENDPOINTS.TERMINAL_EXCLUSIONS}${id}`, data)
        .then((response) => response.data as TerminalExclusionWithImpact),
    onSuccess: () => invalidateRelated(queryClient),
  });
}

export function useDeleteTerminalExclusion() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      apiClient.delete(`${API_ENDPOINTS.TERMINAL_EXCLUSIONS}${id}`),
    onSuccess: () => invalidateRelated(queryClient),
  });
}

export function useToggleTerminalExclusion() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: number) =>
      apiClient
        .post(`${API_ENDPOINTS.TERMINAL_EXCLUSIONS}${id}/toggle`)
        .then((response) => response.data as TerminalExclusionWithImpact),
    onSuccess: () => invalidateRelated(queryClient),
  });
}
