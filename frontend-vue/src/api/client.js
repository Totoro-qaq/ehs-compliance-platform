import { useSessionStore } from '../stores/session';
import { useToastStore } from '../stores/toast';

export const REQUEST_ID_HEADER = 'X-Request-Id';
const DEFAULT_TIMEOUT_MS = 30000;

export function normalizeBase(value) {
  const base = (value || '').trim().replace(/\/+$/, '');
  if (!base) return '';
  if (!/^https?:\/\//i.test(base)) return `http://${base}`;
  return base;
}

export function newRequestId() {
  if (globalThis.crypto?.randomUUID) return globalThis.crypto.randomUUID();
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 10)}`;
}

export function apiUrl(path) {
  const session = useSessionStore();
  const base = normalizeBase(session.apiBase);
  return `${base}${path}`;
}

async function fetchWithTimeout(url, options, timeoutMs) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...options, signal: controller.signal });
  } finally {
    clearTimeout(timer);
  }
}

function connectionError(err, url, requestId, timeoutMs) {
  if (err?.name === 'AbortError') {
    return makeApiError(`请求超时：${timeoutMs / 1000}s`, { requestId });
  }
  return makeApiError(`无法连接后端：${url}`, { requestId });
}

function unwrapEnvelope(body) {
  if (body && typeof body === 'object' && Object.prototype.hasOwnProperty.call(body, 'success')) {
    if (!body.success) {
      const err = makeApiError(body.message || body.code || '请求失败', {
        code: body.code,
        details: body.details,
      });
      throw err;
    }
    return body.data;
  }
  return body;
}

function makeApiError(message, extra = {}) {
  const err = new Error(message || '请求失败');
  Object.assign(err, extra);
  return err;
}

export function formatApiError(err) {
  const parts = [err?.message || '请求失败'];
  if (err?.code) parts.push(`code: ${err.code}`);
  if (err?.requestId) parts.push(`request_id: ${err.requestId}`);
  return parts.join(' | ');
}

async function readBody(response) {
  const ct = response.headers.get('content-type') || '';
  if (ct.includes('application/json')) return await response.json();
  return await response.text();
}

export async function request(path, options = {}) {
  const session = useSessionStore();
  const headers = new Headers(options.headers || {});
  const requestId = options.requestId || newRequestId();
  headers.set(REQUEST_ID_HEADER, requestId);
  if (session.token) headers.set('Authorization', `Bearer ${session.token}`);
  if (options.body && !(options.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  const timeoutMs = options.timeoutMs ?? DEFAULT_TIMEOUT_MS;
  const base = normalizeBase(session.apiBase);
  const requestUrl = `${base}${path}`;
  const fetchOptions = { ...options, headers };
  let response;
  try {
    response = await fetchWithTimeout(requestUrl, fetchOptions, timeoutMs);
  } catch (err) {
    if (base && path.startsWith('/')) {
      try {
        response = await fetchWithTimeout(path, fetchOptions, timeoutMs);
        session.setApiBase('');
      } catch {
        throw connectionError(err, requestUrl, requestId, timeoutMs);
      }
    } else {
      throw connectionError(err, requestUrl, requestId, timeoutMs);
    }
  }

  if (base && path.startsWith('/') && response.status === 404) {
    try {
      const fallbackResponse = await fetchWithTimeout(path, fetchOptions, timeoutMs);
      if (fallbackResponse.ok || fallbackResponse.status !== 404) {
        response = fallbackResponse;
        session.setApiBase('');
      }
    } catch {
      /* Keep the original 404 response. */
    }
  }

  const responseRequestId = response.headers.get(REQUEST_ID_HEADER) || requestId;
  const body = await readBody(response);

  if (!response.ok) {
    if (response.status === 401 && session.token) {
      session.clear();
      useToastStore().show('登录已过期，请重新登录', 'error');
      const router = (await import('../router')).default;
      router.replace({ name: 'login' });
      throw makeApiError('登录已过期', { requestId: responseRequestId, status: response.status });
    }
    if (body && typeof body === 'object') {
      throw makeApiError(body.message || body.code || `HTTP ${response.status}`, {
        code: body.code,
        details: body.details,
        requestId: responseRequestId,
        status: response.status,
      });
    }
    throw makeApiError(body || `HTTP ${response.status}`, {
      requestId: responseRequestId,
      status: response.status,
    });
  }

  try {
    return unwrapEnvelope(body);
  } catch (err) {
    err.requestId = responseRequestId;
    throw err;
  }
}

export async function fetchCaptcha() {
  const session = useSessionStore();
  const requestId = newRequestId();
  const resp = await fetch(apiUrl('/api/v1/auth/captcha'), {
    cache: 'no-store',
    headers: { [REQUEST_ID_HEADER]: requestId },
  });
  if (!resp.ok) {
    throw makeApiError('获取验证码失败', {
      requestId: resp.headers.get(REQUEST_ID_HEADER) || requestId,
      status: resp.status,
    });
  }
  session.setCaptchaId(resp.headers.get('X-Captcha-Id') || '');
  return await resp.blob();
}
