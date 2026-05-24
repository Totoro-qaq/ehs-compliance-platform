import { request } from './client';

export function listDetectionReports(page = 1, pageSize = 15, filters = {}) {
  const params = new URLSearchParams({
    page: String(page),
    page_size: String(pageSize),
  });
  if (filters.organizationId) params.set('organization_id', filters.organizationId);
  if (filters.reportType) params.set('report_type', filters.reportType);
  if (filters.status) params.set('status', filters.status);
  if (filters.clientName) params.set('client_name', filters.clientName);
  if (filters.projectName) params.set('project_name', filters.projectName);
  if (filters.projectCode) params.set('project_code', filters.projectCode);
  if (filters.serviceType) params.set('service_type', filters.serviceType);
  return request(`/api/v1/detection/reports?${params.toString()}`);
}

export function createDetectionReport(file, {
  organizationId,
  reportType,
  reportName,
  clientName,
  projectName,
  projectCode,
  serviceType,
}) {
  const form = new FormData();
  form.append('file', file);
  if (organizationId) form.append('organization_id', organizationId);
  if (reportType) form.append('report_type', reportType);
  if (reportName?.trim()) form.append('report_name', reportName.trim());
  if (clientName?.trim()) form.append('client_name', clientName.trim());
  if (projectName?.trim()) form.append('project_name', projectName.trim());
  if (projectCode?.trim()) form.append('project_code', projectCode.trim());
  if (serviceType?.trim()) form.append('service_type', serviceType.trim());
  return request('/api/v1/detection/reports', { method: 'POST', body: form, timeoutMs: 60000 });
}

export function previewDetectionDocument(file, { reportType }) {
  const form = new FormData();
  form.append('file', file);
  if (reportType) form.append('report_type', reportType);
  return request('/api/v1/detection/documents/preview', {
    method: 'POST',
    body: form,
    timeoutMs: 90000,
  });
}

export function importDetectionDocumentPreview(payload) {
  return request('/api/v1/detection/documents/import', {
    method: 'POST',
    body: JSON.stringify(payload),
    timeoutMs: 60000,
  });
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
