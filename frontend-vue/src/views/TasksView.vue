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

const TERMINAL_STATUSES = new Set(['SUCCESS', 'NEEDS_REVIEW', 'FAILED']);
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
const taskStats = ref({ all: 0, active: 0, success: 0, needsReview: 0, failed: 0 });

const organizations = ref([]);
const orgSelected = ref('');
const statusFilter = ref('');
const searchText = ref('');
const clientNameFilter = ref('');
const projectNameFilter = ref('');
const projectCodeFilter = ref('');
const serviceTypeFilter = ref('');

const showUpload = ref(false);
const fileInput = ref(null);
const fileLabel = ref('点击或拖拽文件到此处');
const hasFile = ref(false);
const selectedFile = ref(null);
const taskName = ref('');
const taskClientName = ref('');
const taskProjectName = ref('');
const taskProjectCode = ref('');
const taskServiceType = ref('评价');
const uploadBusy = ref(false);

const drawerOpen = ref(false);
const activeTask = ref(null);
const sseConnected = ref(false);
const requeueBusyTaskId = ref('');
const riskFilter = ref('ALL');

const taskCountText = computed(() => `${totalTasks.value} 条任务`);
const selectedOrgName = computed(
  () => organizations.value.find((item) => item.id === orgSelected.value)?.name || '',
);
const taskNamePlaceholder = computed(() => {
  const orgName = selectedOrgName.value || '公司';
  return `${orgName} EHS合规评价 ${new Date().toISOString().slice(0, 10)}`;
});

const hasActiveWork = computed(
  () =>
    tasks.value.some((t) => !TERMINAL_STATUSES.has(t.status)) ||
    Boolean(activeTask.value && !TERMINAL_STATUSES.has(activeTask.value.status)),
);
const activeRiskCount = computed(() => activeTask.value?.result?.risks?.length || 0);
const activeTaskNeedsReview = computed(() => activeTask.value?.status === 'NEEDS_REVIEW');
const statusStageText = (status) => statusText(status) || '待处理';
const activeTaskIndex = computed(() =>
  tasks.value.findIndex((task) => task.task_id === activeTask.value?.task_id),
);
const hasPreviousTask = computed(() => activeTaskIndex.value > 0);
const hasNextTask = computed(
  () => activeTaskIndex.value !== -1 && activeTaskIndex.value < tasks.value.length - 1,
);

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
    if (!hasActiveWork.value) {
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
    const selectedOrg = organizations.value.find((item) => item.id === orgSelected.value);
    if (session.isAdmin) {
      if (!selectedOrg) orgSelected.value = '';
      session.setOrgName(selectedOrg?.name || '');
    } else if (selectedOrg) {
      session.setOrgName(selectedOrg.name || '默认组织');
    } else if (organizations.value.length) {
      orgSelected.value = organizations.value[0].id;
      session.setOrgName(organizations.value[0].name || '默认组织');
    } else {
      orgSelected.value = '';
      session.setOrgName('');
    }
  } catch (err) {
    toast.show(formatApiError(err), 'error');
  }
}

async function loadTasks({ silent = false } = {}) {
  try {
    const page = await listTasks(currentPage.value, pageSize, {
      organizationId: orgSelected.value,
      status: statusFilter.value,
      q: searchText.value.trim(),
      clientName: clientNameFilter.value.trim(),
      projectName: projectNameFilter.value.trim(),
      projectCode: projectCodeFilter.value.trim(),
      serviceType: serviceTypeFilter.value,
    });
    tasks.value = page?.items || [];
    totalTasks.value = page?.total || 0;
    totalPages.value = page?.pages || 1;
  } catch (err) {
    if (!silent) toast.show(formatApiError(err), 'error');
  }
}

