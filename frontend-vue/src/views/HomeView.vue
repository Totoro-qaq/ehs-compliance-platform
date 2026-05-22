<script setup>
import { computed, onMounted, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { listTasks, getPublicStats } from '../api/assessment';
import { formatApiError } from '../api/client';
import { listDetectionReports } from '../api/detection';
import { useSessionStore } from '../stores/session';
import { formatTime, statusText } from '../utils/format';

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
const recentReports = ref([]);
const pendingReportItems = ref([]);
const failedReportItems = ref([]);
const workbenchBusy = ref(false);
const todoCategory = ref('all');
const todoPage = ref(1);

const TODO_PAGE_SIZE = 5;
const TODO_FETCH_PAGE_SIZE = 20;

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
  { title: '适合企业管理', desc: '支持公司归属、管理员视图、任务状态和检测报告管理。' },
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

const workbenchStats = computed(() => [
  { label: '已服务公司', value: publicCompaniesServed.value, tone: 'accent' },
  { label: '已完成任务', value: publicCompletedTasks.value, tone: 'success' },
  { label: '评价任务', value: assessmentTasks.value, tone: 'info' },
  { label: '检测任务', value: detectionTasks.value, tone: 'info' },
  { label: '失败任务', value: failedTasks.value, tone: 'danger' },
]);

const allTodoItems = computed(() => {
  const items = [
    ...failedTaskItems.value.map((task) => buildTodoItem({ kind: 'assessment', type: '失败', record: task, priority: 0 })),
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
  { key: 'failed', label: '失败异常', count: allTodoItems.value.filter((item) => item.priority === 0).length },
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
      reportsTotal,
      reportsDone,
      reportsFailed,
      reports,
      uploadedReports,
      parsedReports,
      validatedReports,
      failedReports,
    ] = results.map((_, index) => settledValue(results, index));
    const activePages = results.slice(11).map((item) => (item.status === 'fulfilled' ? item.value : null));

    const assessmentTotal = tasks?.total ?? numberOrZero(publicTotalTasks.value);
    const detectionTotal = reportsTotal?.total ?? 0;
    assessmentTasks.value = assessmentTotal;
    detectionTasks.value = detectionTotal;
    failedTasks.value = (failed?.total || 0) + (reportsFailed?.total || 0);
    recentTasks.value = tasks?.items || [];
    activeTaskItems.value = activePages.flatMap((page) => page?.items || []);
    failedTaskItems.value = failed?.items || [];
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
          <button v-if="session.isAdmin" type="button" class="quick-action" @click="nav('orgs')">
            <strong>公司管理</strong>
            <span>维护组织信息和归属关系</span>
          </button>
          <button v-else type="button" class="quick-action" @click="nav('settings')">
            <strong>账户设置</strong>
            <span>管理个人信息、密码和 API 连接</span>
          </button>
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
          <div class="hero-badge">企业级 EHS 合规管理平台</div>
          <h1 class="hero-title">把 EHS 合规检查从人工比对变成结构化管理</h1>
          <p class="hero-desc">
            面向企业安全、环保、职业卫生团队，自动解析资料、识别风险、匹配标准并生成可追溯的整改建议。
          </p>
          <div class="hero-actions">
            <button v-if="session.token" class="btn-primary btn-lg" @click="openWorkbench">进入工作台</button>
            <button v-else class="btn-primary btn-lg" @click="nav('tasks')">立即体验</button>
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
    </template>
  </div>
</template>
