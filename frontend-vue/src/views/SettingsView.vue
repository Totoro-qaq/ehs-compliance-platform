<script setup>
import { computed, onMounted, reactive, ref } from 'vue';
import { useRouter } from 'vue-router';
import { changePassword } from '../api/auth';
import { formatApiError, normalizeBase } from '../api/client';
import { getOrganization } from '../api/organizations';
import Icon from '../components/Icon.vue';
import { inferDefaultApiBase, useSessionStore } from '../stores/session';
import { useToastStore } from '../stores/toast';

const session = useSessionStore();
const toast = useToastStore();
const router = useRouter();

const showPasswordForm = ref(false);
const company = ref(null);
const companyBusy = ref(false);
const pwd = reactive({ old: '', next: '', confirm: '' });

const apiBaseInput = ref('');
const apiTesting = ref(false);
const apiStatus = ref('');

const companyName = computed(() => company.value?.name || session.orgName || '未绑定公司');
const currentApiText = computed(() => session.apiBase || '同源 / Vite 代理');
const companyRows = computed(() => [
  { label: '公司名称', value: companyName.value },
  { label: '所属行业', value: company.value?.industry || '-' },
  { label: '统一社会信用代码', value: company.value?.unified_social_credit_code || '-' },
  { label: '公司地址', value: company.value?.address || '-' },
  { label: '联系人', value: company.value?.contact_name || '-' },
  { label: '联系电话', value: company.value?.contact_phone || '-' },
  { label: '备注', value: company.value?.notes || '-' },
]);

const passwordScore = computed(() => {
  let score = 0;
  if (pwd.next.length >= 8) score += 1;
  if (/[A-Z]/.test(pwd.next) && /[a-z]/.test(pwd.next)) score += 1;
  if (/\d/.test(pwd.next)) score += 1;
  if (/[^A-Za-z0-9]/.test(pwd.next)) score += 1;
  return score;
});

const passwordStrengthText = computed(() => {
  if (!pwd.next) return '请输入新密码';
  if (passwordScore.value <= 1) return '强度偏弱';
  if (passwordScore.value === 2) return '强度一般';
  return '强度较好';
});

const passwordStrengthClass = computed(() => {
  if (!pwd.next) return '';
  if (passwordScore.value <= 1) return 'weak';
  if (passwordScore.value === 2) return 'medium';
  return 'strong';
});

function resetPasswordFields() {
  pwd.old = '';
  pwd.next = '';
  pwd.confirm = '';
}

function cancelPasswordChange() {
  resetPasswordFields();
  showPasswordForm.value = false;
}

async function submitPassword() {
  if (pwd.next !== pwd.confirm) {
    toast.show('两次输入的新密码不一致', 'error');
    return;
  }
  try {
    await changePassword(pwd.old, pwd.next);
    resetPasswordFields();
    showPasswordForm.value = false;
    toast.show('密码修改成功，请使用新密码重新登录', 'success');
    setTimeout(() => {
      session.clear();
      router.replace({ name: 'login' });
    }, 1500);
  } catch (err) {
    toast.show(formatApiError(err), 'error');
  }
}

function logout() {
  session.clear();
  toast.show('已退出登录', 'info');
  router.replace({ name: 'login' });
}

function goHome() {
  router.push({ name: 'home', query: { view: 'workbench' } });
}

async function loadCompany() {
  companyBusy.value = true;
  try {
    if (session.orgId) {
      company.value = await getOrganization(session.orgId);
    } else if (session.isAdmin) {
      company.value = null;
    }
    if (company.value?.name) session.setOrgName(company.value.name);
  } catch (err) {
    toast.show(formatApiError(err), 'error');
  } finally {
    companyBusy.value = false;
  }
}

function initApiBase() {
  apiBaseInput.value = session.apiBase || '';
}

async function testApiConnection() {
  apiTesting.value = true;
  apiStatus.value = '';
  const base = normalizeBase(apiBaseInput.value);
  const url = `${base}/api/v1/healthz`;
  try {
    const resp = await fetch(url, { signal: AbortSignal.timeout(5000) });
    apiStatus.value = resp.ok ? '连接正常' : `服务器返回 HTTP ${resp.status}`;
  } catch {
    apiStatus.value = '无法连接，请检查地址和服务状态';
  } finally {
    apiTesting.value = false;
  }
}

function saveApiBase() {
  const normalized = normalizeBase(apiBaseInput.value);
  session.setApiBase(normalized);
  apiBaseInput.value = normalized;
  toast.show('API 地址已保存', 'success');
  apiStatus.value = '';
}

function resetApiBase() {
  session.setApiBase(inferDefaultApiBase());
  apiBaseInput.value = session.apiBase;
  toast.show('已重置为默认地址', 'info');
  apiStatus.value = '';
}