async function loadTaskStats() {
  try {
    const [all, pending, parsing, analyzing, validating, persisting, success, needsReview, failed] = await Promise.all([
      listTasks(1, 1),
      listTasks(1, 1, { status: 'PENDING' }),
      listTasks(1, 1, { status: 'PARSING' }),
      listTasks(1, 1, { status: 'AI_ANALYZING' }),
      listTasks(1, 1, { status: 'VALIDATING' }),
      listTasks(1, 1, { status: 'PERSISTING' }),
      listTasks(1, 1, { status: 'SUCCESS' }),
      listTasks(1, 1, { status: 'NEEDS_REVIEW' }),
      listTasks(1, 1, { status: 'FAILED' }),
    ]);
    taskStats.value = {
      all: all?.total || 0,
      active:
        (pending?.total || 0) +
        (parsing?.total || 0) +
        (analyzing?.total || 0) +
        (validating?.total || 0) +
        (persisting?.total || 0),
      success: success?.total || 0,
      needsReview: needsReview?.total || 0,
      failed: failed?.total || 0,
    };
  } catch {
    /* 静默 */
  }
}

async function refreshAll() {
  await loadOrganizations();
  await Promise.all([loadTasks(), loadTaskStats()]);
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
  taskName.value = '';
  taskClientName.value = '';
  taskProjectName.value = '';
  taskProjectCode.value = '';
  taskServiceType.value = '评价';
}

async function submitUpload() {
  if (uploadBusy.value) return;
  uploadBusy.value = true;
  try {
    const file = selectedFile.value || fileInput.value?.files?.[0];
    if (!file) throw new Error('请选择文件');
    const data = await createTask(file, {
      organizationId: orgSelected.value,
      taskName: taskName.value,
      clientName: taskClientName.value,
      projectName: taskProjectName.value,
      projectCode: taskProjectCode.value,
      serviceType: taskServiceType.value,
    });
    session.setSelectedTaskId(data.task_id);
    resetUpload();
    showUpload.value = false;
    toast.show('任务已创建', 'success');
    statusFilter.value = '';
    searchText.value = '';
    currentPage.value = 1;
    await Promise.all([loadTasks(), loadTaskStats()]);
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
  riskFilter.value = 'ALL';
  closeProgressStream();
}

async function selectAdjacentTask(direction) {
  const nextIndex = activeTaskIndex.value + direction;
  const nextTask = tasks.value[nextIndex];
  if (!nextTask) return;
  await selectTask(nextTask.task_id);
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
    await Promise.all([loadTasks(), loadTaskStats()]);
  } catch (err) {
    toast.show(formatApiError(err), 'error');
  }
}

function canRequeue(task) {
  return task?.status === 'FAILED' || task?.status === 'NEEDS_REVIEW';
}

