import { defineStore } from 'pinia';
import { refreshToken as apiRefreshToken } from '../api/auth';

const KEYS = {
  apiBase: 'ehs.apiBase',
  token: 'ehs.token',
  username: 'ehs.username',
  role: 'ehs.role',
  orgId: 'ehs.orgId',
  orgName: 'ehs.orgName',
  selectedTaskId: 'ehs.selectedTaskId',
};

function parseJwtPayload(token) {
  try {
    return JSON.parse(atob(token.split('.')[1]));
  } catch {
    return null;
  }
}

function parseJwtRole(token) {
  const payload = parseJwtPayload(token);
  return payload?.role || 'USER';
}

function parseJwtUsername(token) {
  const payload = parseJwtPayload(token);
  return payload?.sub || '';
}

function parseJwtExp(token) {
  const payload = parseJwtPayload(token);
  return payload?.exp ? payload.exp * 1000 : 0;
}

function parseJwtOrgId(token) {
  const payload = parseJwtPayload(token);
  return payload?.oid || '';
}

const ENV_API_BASE = (import.meta.env?.VITE_API_BASE || '').trim();

function isLoopbackHost(hostname) {
  const host = (hostname || '').toLowerCase();
  return host === 'localhost' || host === '::1' || host === '[::1]' || host.startsWith('127.');
}

