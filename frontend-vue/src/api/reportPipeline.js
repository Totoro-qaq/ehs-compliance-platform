import { request, requestFile } from './client';

const BASE = '/api/v1/report-pipeline';

export function listReportSectionTemplates() {
  return request(`${BASE}/templates`);
}

export function bootstrapReportSections(reportId) {
  return request(`${BASE}/reports/${encodeURIComponent(reportId)}/bootstrap-sections`, {
    method: 'POST',
  });
}

export function listReportSections(reportId) {
  return request(`${BASE}/reports/${encodeURIComponent(reportId)}/sections`);
}

export function getReportReadiness(reportId) {
  return request(`${BASE}/reports/${encodeURIComponent(reportId)}/readiness`);
}

export function reviewReportSection(sectionId, payload) {
  return request(`${BASE}/sections/${encodeURIComponent(sectionId)}/review`, {
    method: 'PATCH',
    body: JSON.stringify(payload),
  });
}

export function exportReport(reportId, format = 'markdown') {
  const params = new URLSearchParams({ format });
  return requestFile(`${BASE}/reports/${encodeURIComponent(reportId)}/export?${params.toString()}`, {
    timeoutMs: 60000,
  });
}