async function requeueAssessment(taskId) {
  if (!taskId || requeueBusyTaskId.value) return;
  requeueBusyTaskId.value = taskId;
  try {
    await requeueTask(taskId);
    toast.show('任务已重新投递', 'success');
    await Promise.all([loadTasks({ silent: true }), loadTaskStats()]);
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
  syncTaskInList(activeTask.value);
}

function taskMatchesCurrentFilters(task) {
  if (!task) return false;
  if (statusFilter.value && task.status !== statusFilter.value) return false;
  if (clientNameFilter.value && !(task.client_name || '').includes(clientNameFilter.value.trim())) return false;
  if (projectNameFilter.value && !(task.project_name || '').includes(projectNameFilter.value.trim())) return false;
  if (projectCodeFilter.value && !(task.project_code || '').includes(projectCodeFilter.value.trim())) return false;
  if (serviceTypeFilter.value && task.service_type !== serviceTypeFilter.value) return false;

  const q = searchText.value.trim().toLowerCase();
  if (!q) return true;

  const businessName = (task.task_name || '').toLowerCase();
  const filename = (task.filename || '').toLowerCase();
  const taskId = (task.task_id || '').toLowerCase();
  const clientName = (task.client_name || '').toLowerCase();
  const projectName = (task.project_name || '').toLowerCase();
  const projectCode = (task.project_code || '').toLowerCase();
  return (
    businessName.includes(q) ||
    filename.includes(q) ||
    clientName.includes(q) ||
    projectName.includes(q) ||
    projectCode.includes(q) ||
    taskId === q
  );
}

function syncTaskInList(task) {
  if (!task?.task_id) return;
  const idx = tasks.value.findIndex((t) => t.task_id === task.task_id);
  const matches = taskMatchesCurrentFilters(task);

  if (!matches) {
    if (idx !== -1) {
      tasks.value.splice(idx, 1);
      totalTasks.value = Math.max(totalTasks.value - 1, 0);
    }
    return;
  }

  if (idx !== -1) {
    tasks.value[idx] = { ...tasks.value[idx], ...task };
    return;
  }

  if (currentPage.value === 1) {
    tasks.value = [task, ...tasks.value].slice(0, pageSize);
    totalTasks.value += 1;
  }
}

async function refreshTaskAndList(taskId) {
  try {
    activeTask.value = await getTask(taskId);
    await Promise.all([loadTasks({ silent: true }), loadTaskStats()]);
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
  clientNameFilter.value = '';
  projectNameFilter.value = '';
  projectCodeFilter.value = '';
  serviceTypeFilter.value = '';
  applyFilters();
}

function contextParts(record) {
  const parts = [];
  if (record?.client_name) parts.push(`客户：${record.client_name}`);
  if (record?.project_name) parts.push(`项目：${record.project_name}`);
  if (record?.project_code) parts.push(`编号：${record.project_code}`);
  if (record?.service_type) parts.push(`服务：${record.service_type}`);
  return parts;
}

function contextText(record) {
  return contextParts(record).join(' · ');
}

const drawerSummary = computed(() => activeTask.value?.result?.summary || '');
const drawerRisks = computed(() => activeTask.value?.result?.risks || []);
const drawerCriticalRiskCount = computed(
  () => drawerRisks.value.filter((risk) => riskSeverity(risk) === 'CRITICAL').length,
);
const drawerHighRiskCount = computed(
  () => drawerRisks.value.filter((risk) => riskSeverity(risk) === 'HIGH').length,
);
const drawerMediumRiskCount = computed(
  () => drawerRisks.value.filter((risk) => riskSeverity(risk) === 'MEDIUM').length,
);
const drawerLowRiskCount = computed(
  () => drawerRisks.value.filter((risk) => riskSeverity(risk) === 'LOW').length,
);
const filteredDrawerRisks = computed(() => {
  if (riskFilter.value === 'ALL') return drawerRisks.value;
  return drawerRisks.value.filter((risk) => riskSeverity(risk) === riskFilter.value);
});
const drawerWaterfall = computed(() => activeTask.value?.waterfall || []);
const waterfallTotalMs = computed(() => {
  const segments = drawerWaterfall.value;
  if (!segments.length) return 0;
  return Math.max(...segments.map((item) => (item.start_ms || 0) + (item.duration_ms || 0)));
});
const waterfallTotalText = computed(() => formatDuration(waterfallTotalMs.value));
const drawerParsed = computed(() => {
  const text = activeTask.value?.parsed_text;
  return text ? text.slice(0, 2000) : '';
});

function formatDuration(ms) {
  const value = Number(ms || 0);
  if (value < 1000) return `${value}ms`;
  if (value < 60_000) return `${(value / 1000).toFixed(value < 10_000 ? 1 : 0)}s`;
  const minutes = Math.floor(value / 60_000);
  const seconds = Math.round((value % 60_000) / 1000);
  return `${minutes}m ${seconds}s`;
}

function waterfallWidth(segment) {
  if (!waterfallTotalMs.value) return '2%';
  const width = ((segment.duration_ms || 0) / waterfallTotalMs.value) * 100;
  return `${Math.max(width, 2)}%`;
}

function waterfallOffset(segment) {
  if (!waterfallTotalMs.value) return '0%';
  const offset = ((segment.start_ms || 0) / waterfallTotalMs.value) * 100;
  return `${Math.min(offset, 98)}%`;
}

function riskTitle(risk, index) {
  return risk.description || risk.violated_standard || `风险 ${index + 1}`;
}

function riskSeverity(risk) {
  const raw = String(risk.severity || risk.risk_level || 'MEDIUM').trim().toUpperCase();
  const aliases = {
    SERIOUS: 'CRITICAL',
    URGENT: 'CRITICAL',
    MAJOR: 'CRITICAL',
    重大: 'CRITICAL',
    严重: 'CRITICAL',
    紧急: 'CRITICAL',
    高: 'HIGH',
    中: 'MEDIUM',
    低: 'LOW',
  };
  return aliases[raw] || (['CRITICAL', 'HIGH', 'MEDIUM', 'LOW'].includes(raw) ? raw : 'MEDIUM');
}

function riskSeverityText(level) {
  return {
    CRITICAL: '重大',
    HIGH: '高',
    MEDIUM: '中',
    LOW: '低',
  }[level] || level;
}

async function copyRiskAdvice(risk) {
  const text = risk.recommendation || risk.rectification_advice || risk.evidence || riskTitle(risk, 0);
  try {
    await navigator.clipboard.writeText(text);
    toast.show('整改建议已复制', 'success');
  } catch {
    toast.show('复制失败，请手动选择文本', 'error');
  }
}

onMounted(refreshAll);

watch(
  hasActiveWork,
  (active) => {
    if (active) startPolling();
    else stopPolling();
  },
  { immediate: true },
);

watch(orgSelected, async (next, previous) => {
  const org = organizations.value.find((item) => item.id === next);
  session.setOrgName(org?.name || '');
  if (next === previous) return;
  currentPage.value = 1;
  await Promise.all([loadTasks({ silent: true }), loadTaskStats()]);
});

onBeforeUnmount(stopPolling);
onBeforeUnmount(closeProgressStream);
onBeforeUnmount(() => clearTimeout(searchTimer));
</script>

<template>
  <div class="view-container">
    <header class="view-header">
      <div>
        <h1>评价任务</h1>
        <p class="view-desc">管理和查看 EHS 合规评价任务</p>
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
        <h3>创建评价任务</h3>
        <p>上传 PDF、TXT、DOC、DOCX 或 CSV 格式的评价材料</p>
        <details class="upload-guide">
          <summary><span>上传须知</span><small>材料里建议包含的信息</small></summary>
          <div class="upload-guide-body">
            <h4>支持格式</h4>
            <ul>
              <li><strong>PDF / DOCX / DOC / TXT</strong> — 评价报告、检查记录、制度文件、现场说明</li>
              <li><strong>CSV</strong> — 风险清单、隐患台账、检查表等结构化数据</li>
            </ul>
            <h4>建议包含的信息</h4>
            <ul>
              <li><strong>企业和场所</strong>：公司名称、厂区/车间、岗位、评价范围</li>
              <li><strong>生产活动</strong>：主要工艺、设备设施、原辅材料、作业人数或班次</li>
              <li><strong>风险因素</strong>：职业病危害因素、危险源、环保排放点、消防/用电/特种设备信息</li>
              <li><strong>管理资料</strong>：制度、培训、应急预案、检查记录、整改闭环记录</li>
              <li><strong>检测和证据</strong>：检测报告、现场照片说明、问题描述、已有整改措施</li>
            </ul>
            <h4>导入边界</h4>
            <ul>
              <li>材料不必完全覆盖以上所有内容，但信息越完整，评价结果越稳定</li>
              <li>系统会保留解析文本预览，明显缺失或无法判断的内容会在结果中标记为需复核</li>
              <li>单文件最大 50MB；扫描件 PDF 如无文本层，识别效果取决于 OCR 能力</li>
            </ul>
          </div>
        </details>
        <form class="upload-form" @submit.prevent="submitUpload">
          <div class="form-row">
            <label class="form-field">
              <span class="label-text">所属公司</span>
              <select v-if="session.isAdmin" v-model="orgSelected">
                <option value="">默认公司</option>
                <option v-for="org in organizations" :key="org.id" :value="org.id">
                  {{ org.name || org.id }}
                </option>
              </select>
              <input v-else :value="selectedOrgName || session.orgName || '默认公司'" disabled />
            </label>
            <label class="form-field">
              <span class="label-text">任务名称</span>
              <input
                v-model="taskName"
                type="text"
                maxlength="255"
                :placeholder="taskNamePlaceholder"
              />
            </label>
            <label class="form-field">
              <span class="label-text">委托单位 / 客户公司</span>
              <input v-model="taskClientName" type="text" maxlength="255" placeholder="例如：某某制造有限公司" />
            </label>
            <label class="form-field">
              <span class="label-text">项目名称</span>
              <input v-model="taskProjectName" type="text" maxlength="255" placeholder="例如：年度职业卫生评价" />
            </label>
            <label class="form-field">
              <span class="label-text">项目编号</span>
              <input v-model="taskProjectCode" type="text" maxlength="64" placeholder="可选" />
            </label>
            <label class="form-field">
              <span class="label-text">服务类型</span>
              <select v-model="taskServiceType">
                <option value="">未指定</option>
                <option value="评价">评价</option>
                <option value="检测">检测</option>
                <option value="整改">整改</option>
                <option value="综合">综合</option>
              </select>
            </label>
            <label class="form-field file-field">
              <span class="label-text">评价文件</span>
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
              {{ uploadBusy ? '创建中...' : '开始评价' }}
            </button>
          </div>
        </form>
      </div>
    </section>

    <section class="task-list-section">
      <div class="task-stat-strip">
        <button type="button" class="task-stat-card" @click="statusFilter = ''; applyFilters()">
          <span>{{ taskStats.all }}</span>
          <small>全部任务</small>
        </button>
        <div class="task-stat-card active-work">
          <span>{{ taskStats.active }}</span>
          <small>处理中</small>
        </div>
        <button type="button" class="task-stat-card success" @click="statusFilter = 'SUCCESS'; applyFilters()">
          <span>{{ taskStats.success }}</span>
          <small>已完成</small>
        </button>
        <button type="button" class="task-stat-card warning" @click="statusFilter = 'NEEDS_REVIEW'; applyFilters()">
          <span>{{ taskStats.needsReview }}</span>
          <small>需复核</small>
        </button>
        <button type="button" class="task-stat-card failed" @click="statusFilter = 'FAILED'; applyFilters()">
          <span>{{ taskStats.failed }}</span>
          <small>失败</small>
        </button>
      </div>
      <div class="task-filters project-filters">
        <label class="filter-field">
          <span class="label-text">公司</span>
          <select v-if="session.isAdmin" v-model="orgSelected">
            <option value="">全部公司</option>
            <option v-for="org in organizations" :key="org.id" :value="org.id">
              {{ org.name || org.id }}
            </option>
          </select>
          <input v-else :value="selectedOrgName || session.orgName || '默认公司'" disabled />
        </label>
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
            <option value="NEEDS_REVIEW">需复核</option>
            <option value="FAILED">失败</option>
          </select>
        </label>
        <label class="filter-field filter-search">
          <span class="label-text">搜索</span>
          <input v-model="searchText" type="search" placeholder="任务、文件、客户、项目或任务 ID" @input="onSearchInput" />
        </label>
        <label class="filter-field">
          <span class="label-text">客户</span>
          <input v-model="clientNameFilter" type="search" placeholder="委托单位" @keydown.enter="applyFilters" />
        </label>
        <label class="filter-field">
          <span class="label-text">项目</span>
          <input v-model="projectNameFilter" type="search" placeholder="项目名称" @keydown.enter="applyFilters" />
        </label>
        <label class="filter-field">
          <span class="label-text">项目编号</span>
          <input v-model="projectCodeFilter" type="search" placeholder="编号" @keydown.enter="applyFilters" />
        </label>
        <label class="filter-field">
          <span class="label-text">服务类型</span>
          <select v-model="serviceTypeFilter" @change="applyFilters">
            <option value="">全部类型</option>
            <option value="评价">评价</option>
            <option value="检测">检测</option>
            <option value="整改">整改</option>
            <option value="综合">综合</option>
          </select>
        </label>
        <button type="button" class="btn-secondary filter-reset" @click="applyFilters">查询</button>
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
              <th>任务名称</th>
              <th>客户 / 项目</th>
              <th>状态</th>
              <th>进度</th>
              <th>风险数</th>
              <th>创建时间</th>
              <th>操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!tasks.length" class="empty-row">
              <td colspan="7">暂无评价任务</td>
            </tr>
            <tr
              v-for="task in tasks"
              :key="task.task_id"
              :data-task-id="task.task_id"
              :class="{ selected: task.task_id === session.selectedTaskId }"
              @click="selectTask(task.task_id)"
            >
              <td>
                <span class="task-filename">{{ task.task_name || task.filename || task.task_id }}</span>
                <small v-if="task.filename" class="subtle-line">来源文件：{{ task.filename }}</small>
              </td>
              <td>
                <span v-if="task.client_name || task.project_name" class="task-filename">
                  {{ task.client_name || '-' }}
                </span>
                <small v-if="contextText(task)" class="subtle-line">{{ contextText(task) }}</small>
                <span v-else>-</span>
              </td>
              <td>
                <span :class="['status-badge', task.status || '']">{{ statusText(task.status) }}</span>
              </td>
              <td>
                <div class="progress-bar">
                  <div class="progress-bar-fill" :style="{ width: `${task.progress ?? 0}%` }"></div>
                </div>
                <span class="progress-text">{{ statusStageText(task.status) }} · {{ task.progress ?? 0 }}%</span>
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
          <h2>{{ activeTask?.task_name || activeTask?.filename || activeTask?.task_id || '任务详情' }}</h2>
          <div class="drawer-actions">
            <button
              type="button"
              class="btn-secondary"
              :disabled="!hasPreviousTask"
              @click="selectAdjacentTask(-1)"
            >
              上一条
            </button>
            <button
              type="button"
              class="btn-secondary"
              :disabled="!hasNextTask"
              @click="selectAdjacentTask(1)"
            >
              下一条
            </button>
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
            <div class="drawer-summary-grid">
              <div class="drawer-summary-tile">
                <span>{{ activeRiskCount }}</span>
                <small>风险项</small>
              </div>
              <div class="drawer-summary-tile critical">
                <span>{{ drawerCriticalRiskCount }}</span>
                <small>重大风险</small>
              </div>
              <div class="drawer-summary-tile danger">
                <span>{{ drawerHighRiskCount }}</span>
                <small>高风险</small>
              </div>
              <div class="drawer-summary-tile warn">
                <span>{{ drawerMediumRiskCount }}</span>
                <small>中风险</small>
              </div>
            </div>
            <dl class="detail-meta">
              <dt>任务 ID</dt>
              <dd>{{ activeTask.task_id }}</dd>
              <dt>来源文件</dt>
              <dd>{{ activeTask.filename || '-' }}</dd>
              <dt>委托单位</dt>
              <dd>{{ activeTask.client_name || '-' }}</dd>
              <dt>项目名称</dt>
              <dd>{{ activeTask.project_name || '-' }}</dd>
              <dt>项目编号</dt>
              <dd>{{ activeTask.project_code || '-' }}</dd>
              <dt>服务类型</dt>
              <dd>{{ activeTask.service_type || '-' }}</dd>
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
            <div v-if="activeTaskNeedsReview" class="needs-review-alert">
              模型返回未结构化内容，当前结果需人工复核；风险列表不会进入正常成功统计。
            </div>
            <div v-if="drawerSummary" class="detail-section">
              <h3>评价摘要</h3>
              <p style="font-size: 14px; line-height: 1.7; color: var(--text-secondary)">
                {{ drawerSummary }}
              </p>
            </div>
            <div v-if="drawerWaterfall.length" class="detail-section">
              <div class="section-title-row">
                <h3>处理耗时</h3>
                <span class="duration-total">{{ waterfallTotalText }}</span>
              </div>
              <div class="waterfall-chart">
                <div
                  v-for="(segment, idx) in drawerWaterfall"
                  :key="`${segment.status}-${idx}`"
                  class="waterfall-row"
                >
                  <div class="waterfall-label">
                    <span>{{ segment.label }}</span>
                    <small>{{ statusText(segment.status) }}</small>
                  </div>
                  <div class="waterfall-track">
                    <div
                      :class="['waterfall-bar', segment.status]"
                      :style="{ left: waterfallOffset(segment), width: waterfallWidth(segment) }"
                    ></div>
                  </div>
                  <div class="waterfall-time">{{ formatDuration(segment.duration_ms) }}</div>
                </div>
              </div>
            </div>
            <div class="detail-section">
              <div class="section-title-row">
                <h3>风险项 ({{ drawerRisks.length }})</h3>
                <div v-if="drawerRisks.length" class="risk-filter">
                  <button type="button" :class="{ active: riskFilter === 'ALL' }" @click="riskFilter = 'ALL'">
                    全部
                  </button>
                  <button
                    type="button"
                    :class="{ active: riskFilter === 'CRITICAL' }"
                    @click="riskFilter = 'CRITICAL'"
                  >
                    重大 {{ drawerCriticalRiskCount }}
                  </button>
                  <button type="button" :class="{ active: riskFilter === 'HIGH' }" @click="riskFilter = 'HIGH'">
                    高 {{ drawerHighRiskCount }}
                  </button>
                  <button type="button" :class="{ active: riskFilter === 'MEDIUM' }" @click="riskFilter = 'MEDIUM'">
                    中 {{ drawerMediumRiskCount }}
                  </button>
                  <button type="button" :class="{ active: riskFilter === 'LOW' }" @click="riskFilter = 'LOW'">
                    低 {{ drawerLowRiskCount }}
                  </button>
                </div>
              </div>
              <p v-if="!drawerRisks.length" class="empty-state">暂无风险项</p>
              <div v-for="(risk, idx) in filteredDrawerRisks" :key="idx" class="risk-card">
                <div class="risk-card-header">
                  <span class="risk-card-title">{{ riskTitle(risk, idx) }}</span>
                  <span :class="['risk-severity', riskSeverity(risk)]">
                    {{ riskSeverityText(riskSeverity(risk)) }}
                  </span>
                </div>
                <div class="risk-card-body">
                  <p v-if="risk.recommendation || risk.rectification_advice">
                    <span class="risk-label">整改建议：</span
                    >{{ risk.recommendation || risk.rectification_advice }}
                  </p>
                  <p v-if="risk.evidence"><span class="risk-label">现场证据：</span>{{ risk.evidence }}</p>
                </div>
                <div class="risk-card-actions">
                  <button type="button" class="btn-row-action" @click="copyRiskAdvice(risk)">
                    复制建议
                  </button>
                </div>
              </div>
            </div>
            <div v-if="drawerParsed" class="detail-section">
              <details class="parsed-text-details">
                <summary>解析文本预览</summary>
                <div class="parsed-text-block">{{ drawerParsed }}</div>
              </details>
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
