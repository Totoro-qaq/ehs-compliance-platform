import { request } from './client';

export function login(payload) {
  return request('/api/v1/auth/login', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function register(payload) {
  return request('/api/v1/auth/register', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function changePassword(oldPassword, newPassword) {
  return request('/api/v1/auth/change-password', {
    method: 'POST',
    body: JSON.stringify({ old_password: oldPassword, new_password: newPassword }),
  });
}

export function healthCheck() {
  return request('/healthz');
}
