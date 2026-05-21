import { request } from './client';

export function listDetectionReports(page = 1, pageSize = 15, filters = {}) {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  if (filters.organizationId) params.set('organization_id', filters.organizationId);
  if (filters.reportType) params.set('report_type', filters.reportType);
  if (filters.status) params.set('status', filters.status);
  return request(`/api/v1/detection/reports?${params.toString()}`);
}

export function createDetectionReport(file, { organizationId, reportType }) {
  const form = new FormData();
  form.append('file', file);
  if (organizationId) form.append('organization_id', organizationId);
  if (reportType) form.append('report_type', reportType);
  return request('/api/v1/detection/reports', { method: 'POST', body: form, timeoutMs: 60000 });
}

export function getDetectionReport(reportId) {
  return request(`/api/v1/detection/reports/${encodeURIComponent(reportId)}`);
}

export function calculateDetectionReport(reportId) {
  return request(`/api/v1/detection/reports/${encodeURIComponent(reportId)}/calculate`, {
    method: 'POST',
    timeoutMs: 60000,
  });
}

export function listDetectionResults(reportId) {
  return request(`/api/v1/detection/reports/${encodeURIComponent(reportId)}/results`);
}

export function listRegulatoryLimits(page = 1, pageSize = 15, filters = {}) {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  if (filters.indicatorName) params.set('indicator_name', filters.indicatorName);
  if (filters.medium) params.set('medium', filters.medium);
  if (filters.standardCode) params.set('standard_code', filters.standardCode);
  return request(`/api/v1/detection/limits?${params.toString()}`);
}

export function createRegulatoryLimit(payload) {
  return request('/api/v1/detection/limits', {
    method: 'POST',
    body: JSON.stringify(payload),
  });
}

export function updateRegulatoryLimit(limitId, payload) {
  return request(`/api/v1/detection/limits/${encodeURIComponent(limitId)}`, {
    method: 'PUT',
    body: JSON.stringify(payload),
  });
}

export function deleteRegulatoryLimit(limitId) {
  return request(`/api/v1/detection/limits/${encodeURIComponent(limitId)}`, { method: 'DELETE' });
}
