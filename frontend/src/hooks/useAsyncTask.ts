import { useEffect, useRef, useState } from 'react';

export type AsyncTaskStatus = 'idle' | 'pending' | 'running' | 'success' | 'failed';

export interface AsyncTaskState {
  status: AsyncTaskStatus;
  error: string | null;
  data: { status?: string; error?: string | null; message?: string | null; [key: string]: unknown } | null;
}

/**
 * Poll a background task by id until it reaches a terminal state.
 *
 * - taskId null → idle (no polling)
 * - server status 'pending'/'running' → keep polling
 * - server status 'success'/'failed' → stop and surface the result
 * - transient network errors are ignored (keep polling) so the task is not
 *   misreported as failed during a temporary hiccup
 */
export function useAsyncTask(
  taskId: string | null,
  poll: (id: string) => Promise<{ status?: string; error?: string | null; message?: string | null; [key: string]: unknown }>,
  intervalMs = 1000,
): AsyncTaskState {
  const [state, setState] = useState<AsyncTaskState>({ status: 'idle', error: null, data: null });
  const pollRef = useRef(poll);
  pollRef.current = poll;

  useEffect(() => {
    if (!taskId) {
      setState({ status: 'idle', error: null, data: null });
      return;
    }

    let cancelled = false;
    const timer = setInterval(async () => {
      let result: { status?: string; error?: string | null; message?: string | null };
      try {
        result = await pollRef.current(taskId);
      } catch {
        // Transient poll error — keep polling, do not fail the task.
        return;
      }
      if (cancelled) return;

      if (result.status === 'success') {
        setState({ status: 'success', error: null, data: result });
        clearInterval(timer);
      } else if (result.status === 'failed') {
        setState({ status: 'failed', error: result.error ?? null, data: result });
        clearInterval(timer);
      } else {
        const next = result.status === 'running' ? 'running' : 'pending';
        setState({ status: next, error: null, data: result });
      }
    }, intervalMs);

    return () => {
      cancelled = true;
      clearInterval(timer);
    };
  }, [taskId, intervalMs]);

  return state;
}