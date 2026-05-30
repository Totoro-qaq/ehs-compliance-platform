import { request } from './client';

const BASE = '/api/v1/standards';

export function listStandardSources({ reviewStatus = '', sourceType = '', limit = 100 } = {}) {
  const params = new URLSearchParams({ limit: String(limit) });
  if (reviewStatus) params.set('review_status', reviewStatus);
  if (sourceType) params.set('source_type', sourceType);
  return request(`${BASE}/sources?${params.toString()}`);
}

export function createStandardSource(payload) {
  return request(`${BASE}/sources`, {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function reviewStandardSource(sourceId, payload) {
  return request(`${BASE}/sources/${encodeURIComponent(sourceId)}/review`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}
