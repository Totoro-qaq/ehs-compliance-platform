import { defineStore } from 'pinia';

const KEYS = {
  apiBase: 'ehs.apiBase',
  token: 'ehs.token',
  username: 'ehs.username',
  role: 'ehs.role',
  orgName: 'ehs.orgName',
  selectedTaskId: 'ehs.selectedTaskId',
};

function parseJwtRole(token) {
  try {
    const payload = JSON.parse(atob(token.split('.')[1]));
    return payload.role || 'USER';
  } catch {
    return 'USER';
  }
}

const DEFAULT_API_BASE = (import.meta.env?.VITE_API_BASE || '').trim();

export const useSessionStore = defineStore('session', {
  state: () => ({
    apiBase: DEFAULT_API_BASE,
    token: '',
    username: '',
    role: '',
    orgName: '',
    selectedTaskId: '',
    captchaId: '',
  }),
  getters: {
    isAdmin: (state) => state.role === 'ADMIN',
    roleText: (state) => (state.role === 'ADMIN' ? '管理员' : '普通用户'),
    avatarInitial: (state) => (state.username || '?')[0].toUpperCase(),
  },
  actions: {
    hydrate() {
      const saved = localStorage.getItem(KEYS.apiBase);
      this.apiBase = saved !== null ? saved : DEFAULT_API_BASE;
      this.token = localStorage.getItem(KEYS.token) || '';
      this.username = localStorage.getItem(KEYS.username) || '';
      this.role = localStorage.getItem(KEYS.role) || '';
      this.orgName = localStorage.getItem(KEYS.orgName) || '';
      this.selectedTaskId = localStorage.getItem(KEYS.selectedTaskId) || '';
    },
    setApiBase(value) {
      this.apiBase = value;
      localStorage.setItem(KEYS.apiBase, value);
    },
    setCaptchaId(id) {
      this.captchaId = id || '';
    },
    setSession(token, username) {
      this.token = token || '';
      this.username = username || '';
      this.role = token ? parseJwtRole(token) : '';
      if (this.token) {
        localStorage.setItem(KEYS.token, this.token);
        localStorage.setItem(KEYS.username, this.username);
        localStorage.setItem(KEYS.role, this.role);
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
      this.token = '';
      this.username = '';
      this.role = '';
      this.orgName = '';
      this.selectedTaskId = '';
      localStorage.removeItem(KEYS.token);
      localStorage.removeItem(KEYS.username);
      localStorage.removeItem(KEYS.role);
      localStorage.removeItem(KEYS.orgName);
      localStorage.removeItem(KEYS.selectedTaskId);
    },
  },
});
