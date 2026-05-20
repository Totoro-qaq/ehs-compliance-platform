<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue';
import {
  createTask,
  deleteTask,
  getTask,
  listTasks,
  requeueTask,
  streamTaskProgress,
} from '../api/assessment';
import { formatApiError } from '../api/client';
import { listOrganizations } from '../api/organizations';
import { useSessionStore } from '../stores/session';
import { useToastStore } from '../stores/toast';
import { formatTime, statusText } from '../utils/format';
import Icon from '../components/Icon.vue';

const TERMINAL_STATUSES = new Set(['SUCCESS', 'FAILED']);
const POLL_INTERVAL_MS = 5000;
const MAX_FILE_BYTES = 50 * 1024 * 1024;
const ALLOWED_EXTENSIONS = new Set(['pdf', 'txt', 'doc', 'docx', 'csv']);

const session = useSessionStore();
const toast = useToastStore();

const tasks = ref([]);
const totalTasks = ref(0);
const totalPages = ref(0);
const currentPage = ref(1);
const pageSize = 15;

const organizations = ref([]);
const orgSelected = ref('');
const statusFilter = ref('');
const searchText = ref('');

const showUpload = ref(false);
const fileInput = ref(null);
const fileLabel = ref('点击或拖拽文件到此处');
const hasFile = ref(false);
const selectedFile = ref(null);
const uploadBusy = ref(false);

const drawerOpen = ref(false);
const activeTask = ref(null);
const sseConnected = ref(false);
const requeueBusyTaskId = ref('');

const taskCountText = computed(() => `${totalTasks.value} 条任务`);

const hasPendingTasks = computed(() => tasks.value.some((t) => !TERMINAL_STATUSES.has(t.status)));
const activeRiskCount = computed(() => activeTask.value?.result?.risks?.length || 0);

let pollTimer = null;
let progressStream = null;
let searchTimer = null;

function stopPolling() {
  if (pollTimer) {
    clearInterval(pollTimer);
    pollTimer = null;
  }
}

function startPolling() {
  stopPolling();
  pollTimer = setInterval(async () => {
    if (document.hidden) return;
    if (!hasPendingTasks.value) {
      stopPolling();
      return;
    }
    await loadTasks({ silent: true });
    if (activeTask.value && !TERMINAL_STATUSES.has(activeTask.value.status)) {
      try {
        activeTask.value = await getTask(activeTask.value.task_id);
      } catch {
        /* 静默 */
      }
    }
  }, POLL_INTERVAL_MS);
}

async function loadOrganizations() {
  try {
    const page = await listOrganizations(1, 200);
    organizations.value = page?.items || [];
    if (organizations.value.length) {
      orgSelected.value = organizations.value[0].id;
      session.setOrgName(organizations.value[0].name || '默认组织');
    } else {
      orgSelected.value = '';
    }
  } catch (err) {
    toast.show(formatApiError(err), 'error');
  }
}

async function loadTasks({ silent = false } = {}) {
  try {
    const page = await listTasks(currentPage.value, pageSize, {
      status: statusFilter.value,
      q: searchText.value.trim(),
    });
    tasks.value = page?.items || [];
    totalTasks.value = page?.total || 0;
    totalPages.value = page?.pages || 1;
  } catch (err) {
    if (!silent) toast.show(formatApiError(err), 'error');
  }
}

async function refreshAll() {
  await loadOrganizations();
  await loadTasks();
}

async function refreshClick() {
  try {
    await refreshAll();
    toast.show('数据已刷新', 'success');
  } catch (err) {
    toast.show(formatApiError(err), 'error');
  }
}

function goToPage(page) {
  if (page < 1 || page > totalPages.value) return;
  currentPage.value = page;
  loadTasks();
}

function onFileChange(e) {
  const f = e.target.files?.[0];
  selectedFile.value = f || null;
  hasFile.value = Boolean(f);
  if (!f) {
    fileLabel.value = '点击或拖拽文件到此处';
    return;
  }
  const ext = f.name.split('.').pop()?.toLowerCase() || '';
  if (!ALLOWED_EXTENSIONS.has(ext)) {
    toast.show('仅支持 PDF、TXT、DOC、DOCX、CSV 文件', 'error');
    resetUpload();
    return;
  }
  if (f.size > MAX_FILE_BYTES) {
    toast.show('文件大小不能超过 50MB', 'error');
    resetUpload();
    return;
  }
  fileLabel.value = f.name;
}

function resetUpload() {
  if (fileInput.value) fileInput.value.value = '';
  hasFile.value = false;
  selectedFile.value = null;
  fileLabel.value = '点击或拖拽文件到此处';
}

