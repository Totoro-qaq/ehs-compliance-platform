export function escapeHtml(value) {
  return String(value ?? '')
    .replaceAll('&', '&amp;')
    .replaceAll('<', '&lt;')
    .replaceAll('>', '&gt;')
    .replaceAll('"', '&quot;');
}

export function formatTime(value) {
  if (!value) return '-';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString('zh-CN', {
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
  });
}

const STATUS_MAP = {
  PENDING: '等待中',
  PARSING: '解析中',
  AI_ANALYZING: 'AI 分析',
  VALIDATING: '校验中',
  PERSISTING: '保存中',
  SUCCESS: '已完成',
  NEEDS_REVIEW: '需复核',
  FAILED: '失败',
};

export function statusText(status) {
  return STATUS_MAP[status] || status || '-';
}