onMounted(() => {
  loadCompany();
  initApiBase();
});
</script>

<template>
  <div class="view-container settings-view">
    <header class="settings-page-head">
      <button type="button" class="btn-secondary" @click="goHome">
        <Icon name="home" :size="14" />
        返回工作台
      </button>
      <div>
        <h1>账户设置</h1>
        <p class="view-desc">查看本人账号和所属公司信息，管理安全状态和后端连接。</p>
      </div>
    </header>

    <div class="settings-board">
      <div class="settings-column">
        <section class="settings-card profile-card">
          <div class="settings-card-header">
            <h3>个人信息</h3>
            <span class="settings-badge neutral">当前账号</span>
          </div>
          <div class="settings-card-body">
            <div class="profile-summary">
              <div class="profile-avatar">{{ session.avatarInitial }}</div>
              <div>
                <strong>{{ session.username || '-' }}</strong>
                <span>{{ session.roleText }} · {{ companyName }}</span>
              </div>
            </div>
            <div class="field-list">
              <div class="field-row">
                <span class="field-label">用户名</span>
                <span class="field-value">{{ session.username || '-' }}</span>
              </div>
              <div class="field-row">
                <span class="field-label">角色</span>
                <span class="field-value">{{ session.roleText }}</span>
              </div>
              <div class="field-row">
                <span class="field-label">所属公司</span>
                <span class="field-value">{{ companyName }}</span>
              </div>
            </div>
          </div>
        </section>

        <section class="settings-card">
          <div class="settings-card-header">
            <h3>API 连接</h3>
            <span class="settings-badge neutral">后端服务</span>
          </div>
          <div class="settings-card-body">
            <div class="api-current">
              <span>当前地址</span>
              <strong>{{ currentApiText }}</strong>
            </div>
            <label class="form-field">
              <span class="label-text">后端接口地址</span>
              <input
                v-model="apiBaseInput"
                type="text"
                placeholder="留空表示同源代理，或输入 http://localhost:8000"
                @keyup.enter="saveApiBase"
              />
            </label>
            <div v-if="apiStatus" :class="['api-status-msg', apiStatus === '连接正常' ? 'ok' : 'err']">
              {{ apiStatus }}
            </div>
            <div class="compact-actions">
              <button type="button" class="btn-secondary" :disabled="apiTesting" @click="testApiConnection">
                {{ apiTesting ? '测试中...' : '测试连接' }}
              </button>
              <button type="button" class="btn-secondary" @click="resetApiBase">重置默认</button>
              <button type="button" class="btn-primary" @click="saveApiBase">保存</button>
            </div>
          </div>
        </section>
      </div>

      <div class="settings-column">
        <section class="settings-card">
          <div class="settings-card-header">
            <h3>公司信息</h3>
            <span class="settings-badge neutral">只读</span>
          </div>
          <div class="settings-card-body">
            <div v-if="companyBusy" class="empty-state compact">加载中...</div>
            <div v-else class="field-list">
              <div v-for="row in companyRows" :key="row.label" class="field-row">
                <span class="field-label">{{ row.label }}</span>
                <span class="field-value">{{ row.value }}</span>
              </div>
            </div>
          </div>
        </section>

        <section class="settings-card">
          <div class="settings-card-header">
            <h3>安全与账户</h3>
            <span class="settings-badge">已登录</span>
          </div>
          <div class="settings-card-body">
            <div class="field-list">
              <div class="field-row">
                <span class="field-label">登录方式</span>
                <span class="field-value">账号密码</span>
              </div>
              <div class="field-row">
                <span class="field-label">密码状态</span>
                <span class="field-value session-active">已启用</span>
              </div>
            </div>

            <div v-if="!showPasswordForm" class="compact-actions">
              <button type="button" class="btn-primary" @click="showPasswordForm = true">修改密码</button>
              <button type="button" class="btn-danger-ghost" @click="logout">退出当前会话</button>
            </div>

            <form v-else class="settings-form security-form" @submit.prevent="submitPassword">
              <label class="form-field">
                <span class="label-text">当前密码</span>
                <input v-model="pwd.old" type="password" autocomplete="current-password" required />
              </label>
              <label class="form-field">
                <span class="label-text">新密码</span>
                <input
                  v-model="pwd.next"
                  type="password"
                  autocomplete="new-password"
                  required
                  placeholder="8位以上，含大小写字母和数字"
                />
              </label>
              <div :class="['password-strength', passwordStrengthClass]">
                <span></span>
                <small>{{ passwordStrengthText }}</small>
              </div>
              <label class="form-field">
                <span class="label-text">确认新密码</span>
                <input v-model="pwd.confirm" type="password" autocomplete="new-password" required />
              </label>
              <div class="form-actions">
                <button type="button" class="btn-secondary" @click="cancelPasswordChange">取消</button>
                <button type="submit" class="btn-primary">更新密码</button>
              </div>
            </form>
          </div>
        </section>
      </div>
    </div>
  </div>
