import { request } from './client';

export function listOrganizations(page = 1, pageSize = 15) {
  return request(`/api/v1/organizations?page=${page}&page_size=${pageSize}`);
}

export function createOrganization(name) {
  return request('/api/v1/organizations', {
    method: 'POST',
    body: JSON.stringify({ name }),
  });
}

export function updateOrganization(id, name) {
  return request(`/api/v1/organizations/${id}`, {
    method: 'PATCH',
    body: JSON.stringify({ name }),
  });
}

export function deleteOrganization(id) {
  return request(`/api/v1/organizations/${id}`, { method: 'DELETE' });
}
