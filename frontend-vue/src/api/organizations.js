import { request } from './client';

export function listOrganizations(page = 1, pageSize = 15) {
  return request(`/api/v1/organizations?page=${page}&page_size=${pageSize}`);
}

export function getOrganization(id) {
  return request(`/api/v1/organizations/${encodeURIComponent(id)}`);
}

export function createOrganization(payload) {
  return request('/api/v1/organizations', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateOrganization(id, payload) {
  return request(`/api/v1/organizations/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function deleteOrganization(id) {
  return request(`/api/v1/organizations/${id}`, { method: 'DELETE' });
}
