import { apiUrl, request, REQUEST_ID_HEADER, newRequestId } from './client';

export function listTasks(page = 1, pageSize = 15, filters = {}) {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  if (filters.organizationId) params.set('organization_id', filters.organizationId);
  if (filters.status) params.set('status', filters.status);
  if (filters.q) params.set('q', filters.q);
  return request(`/api/v1/assessment?${params.toString()}`);
}

export function getPublicStats() {
  return request('/api/v1/platform/stats');
}

export function getTask(taskId) {
  return request(`/api/v1/assessment/${encodeURIComponent(taskId)}`);
}

export function createTask(file, organizationId, taskName = '') {
  const form = new FormData();
  form.append('file', file);
  if (organizationId) form.append('organization_id', organizationId);
  if (taskName?.trim()) form.append('task_name', taskName.trim());
  return request('/api/v1/assessment', { method: 'POST', body: form });
}

export function deleteTask(taskId) {
  return request(`/api/v1/assessment/${encodeURIComponent(taskId)}`, { method: 'DELETE' });
}

export function requeueTask(taskId) {
  return request(`/api/v1/assessment/${encodeURIComponent(taskId)}/requeue`, { method: 'POST' });
}

function parseSseFrame(frame) {
  const event = { type: 'message', data: '' };
  for (const line of frame.split(/\r?\n/)) {
    if (!line || line.startsWith(':')) continue;
    const idx = line.indexOf(':');
    const field = idx === -1 ? line : line.slice(0, idx);
    const value = idx === -1 ? '' : line.slice(idx + 1).replace(/^ /, '');
    if (field === 'event') event.type = value || 'message';
    if (field === 'data') event.data += value;
  }
  return event;
}

export async function streamTaskProgress(taskId, token, handlers = {}) {
  const controller = new AbortController();
  const requestId = newRequestId();
  const response = await fetch(apiUrl(`/api/v1/assessment/${encodeURIComponent(taskId)}/progress`), {
    headers: {
      Authorization: `Bearer ${token}`,
      [REQUEST_ID_HEADER]: requestId,
    },
    signal: controller.signal,
  });

  if (!response.ok) {
    throw new Error(`进度订阅失败：HTTP ${response.status}`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  async function pump() {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const frames = buffer.split(/\n\n|\r\n\r\n/);
      buffer = frames.pop() || '';
      for (const frame of frames) {
        const event = parseSseFrame(frame);
        const payload = event.data ? JSON.parse(event.data) : {};
        if (event.type === 'progress') handlers.onProgress?.(payload);
        else if (event.type === 'complete') {
          handlers.onComplete?.(payload);
          controller.abort();
          return;
        } else if (event.type === 'error') {
          handlers.onError?.(payload);
        }
      }
    }
  }

  const done = pump().catch((err) => {
    if (err?.name !== 'AbortError') handlers.onError?.(err);
  });

  return {
    requestId: response.headers.get(REQUEST_ID_HEADER) || requestId,
    close() {
      controller.abort();
    },
    done,
  };
}