function isLoopbackApiBase(value) {
  try {
    const url = new URL(/^https?:\/\//i.test(value) ? value : `http://${value}`);
    return isLoopbackHost(url.hostname);
  } catch {
    return false;
  }
}

export function inferDefaultApiBase() {
  if (ENV_API_BASE) return ENV_API_BASE;
  return '';
}

function resolveApiBase(saved) {
  const inferred = inferDefaultApiBase();
  if (saved === null) return inferred;
  if (!ENV_API_BASE && isLoopbackApiBase(saved)) return '';
  if (
    inferred &&
    typeof window !== 'undefined' &&
    !isLoopbackHost(window.location.hostname) &&
    isLoopbackApiBase(saved)
  ) {
    return inferred;
  }
  return saved;
}

const DEFAULT_API_BASE = inferDefaultApiBase();

// 活动事件节流间隔：15 秒内不重复调度
const ACTIVITY_THROTTLE_MS = 15_000;
// 令牌过期前提前刷新的时间：10 分钟
const REFRESH_BEFORE_MS = 10 * 60 * 1000;
// 不活跃阈值：超过此时间主动清除会话
const INACTIVITY_LIMIT_MS = 60 * 60 * 1000;

export const useSessionStore = defineStore('session', {
  state: () => ({
    apiBase: DEFAULT_API_BASE,
    token: '',
    username: '',
    role: '',
    orgId: '',
    orgName: '',
    selectedTaskId: '',
    captchaId: '',

    // ---- 活动追踪与自动刷新 ----
    _tokenExpiry: 0, // JWT exp 时间戳（毫秒）
    _lastActivity: 0, // 最后一次用户活动时间戳（毫秒）
    _refreshTimer: null, // setTimeout ID
    _inactivityTimer: null, // 不活跃登出定时器 ID
    _lastActivityRecorded: 0, // 活动事件节流用
    _activityHandler: null, // 保存绑定的 handler 引用，解绑用
  }),

  getters: {
    isAdmin: (state) => state.role === 'ADMIN',
    roleText: (state) => (state.role === 'ADMIN' ? '管理员' : '普通用户'),
    avatarInitial: (state) => (state.username || '?')[0].toUpperCase(),
  },

  actions: {
    // ======================== 基础会话 ========================

    hydrate() {
      const saved = localStorage.getItem(KEYS.apiBase);
      this.apiBase = resolveApiBase(saved);
      this.token = localStorage.getItem(KEYS.token) || '';
      this.username = localStorage.getItem(KEYS.username) || '';
      this.role = localStorage.getItem(KEYS.role) || '';
      this.orgId = localStorage.getItem(KEYS.orgId) || '';
      this.orgName = localStorage.getItem(KEYS.orgName) || '';
      this.selectedTaskId = localStorage.getItem(KEYS.selectedTaskId) || '';
      if (this.token) {
        this._tokenExpiry = parseJwtExp(this.token);
        this.orgId = parseJwtOrgId(this.token) || this.orgId;
        this._startActivityTracking();
      }
    },

    setApiBase(value) {
      this.apiBase = value || '';
      if (this.apiBase) localStorage.setItem(KEYS.apiBase, this.apiBase);
      else localStorage.removeItem(KEYS.apiBase);
    },

    setCaptchaId(id) {
      this.captchaId = id || '';
    },

    setSession(token, username) {
      this.token = token || '';
      this.username = token ? parseJwtUsername(token) || username || '' : '';
      this.role = token ? parseJwtRole(token) : '';
      this.orgId = token ? parseJwtOrgId(token) : '';
      if (this.token) {
        localStorage.setItem(KEYS.token, this.token);
        localStorage.setItem(KEYS.username, this.username);
        localStorage.setItem(KEYS.role, this.role);
        if (this.orgId) localStorage.setItem(KEYS.orgId, this.orgId);
        else localStorage.removeItem(KEYS.orgId);
        this._tokenExpiry = parseJwtExp(this.token);
        this._lastActivity = Date.now();
        this._startActivityTracking();
        this._scheduleRefresh();
      } else {
        this.clear();
      }
    },

    setOrgName(name) {
      this.orgName = name || '';
      if (name) localStorage.setItem(KEYS.orgName, name);
      else localStorage.removeItem(KEYS.orgName);
    },

    setSelectedTaskId(id) {
      this.selectedTaskId = id || '';
      if (id) localStorage.setItem(KEYS.selectedTaskId, id);
      else localStorage.removeItem(KEYS.selectedTaskId);
    },

    clear() {
      this._stopActivityTracking();
      this.token = '';
      this.username = '';
      this.role = '';
      this.orgId = '';
      this.orgName = '';
      this.selectedTaskId = '';
      this._tokenExpiry = 0;
      this._lastActivity = 0;
      localStorage.removeItem(KEYS.token);
      localStorage.removeItem(KEYS.username);
      localStorage.removeItem(KEYS.role);
      localStorage.removeItem(KEYS.orgId);
      localStorage.removeItem(KEYS.orgName);
      localStorage.removeItem(KEYS.selectedTaskId);
    },

    // ======================== 活动追踪与自动刷新 ========================

    /** 绑定 DOM 事件，监听用户操作 */
    _startActivityTracking() {
      if (this._activityHandler) return;
      this._lastActivity = Date.now();
      this._activityHandler = this._onUserActivity.bind(this);
      const opts = { passive: true, capture: true };
      document.addEventListener('mousedown', this._activityHandler, opts);
      document.addEventListener('keydown', this._activityHandler, opts);
      document.addEventListener('scroll', this._activityHandler, opts);
      document.addEventListener('touchstart', this._activityHandler, opts);
      document.addEventListener('mousemove', this._activityHandler, opts);
      // 启动不活跃登出定时器（60 分钟无操作后主动清除会话）
      this._scheduleInactivityLogout();
    },

    /** 解绑 DOM 事件 */
    _stopActivityTracking() {
      if (!this._activityHandler) return;
      if (this._refreshTimer) {
        clearTimeout(this._refreshTimer);
        this._refreshTimer = null;
      }
      if (this._inactivityTimer) {
        clearTimeout(this._inactivityTimer);
        this._inactivityTimer = null;
      }
      const opts = { passive: true, capture: true };
      document.removeEventListener('mousedown', this._activityHandler, opts);
      document.removeEventListener('keydown', this._activityHandler, opts);
      document.removeEventListener('scroll', this._activityHandler, opts);
      document.removeEventListener('touchstart', this._activityHandler, opts);
      document.removeEventListener('mousemove', this._activityHandler, opts);
      this._activityHandler = null;
    },

    /** 用户活动事件处理（节流至 15s 一次） */
    _onUserActivity() {
      if (!this._activityHandler || !this.token) return;
      const now = Date.now();
      this._lastActivity = now;
      if (now - this._lastActivityRecorded < ACTIVITY_THROTTLE_MS) return;
      this._lastActivityRecorded = now;
      // 高频事件只按节流窗口重置定时器；最后活动时间始终保持最新。
      this._scheduleInactivityLogout();
      // 若因不活跃停止了刷新，重新启动
      if (!this._refreshTimer) {
        this._scheduleRefresh();
      }
    },

    /** 设置不活跃登出定时器：60 分钟无操作后主动清除会话并跳转登录页 */
    _scheduleInactivityLogout() {
      if (this._inactivityTimer) {
        clearTimeout(this._inactivityTimer);
        this._inactivityTimer = null;
      }
      if (!this.token) return;
      const idleMs = Date.now() - this._lastActivity;
      const delay = Math.max(INACTIVITY_LIMIT_MS - idleMs, 0);
      this._inactivityTimer = setTimeout(async () => {
        this._inactivityTimer = null;
        if (!this.token) return;
        const latestIdleMs = Date.now() - this._lastActivity;
        if (latestIdleMs < INACTIVITY_LIMIT_MS) {
          // 在等待期间又有活动，重新调度
          this._scheduleInactivityLogout();
          return;
        }
        // 超过 60 分钟不活跃 → 主动退出
        this.clear();
        try {
          const { useToastStore } = await import('../stores/toast');
          useToastStore().show('长时间未操作，已自动退出登录', 'info');
        } catch { /* 静默 */ }
        try {
          const router = (await import('../router')).default;
          router.replace({ name: 'login' });
        } catch { /* 静默 */ }
      }, delay);
    },

    /** 调度下一次令牌刷新 */
    _scheduleRefresh() {
      if (this._refreshTimer) {
        clearTimeout(this._refreshTimer);
        this._refreshTimer = null;
      }
      if (!this.token || this._tokenExpiry <= 0) return;

      const now = Date.now();
      // 若已超过不活跃阈值，停止刷新
      if (now - this._lastActivity > INACTIVITY_LIMIT_MS) return;

      const remaining = this._tokenExpiry - now;
      if (remaining <= 0) return; // 令牌已过期

      // 在令牌过期前 10 分钟刷新，但最少等 1 分钟
      const delay = Math.max(Math.min(remaining - REFRESH_BEFORE_MS, remaining - 60_000), 60_000);
      this._refreshTimer = setTimeout(() => this._doRefresh(), delay);
    },

    /** 执行令牌刷新 */
    async _doRefresh() {
      this._refreshTimer = null;
      if (!this.token) return;

      const now = Date.now();
      // 超过不活跃阈值 → 停止，令令牌自然过期
      if (now - this._lastActivity > INACTIVITY_LIMIT_MS) return;

      try {
        const data = await apiRefreshToken();
        if (data?.access_token) {
          this.token = data.access_token;
          this._tokenExpiry = parseJwtExp(data.access_token);
          this.username = parseJwtUsername(data.access_token) || this.username;
          this.role = parseJwtRole(data.access_token);
          this.orgId = parseJwtOrgId(data.access_token);
          localStorage.setItem(KEYS.token, this.token);
          localStorage.setItem(KEYS.username, this.username);
          localStorage.setItem(KEYS.role, this.role);
          if (this.orgId) localStorage.setItem(KEYS.orgId, this.orgId);
          else localStorage.removeItem(KEYS.orgId);
          this._lastActivity = Date.now();
        }
      } catch {
        // 刷新失败（如网络问题）静默处理，下次定时器会重试；
        // 若令牌已真正过期，后续 API 调用的 401 处理会兜底
      }
      // 无论成功与否，调度下一次刷新
      if (this.token) {
        this._scheduleRefresh();
      }
    },
  },
});