</template>

<style scoped>
.settings-view {
  max-width: none;
}

.settings-page-head {
  display: flex;
  align-items: center;
  gap: 16px;
  margin-bottom: 18px;
}

.settings-page-head h1 {
  font-size: 24px;
  font-weight: 700;
}

.settings-board {
  display: grid;
  grid-template-columns: minmax(300px, 0.92fr) minmax(420px, 1.08fr);
  gap: 16px;
  align-items: start;
}

.settings-column {
  display: grid;
  gap: 16px;
  min-width: 0;
}

.settings-card {
  overflow: hidden;
  border: 1px solid var(--border);
  border-radius: 10px;
  background: var(--panel);
  box-shadow: var(--shadow-sm);
}

.settings-card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 12px 14px;
  border-bottom: 1px solid var(--border);
  background: #fafafa;
}

.settings-card-header h3 {
  font-size: 14px;
  font-weight: 700;
}

.settings-card-body {
  padding: 14px;
}

.settings-badge {
  flex: 0 0 auto;
  padding: 3px 8px;
  border-radius: 999px;
  background: var(--success-bg);
  color: var(--success);
  font-size: 11px;
  font-weight: 700;
}

.settings-badge.neutral {
  background: var(--bg-subtle);
  color: var(--text-secondary);
}

.profile-summary {
  display: flex;
  align-items: center;
  gap: 12px;
  padding-bottom: 12px;
  margin-bottom: 4px;
  border-bottom: 1px solid var(--border-subtle);
}

.profile-summary strong {
  display: block;
  font-size: 16px;
  line-height: 1.2;
}

.profile-summary span {
  display: block;
  margin-top: 3px;
  color: var(--text-secondary);
  font-size: 12px;
}

.profile-avatar {
  display: flex;
  align-items: center;
  justify-content: center;
  flex: 0 0 auto;
  width: 44px;
  height: 44px;
  border-radius: 50%;
  background: var(--accent-light);
  color: var(--accent);
  font-size: 17px;
  font-weight: 800;
}

.field-list {
  display: grid;
}

.field-row {
  display: grid;
  grid-template-columns: 120px minmax(0, 1fr);
  gap: 12px;
  align-items: start;
  padding: 8px 0;
  border-bottom: 1px solid var(--border-subtle);
}

.field-row:last-child {
  border-bottom: 0;
}

.field-label {
  color: var(--text-secondary);
  font-size: 12px;
}

.field-value {
  min-width: 0;
  color: var(--text);
  font-size: 13px;
  font-weight: 600;
  text-align: left;
  word-break: break-word;
}

.session-active {
  color: var(--success);
}

.compact-actions {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  justify-content: flex-end;
  margin-top: 14px;
}

.security-form {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px solid var(--border-subtle);
}

.settings-form .form-field {
  margin-bottom: 12px;
}

.password-strength {
  display: flex;
  align-items: center;
  gap: 8px;
  margin: -2px 0 12px;
}

.password-strength span {
  width: 82px;
  height: 6px;
  overflow: hidden;
  border-radius: 999px;
  background: var(--border);
}

.password-strength span::before {
  content: '';
  display: block;
  width: 0;
  height: 100%;
  border-radius: inherit;
  background: var(--text-tertiary);
}

.password-strength.weak span::before { width: 35%; background: var(--danger); }
.password-strength.medium span::before { width: 65%; background: var(--warning); }
.password-strength.strong span::before { width: 100%; background: var(--success); }

.password-strength small {
  color: var(--text-secondary);
  font-size: 12px;
}

.api-current {
  display: grid;
  gap: 4px;
  margin-bottom: 12px;
  padding: 10px 12px;
  border: 1px solid var(--border-subtle);
  border-radius: 8px;
  background: var(--bg-subtle);
}

.api-current span {
  color: var(--text-secondary);
  font-size: 12px;
}

.api-current strong {
  color: var(--text);
  font-size: 13px;
  word-break: break-all;
}

.api-status-msg {
  margin: -2px 0 10px;
  font-size: 12px;
}

.api-status-msg.ok { color: var(--success); }
.api-status-msg.err { color: var(--danger); }

@media (max-width: 900px) {
  .settings-board {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 640px) {
  .settings-page-head {
    align-items: flex-start;
    flex-direction: column;
  }

  .field-row {
    grid-template-columns: 1fr;
    gap: 3px;
  }

  .compact-actions {
    flex-direction: column;
    justify-content: stretch;
  }

  .compact-actions button {
    width: 100%;
    justify-content: center;
  }
}
</style>