async function submitUpload() {
  if (uploadBusy.value) return;
  uploadBusy.value = true;
  try {
    const file = selectedFile.value || fileInput.value?.files?.[0];
    if (!file) throw new Error('请选择文件');
    const data = await createTask(file, orgSelected.value);
    session.setSelectedTaskId(data.task_id);
    resetUpload();
    showUpload.value = false;
    toast.show('任务已创建', 'success');
    currentPage.value = 1;
    await loadTasks();
    await selectTask(data.task_id);
  } catch (err) {
    toast.show(formatApiError(err), 'error');
  } finally {
    uploadBusy.value = false;
  }
}

async function selectTask(taskId) {
  if (!taskId) return;
  session.setSelectedTaskId(taskId);
  try {
    activeTask.value = await getTask(taskId);
    drawerOpen.value = true;
    subscribeActiveTaskProgress(taskId);
  } catch (err) {
    toast.show(formatApiError(err), 'error');
  }
}

function closeDrawer() {
  drawerOpen.value = false;
  closeProgressStream();
}

function onDrawerLeft() {
  activeTask.value = null;
}

async function deleteActiveTask() {
  if (!activeTask.value) return;
  if (!confirm('确认删除当前任务？此操作可由管理员恢复。')) return;
  try {
    await deleteTask(activeTask.value.task_id);
    session.setSelectedTaskId('');
    closeDrawer();
    toast.show('任务已删除', 'success');
    if (tasks.value.length === 1 && currentPage.value > 1) {
      currentPage.value -= 1;
    }
    await loadTasks();
  } catch (err) {
    toast.show(formatApiError(err), 'error');
  }
}

function canRequeue(task) {
  return task?.status === 'FAILED';
}

async function requeueAssessment(taskId) {
  if (!taskId || requeueBusyTaskId.value) return;
  requeueBusyTaskId.value = taskId;
  try {
    await requeueTask(taskId);
    toast.show('任务已重新投递', 'success');
    await loadTasks({ silent: true });
    if (activeTask.value?.task_id === taskId) {
      activeTask.value = await getTask(taskId);
      subscribeActiveTaskProgress(taskId);
    }
    startPolling();
  } catch (err) {
    toast.show(formatApiError(err), 'error');
  } finally {
    requeueBusyTaskId.value = '';
  }
}

async function requeueFromRow(task, event) {
  event?.stopPropagation();
  await requeueAssessment(task.task_id);
}

function closeProgressStream() {
  if (progressStream) {
    progressStream.close();
    progressStream = null;
  }
  sseConnected.value = false;
}

async function subscribeActiveTaskProgress(taskId) {
  closeProgressStream();
  if (!session.token) return;
  const current = activeTask.value;
  if (current && TERMINAL_STATUSES.has(current.status)) return;
  try {
    progressStream = await streamTaskProgress(taskId, session.token, {
      onProgress(payload) {
        applyProgressPayload(payload);
      },
      async onComplete(payload) {
        applyProgressPayload(payload);
        await refreshTaskAndList(taskId);
        closeProgressStream();
      },
      onError(err) {
        if (err?.message) toast.show(formatApiError(err), 'error');
        closeProgressStream();
      },
    });
    sseConnected.value = true;
  } catch (err) {
    toast.show(formatApiError(err), 'error');
  }
}

function applyProgressPayload(payload) {
  if (!payload || payload.task_id !== activeTask.value?.task_id) return;
  activeTask.value = {
    ...activeTask.value,
    status: payload.status || activeTask.value.status,
    progress: payload.progress ?? activeTask.value.progress,
    error_message: payload.error_message ?? activeTask.value.error_message,
  };
  const idx = tasks.value.findIndex((t) => t.task_id === payload.task_id);
  if (idx !== -1) {
    tasks.value[idx] = { ...tasks.value[idx], ...activeTask.value };
  }
}

async function refreshTaskAndList(taskId) {
  try {
    activeTask.value = await getTask(taskId);
    await loadTasks({ silent: true });
  } catch {
    /* 静默 */
  }
}

function applyFilters() {
  currentPage.value = 1;
  loadTasks();
}

function onSearchInput() {
  clearTimeout(searchTimer);
  searchTimer = setTimeout(applyFilters, 300);
}

function resetFilters() {
  statusFilter.value = '';
  searchText.value = '';
  applyFilters();
}

const drawerSummary = computed(() => activeTask.value?.result?.summary || '');
const drawerRisks = computed(() => activeTask.value?.result?.risks || []);
const drawerParsed = computed(() => {
  const text = activeTask.value?.parsed_text;
  return text ? text.slice(0, 2000) : '';
});

