import { request } from './client';

export function chatWithAgent({ content, sessionId }) {
  return request('/api/v1/agent/chat', {
    method: 'POST',
    body: JSON.stringify({
      content,
      session_id: sessionId || null,
    }),
    timeoutMs: 180000,
  });
}

export function listAgentSessions(page = 1, pageSize = 20) {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  return request(`/api/v1/agent/sessions?${params.toString()}`);
}

export function listAgentMessages(sessionId) {
  return request(`/api/v1/agent/sessions/${encodeURIComponent(sessionId)}/messages`);
}

export function deleteAgentSession(sessionId) {
  return request(`/api/v1/agent/sessions/${encodeURIComponent(sessionId)}`, {
    method: 'DELETE',
  });
}

export function clearAgentSessions() {
  return request('/api/v1/agent/sessions', {
    method: 'DELETE',
  });
}
