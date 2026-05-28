<script setup>
import { computed, onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { chatWithAgent } from '../api/agent';
import { listTasks, getPublicStats } from '../api/assessment';
import { formatApiError } from '../api/client';
import { listDetectionReports } from '../api/detection';
import { useSessionStore } from '../stores/session';
import { formatTime, statusText } from '../utils/format';
import Icon from '../components/Icon.vue';

const router = useRouter();
const route = useRoute();
const session = useSessionStore();

const publicTotalTasks = ref('-');
const publicCompaniesServed = ref('-');
const publicCompletedTasks = ref('-');
const publicStatsBusy = ref(false);
const publicStatsError = ref('');

const assessmentTasks = ref('-');
const detectionTasks = ref('-');
const failedTasks = ref('-');
const recentTasks = ref([]);
const activeTaskItems = ref([]);
const failedTaskItems = ref([]);
const needsReviewTaskItems = ref([]);
const recentReports = ref([]);
const pendingReportItems = ref([]);
const failedReportItems = ref([]);
const workbenchBusy = ref(false);
const todoCategory = ref('all');
const todoPage = ref(1);
const agentSessionId = ref('');
const agentInput = ref('');
const agentAnswer = ref('');
const agentError = ref('');
const agentBusy = ref(false);
const agentDegraded = ref(false);
const agentResponseMode = ref('model');
const supportOpen = ref(false);
const supportInput = ref('');
const supportMessages = ref([
  {
    role: 'assistant',
    content: '留下一个问题或选择上方服务路径，我们会按试点验证、部署评估、方案演示三个方向给你建议。',
    handoff: false,
  },
]);

const TODO_PAGE_SIZE = 5;
const TODO_FETCH_PAGE_SIZE = 20;
const SUPPORT_EMAIL = 'msy626836554@gmail.com';

const showWorkbench = computed(() => Boolean(session.token) && route.query.view === 'workbench');
const statsBusy = computed(() => publicStatsBusy.value || workbenchBusy.value);

const heroStats = computed(() => [
  { label: '已服务公司', value: publicCompaniesServed.value },
  { label: '已完成任务', value: publicCompletedTasks.value },
  { label: '累计任务', value: publicTotalTasks.value },
]);

const scenarioCards = [
  {
    title: '安全生产检查',
    desc: '把检查记录、现场照片和整改要求统一归档，自动识别隐患和责任闭环。',
    tag: '隐患排查',
  },
  {
    title: '职业卫生检测',
    desc: '导入检测报告后自动匹配限值，快速定位超标岗位、因子和采样点。',
    tag: '限值判定',
  },
  {
    title: '环保合规排查',
    desc: '沉淀检查证据、标准条款和整改建议，降低重复人工比对成本。',
    tag: '条款对标',
  },
  {
    title: '内审与外审整改',
    desc: '把风险项、依据、建议和处理状态结构化，方便管理层追踪进度。',
    tag: '整改闭环',
  },
];

const capabilityCards = [
  {
    title: '材料自动解析',
    desc: '支持常见文档和检测数据导入，提取关键字段、报告信息和现场描述。',
    tone: 'info',
  },
  {
    title: 'AI 风险识别',
    desc: '从检查文本中识别风险点、违规表现和证据线索，减少人工初筛时间。',
    tone: 'danger',
  },
  {
    title: '法规标准匹配',
    desc: '把风险项关联到标准条款和限值要求，让判断依据更容易复核。',
    tone: 'accent',
  },
  {
    title: '报告归档追溯',
    desc: '任务、检测报告、组织归属和处理状态统一管理，方便审计和复盘。',
    tone: 'success',
  },
];

const proofCards = [
  { title: '更快形成结论', desc: '把资料解析、风险识别、条款匹配合并到一条工作流。' },
  { title: '结果可复核', desc: '输出风险等级、依据条款、整改建议和原始证据来源。' },
  { title: '适合企业与检测机构', desc: '支持企业内部管理，也支持第三方检测机构按委托单位和项目归档资料。' },
];

const workflowSteps = [
  { title: '导入资料', desc: '上传检查记录、检测报告或现场材料。' },
  { title: '自动分析', desc: '系统解析内容并识别风险、超标项和依据。' },
  { title: '复核结果', desc: '查看风险等级、条款匹配和整改建议。' },
  { title: '归档跟踪', desc: '沉淀任务记录，持续跟踪整改和合规状态。' },
];

const intelligenceCards = [
  { title: '私有化部署', value: '内网可用', desc: '模型、知识库和业务数据可放在企业可控环境。' },
  { title: '权限隔离', value: '按组织', desc: '围绕公司、角色和用户范围控制可见数据。' },
  { title: '审计留痕', value: '全链路', desc: '任务、报告、分析过程和后续 Agent 调用可追溯。' },
  { title: '知识增强', value: '可扩展', desc: '法规、限值、历史报告和整改模板可持续沉淀。' },
];

const agentQuickPrompts = [
  '总结当前工作台',
  '有哪些待处理事项',
  '最近失败的任务是什么',
  '检测报告还有哪些没判定',
];

const supportQuickPrompts = ['获取试点方案', '上传样例评估', '私有化部署', '项目顾问'];
const consultationCards = [
  { title: '解决方案咨询', desc: '按企业或第三方检测机构场景梳理模块组合和上线路径。', prompt: '预约演示' },
  { title: '数据样例评估', desc: '用脱敏报告验证解析、限值判定、风险摘要和权限隔离。', prompt: '上传样例评估' },
  { title: '私有化部署对接', desc: '确认服务器、模型服务、内网访问、系统对接和审计要求。', prompt: '私有化部署' },
];
const consultationStats = [
  { value: '3 类', label: '试点场景' },
  { value: '只读', label: '数据评估' },
  { value: '私有化', label: '部署路径' },
];
const consultationSteps = ['需求沟通', '样例验证', '部署方案'];

const workbenchStats = computed(() => [
  { label: '已服务公司', value: publicCompaniesServed.value, tone: 'accent' },
  { label: '已完成任务', value: publicCompletedTasks.value, tone: 'success' },
  { label: '评价任务', value: assessmentTasks.value, tone: 'info' },
  { label: '检测任务', value: detectionTasks.value, tone: 'info' },
  { label: '异常/复核任务', value: failedTasks.value, tone: 'danger' },
]);

const allTodoItems = computed(() => {
  const items = [
    ...failedTaskItems.value.map((task) => buildTodoItem({ kind: 'assessment', type: '失败', record: task, priority: 0 })),
    ...needsReviewTaskItems.value.map((task) => buildTodoItem({ kind: 'assessment', type: '需复核', record: task, priority: 0 })),
    ...failedReportItems.value.map((report) => buildTodoItem({ kind: 'detection', type: '失败', record: report, priority: 0 })),
    ...activeTaskItems.value.map((task) => buildTodoItem({ kind: 'assessment', type: '处理中', record: task, priority: 1 })),
    ...pendingReportItems.value.map((report) => buildTodoItem({ kind: 'detection', type: '待判定', record: report, priority: 1 })),
  ];
  const uniqueItems = new Map();
  for (const item of items) uniqueItems.set(item.key, item);
  return Array.from(uniqueItems.values()).sort((a, b) => {
    if (a.priority !== b.priority) return a.priority - b.priority;
    return b.timestamp - a.timestamp;
  });
});

const todoCategories = computed(() => [
  { key: 'all', label: '全部', count: allTodoItems.value.length },
  { key: 'assessment', label: '评价任务', count: allTodoItems.value.filter((item) => item.kind === 'assessment').length },
  { key: 'detection', label: '检测合规', count: allTodoItems.value.filter((item) => item.kind === 'detection').length },
  { key: 'failed', label: '异常/复核', count: allTodoItems.value.filter((item) => item.priority === 0).length },
]);

const filteredTodoItems = computed(() => {
  if (todoCategory.value === 'all') return allTodoItems.value;
  if (todoCategory.value === 'failed') return allTodoItems.value.filter((item) => item.priority === 0);
  return allTodoItems.value.filter((item) => item.kind === todoCategory.value);
});

const todoTotalPages = computed(() => Math.max(1, Math.ceil(filteredTodoItems.value.length / TODO_PAGE_SIZE)));

const pagedTodoItems = computed(() => {
  const start = (todoPage.value - 1) * TODO_PAGE_SIZE;
  return filteredTodoItems.value.slice(start, start + TODO_PAGE_SIZE);
});

const ACTIVE_TASK_STATUSES = ['PENDING', 'PARSING', 'AI_ANALYZING', 'VALIDATING', 'PERSISTING'];
const REPORT_STATUS_TEXT = {
  UPLOADED: '已上传',
  PARSED: '已解析',
  VALIDATED: '已校验',
  CALCULATED: '已判定',
  FAILED: '失败',
};

function buildTodoItem({ kind, type, record, priority }) {
  const timeValue = record?.updated_at || record?.created_at;
  const fallbackId = kind === 'assessment' ? record?.task_id : record?.id;
  return {
    key: `${kind}-${fallbackId}`,
    kind,
    type,
    module: kind === 'assessment' ? '评价' : '检测',
    route: kind === 'assessment' ? 'tasks' : 'detection',
    title: record?.task_name || record?.report_name || record?.filename || fallbackId || '-',
    context: contextText(record),
    status: record?.status || '',
    statusLabel: kind === 'assessment' ? statusText(record?.status) : reportStatusText(record?.status),
    timeValue,
    timestamp: timeValue ? new Date(timeValue).getTime() || 0 : 0,
    priority,
  };
}

function reportStatusText(status) {
  return REPORT_STATUS_TEXT[status] || status || '-';
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

function numberOrZero(value) {
  const next = Number(value);
  return Number.isFinite(next) ? next : 0;
}

function applyPublicStats(stats) {
  const assessmentTotal = numberOrZero(stats?.assessment_tasks);
  const detectionTotal = numberOrZero(stats?.detection_tasks);
  publicTotalTasks.value = numberOrZero(stats?.total_tasks ?? assessmentTotal + detectionTotal);
  publicCompaniesServed.value = numberOrZero(stats?.companies_served);
  publicCompletedTasks.value = numberOrZero(stats?.completed_tasks);

  if (!showWorkbench.value || assessmentTasks.value === '-') assessmentTasks.value = assessmentTotal;
  if (!showWorkbench.value || detectionTasks.value === '-') detectionTasks.value = detectionTotal;
}

function resetWorkbenchData() {
  failedTasks.value = '-';
  recentTasks.value = [];
  activeTaskItems.value = [];
  failedTaskItems.value = [];
  needsReviewTaskItems.value = [];
  recentReports.value = [];
  pendingReportItems.value = [];
  failedReportItems.value = [];
}

async function loadPublicStats() {
  publicStatsBusy.value = true;
  publicStatsError.value = '';
  try {
    applyPublicStats(await getPublicStats());
  } catch (err) {
    publicStatsError.value = formatApiError(err);
    publicTotalTasks.value = 0;
    publicCompaniesServed.value = 0;
    publicCompletedTasks.value = 0;
  } finally {
    publicStatsBusy.value = false;
  }
}

function settledValue(results, index) {
  return results[index]?.status === 'fulfilled' ? results[index].value : null;
}

async function loadWorkbenchData() {
  if (!session.token) {
    resetWorkbenchData();
    return;
  }

  workbenchBusy.value = true;
  try {
    const requests = [
      listTasks(1, 5),
      listTasks(1, 1, { status: 'SUCCESS' }),
      listTasks(1, TODO_FETCH_PAGE_SIZE, { status: 'FAILED' }),
      listTasks(1, TODO_FETCH_PAGE_SIZE, { status: 'NEEDS_REVIEW' }),
      listDetectionReports(1, 1),
      listDetectionReports(1, 1, { status: 'CALCULATED' }),
      listDetectionReports(1, 1, { status: 'FAILED' }),
      listDetectionReports(1, 5),
      listDetectionReports(1, TODO_FETCH_PAGE_SIZE, { status: 'UPLOADED' }),
      listDetectionReports(1, TODO_FETCH_PAGE_SIZE, { status: 'PARSED' }),
      listDetectionReports(1, TODO_FETCH_PAGE_SIZE, { status: 'VALIDATED' }),
      listDetectionReports(1, TODO_FETCH_PAGE_SIZE, { status: 'FAILED' }),
      ...ACTIVE_TASK_STATUSES.map((status) => listTasks(1, TODO_FETCH_PAGE_SIZE, { status })),
    ];
    const results = await Promise.allSettled(requests);
    const [
      tasks,
      success,
      failed,
      needsReview,
      reportsTotal,
      reportsDone,
      reportsFailed,
      reports,
      uploadedReports,
      parsedReports,
      validatedReports,
      failedReports,
    ] = results.map((_, index) => settledValue(results, index));
    const activePages = results.slice(12).map((item) => (item.status === 'fulfilled' ? item.value : null));

    const assessmentTotal = tasks?.total ?? numberOrZero(publicTotalTasks.value);
    const detectionTotal = reportsTotal?.total ?? 0;
    assessmentTasks.value = assessmentTotal;
    detectionTasks.value = detectionTotal;
    failedTasks.value = (failed?.total || 0) + (needsReview?.total || 0) + (reportsFailed?.total || 0);
    recentTasks.value = tasks?.items || [];
    activeTaskItems.value = activePages.flatMap((page) => page?.items || []);
    failedTaskItems.value = failed?.items || [];
    needsReviewTaskItems.value = needsReview?.items || [];
    recentReports.value = reports?.items || [];
    pendingReportItems.value = [
      ...(uploadedReports?.items || []),
      ...(parsedReports?.items || []),
      ...(validatedReports?.items || []),
    ];
    failedReportItems.value = failedReports?.items || [];

    if (results.some((item) => item.status === 'rejected')) {
      const firstError = results.find((item) => item.status === 'rejected')?.reason;
      console.warn('Workbench data loaded partially:', firstError);
    }
  } finally {
    workbenchBusy.value = false;
  }
}

function nav(view) {
  router.push({ name: view });
}

function setTodoCategory(category) {
  todoCategory.value = category;
  todoPage.value = 1;
}

function changeTodoPage(delta) {
  todoPage.value = Math.min(todoTotalPages.value, Math.max(1, todoPage.value + delta));
}

function openTodoTarget() {
  if (todoCategory.value === 'detection') {
    nav('detection');
    return;
  }
  nav('tasks');
}

function openAgent() {
  nav('agent');
}

async function askAgent(question = agentInput.value) {
  const content = (question || '').trim();
  if (!content || agentBusy.value) return;

  agentBusy.value = true;
  agentError.value = '';
  try {
    const data = await chatWithAgent({
      content,
      sessionId: agentSessionId.value,
    });
    agentSessionId.value = data?.session?.id || agentSessionId.value;
    agentAnswer.value = data?.assistant_message?.content || 'Agent 暂无返回内容。';
    agentDegraded.value = Boolean(data?.degraded);
    agentResponseMode.value =
      data?.run?.provider === 'rules' || data?.run?.model_name === 'fast-summary' ? 'rules' : 'model';
    agentInput.value = '';
  } catch (err) {
    agentError.value = formatApiError(err);
  } finally {
    agentBusy.value = false;
  }
}

function useAgentPrompt(prompt) {
  agentInput.value = prompt;
  askAgent(prompt);
}

function supportReply(content) {
  const text = content.toLowerCase();
  if (['人工', '顾问', '联系', '电话', '邮箱', '报价', '价格', '演示', '预约', '项目顾问'].some((key) => text.includes(key))) {
    return {
      content: `建议进入顾问对接。你可以发邮件到 ${SUPPORT_EMAIL}，说明公司名称、行业场景、现有资料类型和预计部署方式，我们按试点验证和部署方案跟进。`,
      handoff: true,
    };
  }
  if (['样例', '评估', '试点', '试用', '体验', '开始', '登录', '注册', '上传'].some((key) => text.includes(key))) {
    return {
      content: '建议先用脱敏样例做试点验证：评价材料看风险识别和依据输出，检测报告看解析、限值匹配和判定结果，再评估是否进入私有化部署。',
      handoff: false,
    };
  }
  if (['方案', '需求', '匹配', '场景', '能做什么', '功能', '适用', '职业卫生', '环保', '安全'].some((key) => text.includes(key))) {
    return {
      content: '适合按场景匹配方案：企业可做安全、环保、职业卫生内部合规管理；第三方检测机构可按委托单位和项目归档资料、解析报告、复核判定。核心交付是资料解析、风险识别、条款匹配、检测限值判定和整改闭环。',
      handoff: false,
    };
  }
  if (['部署', '私有化', '内网', '本地', '数据', '权限', '对接', '系统'].some((key) => text.includes(key))) {
    return {
      content: '私有化部署需要确认服务器资源、模型服务、内网访问、账号组织隔离、审计留痕和现有系统对接方式。建议先做一轮脱敏样例评估再定部署方案。',
      handoff: false,
    };
  }
  if (['agent', '助手', '总结', '工作台', '失败任务', '检测报告'].some((key) => text.includes(key))) {
    return {
      content: '商务咨询入口只负责产品介绍和试用路径。登录后可以打开工作台里的“AI 合规助手”，它会按账号权限读取工作台、评价任务、检测报告和限值库摘要。',
      handoff: false,
    };
  }
  return {
    content: '这个问题需要结合具体业务场景确认，建议预约项目顾问，避免给你不可靠的信息。',
    handoff: true,
  };
}

function askSupport(question = supportInput.value) {
  const content = (question || '').trim();
  if (!content) return;
  supportOpen.value = true;
  supportMessages.value.push({ role: 'user', content, handoff: false });
  supportMessages.value.push({ role: 'assistant', ...supportReply(content) });
  supportInput.value = '';
}

function contactHuman() {
  window.location.href = `mailto:${SUPPORT_EMAIL}?subject=${encodeURIComponent('EHS 系统咨询')}`;
}

function scrollToFeatures() {
  document.querySelector('.features')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function scrollToReportPreview() {
  document.querySelector('.report-showcase')?.scrollIntoView({ behavior: 'smooth', block: 'start' });
}

function openWorkbench() {
  if (!session.token) {
    router.push({ name: 'login', query: { redirect: '/home?view=workbench' } });
    return;
  }
  router.push({ name: 'home', query: { view: 'workbench' } });
}

function enforceHomeAccess() {
  if (!session.token && route.query.view === 'workbench') {
    router.replace({ name: 'home' });
  }
}

onMounted(async () => {
  enforceHomeAccess();
  await loadPublicStats();
  if (showWorkbench.value) await loadWorkbenchData();
});

watch(
  () => [session.token, route.query.view],
  async () => {
    enforceHomeAccess();
    if (showWorkbench.value) {
      await loadPublicStats();
      await loadWorkbenchData();
    } else if (!session.token) {
      resetWorkbenchData();
    }
  },
);

watch(todoTotalPages, (pages) => {
  if (todoPage.value > pages) todoPage.value = pages;
});
</script>

<template>
  <div class="view-container home-view">
    <section v-if="showWorkbench" class="workbench">
      <div class="workbench-header">
        <div>
          <span class="workbench-kicker">工作台</span>
          <h1>你好，{{ session.username || '用户' }}</h1>
          <p>这里汇总当前评价任务、检测报告和待处理事项。</p>
        </div>
        <div class="workbench-actions">
          <button class="btn-primary" @click="nav('tasks')">进入评价任务</button>
          <button class="btn-secondary" @click="nav('detection')">导入检测报告</button>
        </div>
      </div>

      <div class="workbench-stat-grid">
        <div v-for="item in workbenchStats" :key="item.label" :class="['workbench-stat', item.tone]">
          <span>{{ item.value }}</span>
          <small>{{ item.label }}</small>
        </div>
      </div>

      <section class="workbench-panel quick-actions-panel">
        <div class="workbench-panel-head">
          <h2>快捷入口</h2>
        </div>
        <div class="quick-action-grid">
          <button type="button" class="quick-action" @click="nav('tasks')">
            <strong>评价任务</strong>
            <span>查看任务列表，上传材料并启动 AI 分析</span>
          </button>
          <button type="button" class="quick-action" @click="nav('detection')">
            <strong>检测合规</strong>
            <span>导入检测数据，运行限值判定</span>
          </button>
          <button
            type="button"
            class="quick-action"
            @click="router.push({ name: 'detection', query: { tab: 'limits' } })"
          >
            <strong>限值库</strong>
            <span>查询职业卫生和物理因素限值</span>
          </button>
        </div>
      </section>

      <section class="workbench-panel agent-panel">
        <div class="agent-panel-main">
          <div class="agent-panel-copy">
            <span class="workbench-kicker">AI 合规助手</span>
            <h2>先读业务数据，再给处理建议</h2>
            <p>当前阶段为只读 Agent，会按账号权限读取工作台、评价任务、检测报告和限值库摘要。</p>
            <button type="button" class="btn-secondary btn-sm agent-open-btn" @click="openAgent">打开完整会话</button>
          </div>
          <div class="agent-prompt-stack">
            <div class="agent-quick-prompts">
              <button
                v-for="prompt in agentQuickPrompts"
                :key="prompt"
                type="button"
                :disabled="agentBusy"
                @click="useAgentPrompt(prompt)"
              >
                {{ prompt }}
              </button>
            </div>
            <form class="agent-input-row" @submit.prevent="askAgent()">
              <textarea
                v-model="agentInput"
                placeholder="问问当前工作台、失败任务、检测判定或限值库..."
                :disabled="agentBusy"
                rows="3"
                @keydown.enter.exact.prevent="askAgent()"
              ></textarea>
              <button type="submit" class="btn-primary" :disabled="agentBusy || !agentInput.trim()">
                {{ agentBusy ? '分析中' : '发送' }}
              </button>
            </form>
          </div>
        </div>
        <div v-if="agentBusy" class="agent-response muted">Agent 正在读取业务数据...</div>
        <div v-else-if="agentError" class="agent-response error">{{ agentError }}</div>
        <div v-else-if="agentAnswer" class="agent-response">
          <div class="agent-response-head">
            <strong>分析结果</strong>
            <span v-if="agentDegraded || agentResponseMode === 'rules'">规则摘要</span>
            <span v-else>模型生成</span>
          </div>
          <p>{{ agentAnswer }}</p>
        </div>
      </section>

      <div class="workbench-dashboard">
        <section class="workbench-panel todo-panel">
          <div class="workbench-panel-head">
            <h2>待处理事项</h2>
            <button type="button" class="btn-secondary" @click="openTodoTarget">处理事项</button>
          </div>
          <div v-if="statsBusy" class="empty-state compact">加载中...</div>
          <div v-else-if="!allTodoItems.length" class="empty-state compact">暂无待处理事项</div>
          <template v-else>
            <div class="todo-tabs" aria-label="待处理事项分类">
              <button
                v-for="category in todoCategories"
                :key="category.key"
                type="button"
                :class="['todo-tab', { active: todoCategory === category.key }]"
                @click="setTodoCategory(category.key)"
              >
                <span>{{ category.label }}</span>
                <small>{{ category.count }}</small>
              </button>
            </div>
            <div v-if="!filteredTodoItems.length" class="empty-state compact">当前分类暂无事项</div>
            <div v-else class="recent-list">
              <button
                v-for="item in pagedTodoItems"
                :key="item.key"
                type="button"
                :class="['recent-item', 'todo-item', { urgent: item.priority === 0 }]"
                @click="nav(item.route)"
              >
                <span>
                  <strong>{{ item.title }}</strong>
                  <small v-if="item.context">{{ item.context }}</small>
                  <small>
                    <span class="todo-module">{{ item.module }}</span>
                    {{ item.type }} · {{ formatTime(item.timeValue) }}
                  </small>
                </span>
                <span :class="['status-badge', item.status]">{{ item.statusLabel }}</span>
              </button>
            </div>
            <div v-if="filteredTodoItems.length > TODO_PAGE_SIZE" class="todo-pagination">
              <span>第 {{ todoPage }} / {{ todoTotalPages }} 页，共 {{ filteredTodoItems.length }} 条</span>
              <div class="todo-pagination-actions">
                <button type="button" class="todo-page-btn" :disabled="todoPage <= 1" @click="changeTodoPage(-1)">
                  上一页
                </button>
                <button
                  type="button"
                  class="todo-page-btn"
                  :disabled="todoPage >= todoTotalPages"
                  @click="changeTodoPage(1)"
                >
                  下一页
                </button>
              </div>
            </div>
          </template>
        </section>

        <aside class="workbench-side-stack">
          <section class="workbench-panel">
          <div class="workbench-panel-head">
            <h2>最近评价任务</h2>
            <button type="button" class="btn-secondary" @click="nav('tasks')">查看全部</button>
          </div>
          <div v-if="statsBusy" class="empty-state compact">加载中...</div>
          <div v-else-if="!recentTasks.length" class="empty-state compact">暂无评价任务</div>
          <div v-else class="recent-list">
            <button
              v-for="task in recentTasks"
              :key="task.task_id"
              type="button"
              class="recent-item"
              @click="nav('tasks')"
            >
              <span>
                <strong>{{ task.task_name || task.filename || task.task_id }}</strong>
                <small v-if="contextText(task)">{{ contextText(task) }}</small>
                <small>{{ formatTime(task.created_at) }}</small>
              </span>
              <span :class="['status-badge', task.status || '']">{{ statusText(task.status) }}</span>
            </button>
          </div>
          </section>

          <section class="workbench-panel">
          <div class="workbench-panel-head">
            <h2>最近检测报告</h2>
            <button type="button" class="btn-secondary" @click="nav('detection')">查看全部</button>
          </div>
          <div v-if="statsBusy" class="empty-state compact">加载中...</div>
          <div v-else-if="!recentReports.length" class="empty-state compact">暂无检测报告</div>
          <div v-else class="recent-list">
            <button
              v-for="report in recentReports"
              :key="report.id"
              type="button"
              class="recent-item"
              @click="nav('detection')"
            >
              <span>
                <strong>{{ report.report_name || report.filename || report.id }}</strong>
                <small v-if="contextText(report)">{{ contextText(report) }}</small>
                <small>{{ formatTime(report.created_at) }}</small>
              </span>
              <span :class="['status-badge', report.status || '']">{{ reportStatusText(report.status) }}</span>
            </button>
          </div>
          </section>
        </aside>
      </div>
    </section>

    <template v-else>
      <section class="hero commercial-hero">
        <div class="hero-product-preview" aria-hidden="true">
          <div class="preview-topbar">
            <span></span>
            <span></span>
            <span></span>
            <strong>EHS 合规分析报告</strong>
          </div>
          <div class="preview-score-grid">
            <div>
              <strong>18</strong>
              <span>识别风险</span>
            </div>
            <div>
              <strong>6</strong>
              <span>高优先级</span>
            </div>
            <div>
              <strong>12</strong>
              <span>匹配条款</span>
            </div>
          </div>
          <div class="preview-report-list">
            <div class="preview-report-row danger">
              <span>HIGH</span>
              <p>有限空间作业审批记录缺失，需补充风险辨识与监护要求。</p>
            </div>
            <div class="preview-report-row warning">
              <span>MEDIUM</span>
              <p>职业卫生检测报告存在噪声超标岗位，建议复核防护措施。</p>
            </div>
            <div class="preview-report-row success">
              <span>LOW</span>
              <p>安全培训台账已归档，建议持续维护年度复训记录。</p>
            </div>
          </div>
        </div>

        <div class="hero-content commercial-hero-content">
          <div class="hero-badge">企业和第三方检测机构的 EHS 合规分析平台</div>
          <h1 class="hero-title">把 EHS 检查、检测和评价资料变成结构化管理</h1>
          <p class="hero-desc">
            面向企业安全环保职业卫生团队，以及第三方检测机构，自动解析资料、识别风险、匹配标准并沉淀客户/项目上下文。
          </p>
          <div class="hero-actions">
            <button v-if="session.token" class="btn-primary btn-lg hero-cta-shine" @click="openWorkbench">进入工作台</button>
            <button v-else class="btn-primary btn-lg hero-cta-shine" @click="nav('tasks')">立即体验</button>
            <button class="btn-secondary btn-lg" @click="scrollToReportPreview">查看示例报告</button>
          </div>
          <div class="hero-trust-list">
            <span>风险识别</span>
            <span>条款对标</span>
            <span>限值判定</span>
            <span>整改闭环</span>
          </div>
          <div class="hero-stats">
            <div v-for="item in heroStats" :key="item.label" class="stat-item">
              <span class="stat-number">{{ publicStatsBusy ? '-' : item.value }}</span>
              <span class="stat-label">{{ item.label }}</span>
            </div>
          </div>
          <p v-if="publicStatsError" class="hero-stats-error">累计数据暂未连上后端，请检查 API 地址或后端服务。</p>
        </div>
      </section>

      <section class="commercial-section intelligence-section">
        <div class="intelligence-shell">
          <div class="intelligence-copy">
            <span class="section-kicker">合规智能中枢</span>
            <h2>为后续 Agent 和知识库预留企业级底座</h2>
            <p>
              首页不只展示功能，也需要让客户看到系统具备长期扩展能力：从资料解析、向量检索、风险判断到整改闭环，形成可治理的智能流程。
            </p>
          </div>
          <div class="intelligence-flow" aria-label="合规智能流程">
            <div class="flow-node active">
              <strong>01</strong>
              <span>资料解析</span>
            </div>
            <div class="flow-node">
              <strong>02</strong>
              <span>知识检索</span>
            </div>
            <div class="flow-node">
              <strong>03</strong>
              <span>风险判断</span>
            </div>
            <div class="flow-node">
              <strong>04</strong>
              <span>整改闭环</span>
            </div>
          </div>
          <div class="intelligence-grid">
            <article v-for="item in intelligenceCards" :key="item.title" class="intelligence-card">
              <strong>{{ item.value }}</strong>
              <h3>{{ item.title }}</h3>
              <p>{{ item.desc }}</p>
            </article>
          </div>
        </div>
      </section>

      <section class="commercial-section scenarios-section">
        <div class="section-heading">
          <span>适用场景</span>
          <h2>覆盖企业 EHS 管理的高频工作</h2>
          <p>把分散的检查资料、检测报告和整改事项沉淀到统一流程里。</p>
        </div>
        <div class="scenario-grid">
          <article v-for="item in scenarioCards" :key="item.title" class="scenario-card">
            <small>{{ item.tag }}</small>
            <h3>{{ item.title }}</h3>
            <p>{{ item.desc }}</p>
          </article>
        </div>
      </section>

      <section class="commercial-section report-showcase">
        <div class="report-copy">
          <span class="section-kicker">示例产出</span>
          <h2>客户真正采购的是可复核的合规结论</h2>
          <p>
            系统把风险等级、标准依据、整改建议和检测超标项放在同一份结构化结果里，便于安全负责人复核，也便于管理层追踪整改。
          </p>
          <div class="report-benefits">
            <span>违规依据可追溯</span>
            <span>整改建议可执行</span>
            <span>任务状态可跟踪</span>
          </div>
        </div>
        <div class="report-preview-shell">
          <div class="report-preview-header">
            <div>
              <strong>企业合规分析摘要</strong>
              <span>自动生成 · 可归档 · 可复核</span>
            </div>
            <button type="button" class="btn-secondary btn-sm" @click="nav('tasks')">进入体验</button>
          </div>
          <div class="report-metrics">
            <div><strong>82%</strong><span>完成率</span></div>
            <div><strong>6</strong><span>高风险</span></div>
            <div><strong>4</strong><span>超标项</span></div>
          </div>
          <div class="report-table">
            <div class="report-table-row head">
              <span>事项</span>
              <span>等级</span>
              <span>处理建议</span>
            </div>
            <div class="report-table-row">
              <span>噪声岗位检测值超限</span>
              <span class="pill danger">高</span>
              <span>复核防护配置并安排复测</span>
            </div>
            <div class="report-table-row">
              <span>危废暂存标识不完整</span>
              <span class="pill warning">中</span>
              <span>补充标识与台账记录</span>
            </div>
            <div class="report-table-row">
              <span>培训签到记录缺页</span>
              <span class="pill info">低</span>
              <span>归档补充材料</span>
            </div>
          </div>
        </div>
      </section>

      <section class="commercial-section proof-section">
        <div class="section-heading compact">
          <span>为什么选择</span>
          <h2>让合规工作从“查资料”变成“管结果”</h2>
        </div>
        <div class="proof-grid">
          <article v-for="item in proofCards" :key="item.title" class="proof-card">
            <h3>{{ item.title }}</h3>
            <p>{{ item.desc }}</p>
          </article>
        </div>
      </section>

      <section class="features commercial-section">
        <div class="section-heading">
          <span>核心能力</span>
          <h2>围绕合规结果设计，而不是只做文件上传</h2>
          <p>降低人工比对成本，同时保留业务人员需要的复核链路。</p>
        </div>
        <div class="features-grid">
          <article v-for="item in capabilityCards" :key="item.title" :class="['feature-card', item.tone]">
            <div class="feature-icon"></div>
            <h3>{{ item.title }}</h3>
            <p>{{ item.desc }}</p>
          </article>
        </div>
      </section>

      <section class="workflow commercial-section">
        <div class="section-heading">
          <span>使用流程</span>
          <h2>从资料导入到整改追踪，形成闭环</h2>
        </div>
        <div class="workflow-steps">
          <article v-for="(item, index) in workflowSteps" :key="item.title" class="workflow-step">
            <div class="step-number">{{ index + 1 }}</div>
            <h4>{{ item.title }}</h4>
            <p>{{ item.desc }}</p>
          </article>
        </div>
      </section>

      <aside v-if="!showWorkbench" class="support-assistant" aria-label="商务咨询">
        <div v-if="supportOpen" class="support-panel">
          <div class="support-head">
            <div>
              <span>方案咨询</span>
              <strong>匹配 EHS 数字化试点路径</strong>
            </div>
            <button type="button" class="support-close" aria-label="关闭商务咨询" @click="supportOpen = false">
              <Icon name="close" :size="16" />
            </button>
          </div>
          <div class="consultation-metrics">
            <div v-for="item in consultationStats" :key="item.label">
              <strong>{{ item.value }}</strong>
              <span>{{ item.label }}</span>
            </div>
          </div>
          <div class="consultation-card-grid">
            <button
              v-for="item in consultationCards"
              :key="item.title"
              type="button"
              class="consultation-card"
              @click="askSupport(item.prompt)"
            >
              <strong>{{ item.title }}</strong>
              <span>{{ item.desc }}</span>
            </button>
          </div>
          <div class="consultation-steps" aria-label="咨询流程">
            <span v-for="(step, index) in consultationSteps" :key="step">
              {{ index + 1 }}. {{ step }}
            </span>
          </div>
          <div class="support-messages">
            <div
              v-for="(message, index) in supportMessages"
              :key="index"
              :class="['support-message', message.role]"
            >
              <p>{{ message.content }}</p>
              <button v-if="message.handoff" type="button" class="support-handoff" @click="contactHuman">
                预约顾问
              </button>
            </div>
          </div>
          <div class="support-prompts">
            <button
              v-for="prompt in supportQuickPrompts"
              :key="prompt"
              type="button"
              @click="askSupport(prompt)"
            >
              {{ prompt }}
            </button>
          </div>
          <form class="support-input" @submit.prevent="askSupport()">
            <input v-model="supportInput" placeholder="问产品、试用、部署或预约演示..." />
            <button type="submit" :disabled="!supportInput.trim()">匹配</button>
          </form>
        </div>
        <button
          type="button"
          class="support-fab"
          :aria-expanded="supportOpen"
          aria-label="打开或关闭方案咨询"
          title="方案咨询"
          @click="supportOpen = !supportOpen"
        >
          <span class="support-fab-icon">
            <Icon name="message" :size="19" />
          </span>
          <span class="support-fab-copy">
            <strong>方案咨询</strong>
            <small>试点评估 / 预约演示</small>
          </span>
        </button>
      </aside>
    </template>
  </div>
</template>