function riskTitle(risk, index) {
  return risk.description || risk.violated_standard || `风险 ${index + 1}`;
}

function riskSeverity(risk) {
  return risk.severity || risk.risk_level || 'MEDIUM';
}

onMounted(refreshAll);

watch(
  hasPendingTasks,
  (pending) => {
    if (pending) startPolling();
    else stopPolling();
  },
  { immediate: true },
);

onBeforeUnmount(stopPolling);
onBeforeUnmount(closeProgressStream);
onBeforeUnmount(() => clearTimeout(searchTimer));
</script>

<template>
  <div class="view-container">
    <header class="view-header">
      <div>
        <h1>评估任务</h1>
        <p class="view-desc">管理和查看 EHS 合规评估任务</p>
      </div>
      <div class="header-actions">
        <button type="button" class="btn-secondary" @click="refreshClick">
          <Icon name="refresh" :size="14" />
          刷新
        </button>
        <button type="button" class="btn-primary" @click="showUpload = !showUpload">
          <Icon name="plus" :size="14" />
          新建任务
        </button>
      </div>
    </header>

    <section v-if="showUpload" class="upload-panel">
      <div class="upload-panel-inner">
        <h3>创建评估任务</h3>
        <p>上传 PDF、TXT、DOC、DOCX 或 CSV 格式的评价材料</p>
        <form class="upload-form" @submit.prevent="submitUpload">
          <div class="form-row">
            <label class="form-field">
              <span class="label-text">所属公司</span>
              <select v-model="orgSelected">
                <option v-if="!organizations.length" value="">默认公司</option>
                <option v-for="org in organizations" :key="org.id" :value="org.id">
                  {{ org.name || org.id }}
                </option>
              </select>
            </label>
            <label class="form-field file-field">
              <span class="label-text">评估文件</span>
              <div :class="['file-drop', { 'has-file': hasFile }]">
                <input
                  ref="fileInput"
                  type="file"
                  accept=".pdf,.txt,.doc,.docx,.csv"
                  required
                  @change="onFileChange"
                />
                <Icon name="upload" :size="24" :stroke="1.5" />
                <span class="file-drop-text">{{ fileLabel }}</span>
                <span class="file-drop-hint">支持 PDF, TXT, DOC, DOCX, CSV (最大 50MB)</span>
              </div>
            </label>
          </div>
          <div class="form-actions">
            <button type="button" class="btn-secondary" @click="showUpload = false">取消</button>
            <button type="submit" class="btn-primary" :disabled="uploadBusy || !hasFile">
              {{ uploadBusy ? '创建中...' : '开始评估' }}
            </button>
          </div>
        </form>
      </div>
    </section>

    <section class="task-list-section">
      <div class="task-filters">
        <label class="filter-field">
          <span class="label-text">状态</span>
          <select v-model="statusFilter" @change="applyFilters">
            <option value="">全部状态</option>
            <option value="PENDING">待处理</option>
            <option value="PARSING">解析中</option>
            <option value="AI_ANALYZING">AI 分析中</option>
            <option value="VALIDATING">校验中</option>
            <option value="PERSISTING">保存中</option>
            <option value="SUCCESS">成功</option>
            <option value="FAILED">失败</option>
          </select>
        </label>
        <label class="filter-field filter-search">
          <span class="label-text">搜索</span>
          <input v-model="searchText" type="search" placeholder="文件名或任务 ID" @input="onSearchInput" />
        </label>
        <button type="button" class="btn-secondary filter-reset" @click="resetFilters">重置</button>
      </div>
      <div class="task-list-header">
        <span class="task-count">{{ taskCountText }}</span>
        <div class="pagination">
          <template v-if="totalPages > 1">
            <button class="page-btn" :disabled="currentPage <= 1" @click="goToPage(currentPage - 1)">
              &lt;
            </button>
            <span class="page-info">{{ currentPage }} / {{ totalPages }}</span>
            <button class="page-btn" :disabled="currentPage >= totalPages" @click="goToPage(currentPage + 1)">
              &gt;
            </button>
          </template>
        </div>
      </div>
      <div class="task-table-wrap">
        <table class="task-table">
          <thead>
            <tr>
              <th>文件名</th>
              <th>状态</th>
              <th>进度</th>
              <th>风险数</th>
              <th>创建时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!tasks.length" class="empty-row">
              <td colspan="6">暂无评估任务</td>
            </tr>
            <tr
              v-for="task in tasks"
              :key="task.task_id"
              :data-task-id="task.task_id"
              :class="{ selected: task.task_id === session.selectedTaskId }"
              @click="selectTask(task.task_id)"
            >
              <td>
                <span class="task-filename">{{ task.filename || task.task_id }}</span>
              </td>
              <td>
                <span :class="['status-badge', task.status || '']">{{ statusText(task.status) }}</span>
              </td>
              <td>
                <div class="progress-bar">
                  <div class="progress-bar-fill" :style="{ width: `${task.progress ?? 0}%` }"></div>
                </div>
                <span class="progress-text">{{ task.progress ?? 0 }}%</span>
              </td>
              <td>{{ task.result?.risks?.length ?? '-' }}</td>
              <td>{{ formatTime(task.created_at) }}</td>
              <td>
                <button
                  v-if="canRequeue(task)"
                  type="button"
                  class="btn-row-action"
                  :disabled="requeueBusyTaskId === task.task_id"
                  @click="requeueFromRow(task, $event)"
                >
                  <Icon name="rotate" :size="13" />
                  {{ requeueBusyTaskId === task.task_id ? '投递中' : '重新分析' }}
                </button>
                <span v-else class="row-action-placeholder">-</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <Transition name="drawer" @after-leave="onDrawerLeft">
      <aside v-if="drawerOpen" class="task-drawer open">
        <div class="drawer-header">
          <h2>{{ activeTask?.filename || activeTask?.task_id || '任务详情' }}</h2>
          <div class="drawer-actions">
            <button
              v-if="canRequeue(activeTask)"
              type="button"
              class="btn-secondary"
              :disabled="requeueBusyTaskId === activeTask.task_id"
              @click="requeueAssessment(activeTask.task_id)"
            >
              <Icon name="rotate" :size="14" />
              {{ requeueBusyTaskId === activeTask.task_id ? '投递中' : '重新分析' }}
            </button>
            <button type="button" class="btn-danger-ghost" :disabled="!activeTask" @click="deleteActiveTask">
              删除
            </button>
            <button type="button" class="btn-icon-sm" @click="closeDrawer">
              <Icon name="close" />
            </button>
          </div>
        </div>
        <div class="drawer-body">
          <p v-if="!activeTask" class="empty-state">选择一个任务查看详情</p>
          <template v-else>
            <dl class="detail-meta">
              <dt>任务 ID</dt>
              <dd>{{ activeTask.task_id }}</dd>
              <dt>状态</dt>
              <dd>
                <span :class="['status-badge', activeTask.status || '']">{{
                  statusText(activeTask.status)
                }}</span>
                <span v-if="sseConnected" class="live-chip">实时</span>
              </dd>
              <dt>进度</dt>
              <dd>{{ activeTask.progress ?? 0 }}%</dd>
              <dt>风险数</dt>
              <dd>{{ activeRiskCount }}</dd>
              <dt>创建时间</dt>
              <dd>{{ formatTime(activeTask.created_at) }}</dd>
              <template v-if="activeTask.error_message">
                <dt>错误信息</dt>
                <dd style="color: var(--danger)">{{ activeTask.error_message }}</dd>
              </template>
            </dl>
            <div v-if="drawerSummary" class="detail-section">
              <h3>评估摘要</h3>
              <p style="font-size: 14px; line-height: 1.7; color: var(--text-secondary)">
                {{ drawerSummary }}
              </p>
            </div>
            <div class="detail-section">
              <h3>风险项 ({{ drawerRisks.length }})</h3>
              <p v-if="!drawerRisks.length" class="empty-state">暂无风险项</p>
              <div v-for="(risk, idx) in drawerRisks" :key="idx" class="risk-card">
                <div class="risk-card-header">
                  <span class="risk-card-title">{{ riskTitle(risk, idx) }}</span>
                  <span :class="['risk-severity', riskSeverity(risk)]">{{ riskSeverity(risk) }}</span>
                </div>
                <div class="risk-card-body">
                  <p v-if="risk.recommendation || risk.rectification_advice">
                    <span class="risk-label">整改建议：</span
                    >{{ risk.recommendation || risk.rectification_advice }}
                  </p>
                  <p v-if="risk.evidence"><span class="risk-label">现场证据：</span>{{ risk.evidence }}</p>
                </div>
              </div>
            </div>
            <div v-if="drawerParsed" class="detail-section">
              <h3>解析文本预览</h3>
              <div class="parsed-text-block">{{ drawerParsed }}</div>
            </div>
          </template>
        </div>
      </aside>
    </Transition>
  </div>
</template>

<style scoped>
.drawer-enter-from,
.drawer-leave-to {
  transform: translateX(100%);
  opacity: 0;
}
.drawer-enter-active,
.drawer-leave-active {
  transition:
    transform 0.26s ease,
    opacity 0.26s ease;
}
</style>
