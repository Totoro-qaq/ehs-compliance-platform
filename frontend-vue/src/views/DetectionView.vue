<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue';
import {
  calculateDetectionReport,
  createDetectionReport,
  createRegulatoryLimit,
  deleteRegulatoryLimit,
  getDetectionReport,
  listDetectionReports,
  listDetectionResults,
  listRegulatoryLimits,
  updateRegulatoryLimit,
} from '../api/detection';
import { formatApiError } from '../api/client';
import { listOrganizations } from '../api/organizations';
import Icon from '../components/Icon.vue';
import { useSessionStore } from '../stores/session';
import { useToastStore } from '../stores/toast';
import { formatTime } from '../utils/format';

const MAX_FILE_BYTES = 50 * 1024 * 1024;
const ALLOWED_EXTENSIONS = new Set(['csv', 'xlsx', 'xlsm']);

const REPORT_TYPES = [
  { value: 'OCCUPATIONAL_HEALTH', label: '职业卫生' },
  { value: 'WASTEWATER', label: '废水' },
  { value: 'EXHAUST_GAS', label: '废气' },
  { value: 'NOISE', label: '噪声' },
  { value: 'HIGH_TEMPERATURE', label: '高温 WBGT' },
];
const REPORT_STATUSES = [
  { value: 'UPLOADED', label: '已上传' },
  { value: 'PARSED', label: '已解析' },
  { value: 'VALIDATED', label: '已校验' },
  { value: 'CALCULATED', label: '已判定' },
  { value: 'FAILED', label: '失败' },
];
const MEDIUMS = [
  { value: 'WORKPLACE_AIR', label: '工作场所空气' },
  { value: 'WASTEWATER', label: '废水' },
  { value: 'EXHAUST_GAS', label: '废气' },
  { value: 'NOISE', label: '噪声' },
  { value: 'HIGH_TEMPERATURE', label: '高温 WBGT' },
];
const LIMIT_TYPES = ['MAC', 'PC_TWA', 'PC_STEL', 'DAILY_AVG', 'INSTANT', 'RANGE'];
const SAMPLE_FILES = [
  {
    key: 'occupational',
    label: '职业卫生样例',
    filename: 'occupational-health-sample.csv',
    reportType: 'OCCUPATIONAL_HEALTH',
    content:
      'sample_point,workplace,post_name,indicator_name,raw_value,raw_unit,duration_minutes\n' +
      '喷漆岗,涂装车间,喷漆工,测试因子甲,50000,μg/m3,60\n' +
      '喷漆岗,涂装车间,喷漆工,测试因子乙,20,mg/m3,60\n' +
      '打磨岗,机加工车间,打磨工,其他测试颗粒物,6,mg/m3,240\n',
  },
  {
    key: 'noise',
    label: '噪声样例',
    filename: 'noise-sample.csv',
    reportType: 'NOISE',
    content:
      'sample_point,workplace,post_name,medium,indicator_name,raw_value,raw_unit,shift_hours\n' +
      '空压机房,动力车间,巡检工,噪声,噪声,88,dB(A),8\n' +
      '包装线,成品车间,包装工,噪声,噪声,84,dB(A),8\n',
  },
  {
    key: 'heat',
    label: '高温样例',
    filename: 'high-temperature-sample.csv',
    reportType: 'HIGH_TEMPERATURE',
    content:
      'sample_point,workplace,post_name,medium,indicator_name,raw_value,raw_unit\n' +
      '炼钢平台,炼钢车间,炉前工,高温,测试热指数-A,31,WBGT(℃)\n' +
      '巡检通道,公辅车间,巡检工,高温,测试热指数-B,29,WBGT(℃)\n',
  },
];

const session = useSessionStore();
const toast = useToastStore();

const activeTab = ref('reports');
const organizations = ref([]);
const organizationId = ref('');

const reports = ref([]);
const reportPage = ref(1);
const reportPageSize = 15;
const reportTotal = ref(0);
const reportPages = ref(0);
const reportTypeFilter = ref('');
const reportStatusFilter = ref('');
const reportsBusy = ref(false);

const showUpload = ref(false);
const fileInput = ref(null);
const selectedFile = ref(null);
const fileLabel = ref('点击选择 CSV / XLSX / XLSM 文件');
const uploadBusy = ref(false);
const uploadReportType = ref('OCCUPATIONAL_HEALTH');

const drawerOpen = ref(false);
const activeReport = ref(null);
const activeResults = ref([]);
const calculateBusy = ref(false);

const limits = ref([]);
const limitPage = ref(1);
const limitPageSize = 15;
const limitTotal = ref(0);
const limitPages = ref(0);
const limitsBusy = ref(false);
const limitFilter = reactive({
  indicatorName: '',
  medium: '',
  standardCode: '',
});
const showLimitForm = ref(false);
const limitForm = reactive({
  id: '',
  indicator_name: '',
  cas_no: '',
  aliasesText: '',
  medium: 'WORKPLACE_AIR',
  limit_type: 'PC_TWA',
  limit_value: '',
  limit_min: '',
  limit_max: '',
  unit: 'mg/m3',
  standard_code: '',
  standard_name: '',
  clause: '',
  basis_text: '',
  priority: 100,
});

const reportCountText = computed(() => `${reportTotal.value} 份报告`);
const limitCountText = computed(() => `${limitTotal.value} 条限值`);
const selectedOrgName = computed(
  () => organizations.value.find((item) => item.id === organizationId.value)?.name || '',
);
const activeSampleCount = computed(() => activeReport.value?.samples?.length || 0);
const activeMeasurementCount = computed(() =>
  (activeReport.value?.samples || []).reduce((sum, sample) => sum + (sample.measurements?.length || 0), 0),
);
const resultSummary = computed(() => {
  const rows = activeResults.value || [];
  return {
    total: rows.length,
    exceeded: rows.filter((item) => item.status === 'EXCEEDED').length,
    borderline: rows.filter((item) => item.status === 'BORDERLINE').length,
    insufficient: rows.filter((item) => item.status === 'INSUFFICIENT_DATA').length,
    needsReview: rows.filter((item) => item.status === 'NEEDS_REVIEW').length,
  };
});
const limitFormTitle = computed(() => (limitForm.id ? '编辑限值' : '新增限值'));

function labelOf(options, value) {
  return options.find((item) => item.value === value)?.label || value || '-';
}

function statusText(status) {
  return REPORT_STATUSES.find((item) => item.value === status)?.label || status || '-';
}

function complianceText(status) {
  const map = {
    COMPLIANT: '合规',
    EXCEEDED: '超标',
    BORDERLINE: '临界',
    INSUFFICIENT_DATA: '数据不足',
    NEEDS_REVIEW: '需复核',
  };
  return map[status] || status || '-';
}

function formatNumber(value) {
  if (value === null || value === undefined || value === '') return '-';
  const num = Number(value);
  if (!Number.isFinite(num)) return String(value);
  return num.toLocaleString('zh-CN', { maximumFractionDigits: 6 });
}

function resetUpload() {
  if (fileInput.value) fileInput.value.value = '';
  selectedFile.value = null;
  fileLabel.value = '点击选择 CSV / XLSX / XLSM 文件';
}

function onFileChange(event) {
  const file = event.target.files?.[0];
  selectedFile.value = file || null;
  if (!file) {
    resetUpload();
    return;
  }
  const ext = file.name.split('.').pop()?.toLowerCase() || '';
  if (!ALLOWED_EXTENSIONS.has(ext)) {
    toast.show('仅支持 CSV、XLSX、XLSM 文件', 'error');
    resetUpload();
    return;
  }
  if (file.size > MAX_FILE_BYTES) {
    toast.show('文件大小不能超过 50MB', 'error');
    resetUpload();
    return;
  }
  fileLabel.value = file.name;
}

async function loadOrganizations() {
  try {
    const page = await listOrganizations(1, 200);
    organizations.value = page?.items || [];
    if (!organizationId.value && organizations.value.length) {
      organizationId.value = organizations.value[0].id;
      session.setOrgName(organizations.value[0].name || '');
    }
  } catch (err) {
    toast.show(formatApiError(err), 'error');
  }
}

async function loadReports({ silent = false } = {}) {
  reportsBusy.value = true;
  try {
    const page = await listDetectionReports(reportPage.value, reportPageSize, {
      organizationId: organizationId.value,
      reportType: reportTypeFilter.value,
      status: reportStatusFilter.value,
    });
    reports.value = page?.items || [];
    reportTotal.value = page?.total || 0;
    reportPages.value = page?.pages || 0;
  } catch (err) {
    if (!silent) toast.show(formatApiError(err), 'error');
  } finally {
    reportsBusy.value = false;
  }
}

async function refreshReports() {
  await loadReports();
  toast.show('报告列表已刷新', 'success');
}

async function submitUpload() {
  if (uploadBusy.value) return;
  const file = selectedFile.value || fileInput.value?.files?.[0];
  if (!file) {
    toast.show('请选择检测数据文件', 'error');
    return;
  }
  uploadBusy.value = true;
  try {
    const data = await createDetectionReport(file, {
      organizationId: organizationId.value,
      reportType: uploadReportType.value,
    });
    resetUpload();
    showUpload.value = false;
    reportStatusFilter.value = '';
    reportPage.value = 1;
    await loadReports();
    toast.show(`已导入 ${data.measurement_count || 0} 条检测结果`, 'success');
    await openReport(data.report_id);
  } catch (err) {
    toast.show(formatApiError(err), 'error');
  } finally {
    uploadBusy.value = false;
  }
}

async function openReport(reportId) {
  try {
    activeReport.value = await getDetectionReport(reportId);
    activeResults.value = await listDetectionResults(reportId);
    drawerOpen.value = true;
  } catch (err) {
    toast.show(formatApiError(err), 'error');
  }
}

function closeDrawer() {
  drawerOpen.value = false;
}

async function calculateActiveReport() {
  if (!activeReport.value || calculateBusy.value) return;
  calculateBusy.value = true;
  try {
    const run = await calculateDetectionReport(activeReport.value.id);
    activeResults.value = run?.results || [];
    activeReport.value = await getDetectionReport(activeReport.value.id);
    await loadReports({ silent: true });
    toast.show('合规判定已完成', 'success');
  } catch (err) {
    toast.show(formatApiError(err), 'error');
  } finally {
    calculateBusy.value = false;
  }
}

function applyReportFilters() {
  reportPage.value = 1;
  loadReports();
}

function goReportPage(page) {
  if (page < 1 || page > reportPages.value) return;
  reportPage.value = page;
  loadReports();
}

async function loadLimits({ silent = false } = {}) {
  if (!session.isAdmin) return;
  limitsBusy.value = true;
  try {
    const page = await listRegulatoryLimits(limitPage.value, limitPageSize, {
      indicatorName: limitFilter.indicatorName.trim(),
      medium: limitFilter.medium,
      standardCode: limitFilter.standardCode.trim(),
    });
    limits.value = page?.items || [];
    limitTotal.value = page?.total || 0;
    limitPages.value = page?.pages || 0;
  } catch (err) {
    if (!silent) toast.show(formatApiError(err), 'error');
  } finally {
    limitsBusy.value = false;
  }
}

function applyLimitFilters() {
  limitPage.value = 1;
  loadLimits();
}

function goLimitPage(page) {
  if (page < 1 || page > limitPages.value) return;
  limitPage.value = page;
  loadLimits();
}

function resetLimitForm() {
  Object.assign(limitForm, {
    id: '',
    indicator_name: '',
    cas_no: '',
    aliasesText: '',
    medium: 'WORKPLACE_AIR',
    limit_type: 'PC_TWA',
    limit_value: '',
    limit_min: '',
    limit_max: '',
    unit: 'mg/m3',
    standard_code: '',
    standard_name: '',
    clause: '',
    basis_text: '',
    priority: 100,
  });
}

function openCreateLimit() {
  resetLimitForm();
  showLimitForm.value = true;
}

function openEditLimit(limit) {
  Object.assign(limitForm, {
    id: limit.id,
    indicator_name: limit.indicator_name || '',
    cas_no: limit.cas_no || '',
    aliasesText: (limit.aliases || []).join(', '),
    medium: limit.medium || 'WORKPLACE_AIR',
    limit_type: limit.limit_type || 'PC_TWA',
    limit_value: limit.limit_value ?? '',
    limit_min: limit.limit_min ?? '',
    limit_max: limit.limit_max ?? '',
    unit: limit.unit || 'mg/m3',
    standard_code: limit.standard_code || '',
    standard_name: limit.standard_name || '',
    clause: limit.clause || '',
    basis_text: limit.basis_text || '',
    priority: limit.priority ?? 100,
  });
  showLimitForm.value = true;
}

function cleanNumber(value) {
  const text = String(value ?? '').trim();
  return text === '' ? null : text;
}

function buildLimitPayload() {
  return {
    indicator_name: limitForm.indicator_name.trim(),
    cas_no: limitForm.cas_no.trim() || null,
    aliases: limitForm.aliasesText
      .split(',')
      .map((item) => item.trim())
      .filter(Boolean),
    medium: limitForm.medium,
    limit_type: limitForm.limit_type,
    limit_value: cleanNumber(limitForm.limit_value),
    limit_min: cleanNumber(limitForm.limit_min),
    limit_max: cleanNumber(limitForm.limit_max),
    unit: limitForm.unit.trim(),
    standard_code: limitForm.standard_code.trim(),
    standard_name: limitForm.standard_name.trim(),
    clause: limitForm.clause.trim() || null,
    basis_text: limitForm.basis_text.trim() || null,
    applicability: {},
    priority: Number(limitForm.priority || 100),
  };
}

async function saveLimit() {
  try {
    const payload = buildLimitPayload();
    if (limitForm.id) {
      await updateRegulatoryLimit(limitForm.id, payload);
      toast.show('限值已更新', 'success');
    } else {
      await createRegulatoryLimit(payload);
      toast.show('限值已新增', 'success');
    }
    showLimitForm.value = false;
    await loadLimits({ silent: true });
  } catch (err) {
    toast.show(formatApiError(err), 'error');
  }
}

async function removeLimit(limit) {
  if (!confirm(`确认删除限值「${limit.indicator_name} / ${limit.limit_type}」？`)) return;
  try {
    await deleteRegulatoryLimit(limit.id);
    toast.show('限值已删除', 'success');
    if (limits.value.length === 1 && limitPage.value > 1) limitPage.value -= 1;
    await loadLimits({ silent: true });
  } catch (err) {
    toast.show(formatApiError(err), 'error');
  }
}

function useSampleCsv(sampleKey = 'occupational') {
  const sample = SAMPLE_FILES.find((item) => item.key === sampleKey) || SAMPLE_FILES[0];
  const blob = new Blob([sample.content], { type: 'text/csv;charset=utf-8' });
  const file = new File([blob], sample.filename, { type: 'text/csv' });
  selectedFile.value = file;
  fileLabel.value = file.name;
  uploadReportType.value = sample.reportType;
  showUpload.value = true;
}

onMounted(async () => {
  await loadOrganizations();
  await loadReports();
  if (session.isAdmin) await loadLimits({ silent: true });
});

watch(organizationId, async (next, previous) => {
  const org = organizations.value.find((item) => item.id === next);
  session.setOrgName(org?.name || '');
  if (next === previous) return;
  reportPage.value = 1;
  await loadReports({ silent: true });
});

watch(activeTab, (next) => {
  if (next === 'limits' && session.isAdmin) loadLimits({ silent: true });
});
</script>

<template>
  <div class="view-container detection-view">
    <header class="view-header">
      <div>
        <h1>检测合规</h1>
        <p class="view-desc">结构化检测数据导入、限值匹配和超标判定</p>
      </div>
      <div class="header-actions">
        <button type="button" class="btn-secondary" @click="useSampleCsv()">
          <Icon name="database" :size="14" />
          职业卫生样例
        </button>
        <button type="button" class="btn-secondary" @click="useSampleCsv('noise')">
          <Icon name="database" :size="14" />
          噪声样例
        </button>
        <button type="button" class="btn-secondary" @click="useSampleCsv('heat')">
          <Icon name="database" :size="14" />
          高温样例
        </button>
        <button type="button" class="btn-secondary" @click="refreshReports">
          <Icon name="refresh" :size="14" />
          刷新
        </button>
        <button type="button" class="btn-primary" @click="showUpload = !showUpload">
          <Icon name="upload" :size="14" />
          上传
        </button>
      </div>
    </header>

    <div class="tab-strip">
      <button
        type="button"
        :class="['tab-pill', { active: activeTab === 'reports' }]"
        @click="activeTab = 'reports'"
      >
        报告
      </button>
      <button
        type="button"
        :class="['tab-pill', { active: activeTab === 'limits' }]"
        :disabled="!session.isAdmin"
        @click="activeTab = 'limits'"
      >
        限值库
      </button>
    </div>

    <section v-if="showUpload" class="upload-panel">
      <div class="upload-panel-inner">
        <h3>导入检测数据</h3>
        <form class="upload-form" @submit.prevent="submitUpload">
          <div class="form-row">
            <label class="form-field">
              <span class="label-text">所属公司</span>
              <select v-model="organizationId">
                <option v-if="!organizations.length" value="">默认公司</option>
                <option v-for="org in organizations" :key="org.id" :value="org.id">{{ org.name }}</option>
              </select>
            </label>
            <label class="form-field">
              <span class="label-text">报告类型</span>
              <select v-model="uploadReportType">
                <option v-for="item in REPORT_TYPES" :key="item.value" :value="item.value">
                  {{ item.label }}
                </option>
              </select>
            </label>
            <label class="form-field file-field">
              <span class="label-text">数据文件</span>
              <div :class="['file-drop', { 'has-file': selectedFile }]">
                <input ref="fileInput" type="file" accept=".csv,.xlsx,.xlsm" @change="onFileChange" />
                <Icon name="upload" :size="24" :stroke="1.5" />
                <span class="file-drop-text">{{ fileLabel }}</span>
                <span class="file-drop-hint">支持 CSV, XLSX, XLSM；最大 50MB</span>
              </div>
            </label>
          </div>
          <div class="form-actions">
            <button type="button" class="btn-secondary" @click="showUpload = false">取消</button>
            <button type="submit" class="btn-primary" :disabled="uploadBusy || !selectedFile">
              {{ uploadBusy ? '导入中...' : '导入并解析' }}
            </button>
          </div>
        </form>
      </div>
    </section>

    <section v-if="activeTab === 'reports'" class="task-list-section">
      <div class="task-filters detection-filters">
        <label class="filter-field">
          <span class="label-text">公司</span>
          <select v-model="organizationId">
            <option value="">全部公司</option>
            <option v-for="org in organizations" :key="org.id" :value="org.id">{{ org.name }}</option>
          </select>
        </label>
        <label class="filter-field">
          <span class="label-text">类型</span>
          <select v-model="reportTypeFilter" @change="applyReportFilters">
            <option value="">全部类型</option>
            <option v-for="item in REPORT_TYPES" :key="item.value" :value="item.value">
              {{ item.label }}
            </option>
          </select>
        </label>
        <label class="filter-field">
          <span class="label-text">状态</span>
          <select v-model="reportStatusFilter" @change="applyReportFilters">
            <option value="">全部状态</option>
            <option v-for="item in REPORT_STATUSES" :key="item.value" :value="item.value">
              {{ item.label }}
            </option>
          </select>
        </label>
        <button type="button" class="btn-secondary filter-reset" @click="applyReportFilters">查询</button>
      </div>
      <div class="task-list-header">
        <span class="task-count"
          >{{ reportCountText }}<span v-if="selectedOrgName"> · {{ selectedOrgName }}</span></span
        >
        <div class="pagination">
          <template v-if="reportPages > 1">
            <button class="page-btn" :disabled="reportPage <= 1" @click="goReportPage(reportPage - 1)">
              &lt;
            </button>
            <span class="page-info">{{ reportPage }} / {{ reportPages }}</span>
            <button
              class="page-btn"
              :disabled="reportPage >= reportPages"
              @click="goReportPage(reportPage + 1)"
            >
              &gt;
            </button>
          </template>
        </div>
      </div>
      <div class="task-table-wrap">
        <table class="task-table">
          <thead>
            <tr>
              <th>文件</th>
              <th>类型</th>
              <th>状态</th>
              <th>报告日期</th>
              <th>创建时间</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!reports.length" class="empty-row">
              <td colspan="5">{{ reportsBusy ? '加载中...' : '暂无检测报告' }}</td>
            </tr>
            <tr v-for="report in reports" :key="report.id" @click="openReport(report.id)">
              <td>
                <span class="task-filename">{{ report.filename }}</span>
              </td>
              <td>{{ labelOf(REPORT_TYPES, report.report_type) }}</td>
              <td>
                <span :class="['status-badge', report.status]">{{ statusText(report.status) }}</span>
              </td>
              <td>{{ report.report_date || '-' }}</td>
              <td>{{ formatTime(report.created_at) }}</td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <section v-if="activeTab === 'limits'" class="task-list-section">
      <div v-if="!session.isAdmin" class="empty-state">仅管理员可维护限值库</div>
      <template v-else>
        <div class="task-filters detection-filters">
          <label class="filter-field">
            <span class="label-text">因子</span>
            <input
              v-model="limitFilter.indicatorName"
              placeholder="测试因子甲 / pH / 噪声 / 高温WBGT"
              @keydown.enter="applyLimitFilters"
            />
          </label>
          <label class="filter-field">
            <span class="label-text">介质</span>
            <select v-model="limitFilter.medium" @change="applyLimitFilters">
              <option value="">全部介质</option>
              <option v-for="item in MEDIUMS" :key="item.value" :value="item.value">{{ item.label }}</option>
            </select>
          </label>
          <label class="filter-field">
            <span class="label-text">标准编号</span>
            <input
              v-model="limitFilter.standardCode"
              placeholder="TEST-STD 2.1-2019"
              @keydown.enter="applyLimitFilters"
            />
          </label>
          <button type="button" class="btn-secondary filter-reset" @click="applyLimitFilters">查询</button>
        </div>
        <div class="task-list-header">
          <span class="task-count">{{ limitCountText }}</span>
          <div class="header-actions">
            <button type="button" class="btn-primary" @click="openCreateLimit">
              <Icon name="plus" :size="14" />
              新增限值
            </button>
          </div>
        </div>
        <section v-if="showLimitForm" class="limit-form-panel">
          <h3>{{ limitFormTitle }}</h3>
          <form class="limit-form-grid" @submit.prevent="saveLimit">
            <label class="form-field">
              <span class="label-text">因子</span>
              <input v-model="limitForm.indicator_name" required maxlength="128" />
            </label>
            <label class="form-field">
              <span class="label-text">CAS</span>
              <input v-model="limitForm.cas_no" maxlength="32" />
            </label>
            <label class="form-field">
              <span class="label-text">别名</span>
              <input v-model="limitForm.aliasesText" placeholder="英文名, 常用名" />
            </label>
            <label class="form-field">
              <span class="label-text">介质</span>
              <select v-model="limitForm.medium">
                <option v-for="item in MEDIUMS" :key="item.value" :value="item.value">
                  {{ item.label }}
                </option>
              </select>
            </label>
            <label class="form-field">
              <span class="label-text">限值类型</span>
              <select v-model="limitForm.limit_type">
                <option v-for="item in LIMIT_TYPES" :key="item" :value="item">{{ item }}</option>
              </select>
            </label>
            <label class="form-field">
              <span class="label-text">限值</span>
              <input v-model="limitForm.limit_value" placeholder="标量限值" />
            </label>
            <label class="form-field">
              <span class="label-text">下限</span>
              <input v-model="limitForm.limit_min" placeholder="范围限值" />
            </label>
            <label class="form-field">
              <span class="label-text">上限</span>
              <input v-model="limitForm.limit_max" placeholder="范围限值" />
            </label>
            <label class="form-field">
              <span class="label-text">单位</span>
              <input v-model="limitForm.unit" required />
            </label>
            <label class="form-field">
              <span class="label-text">标准编号</span>
              <input v-model="limitForm.standard_code" required />
            </label>
            <label class="form-field">
              <span class="label-text">标准名称</span>
              <input v-model="limitForm.standard_name" required />
            </label>
            <label class="form-field">
              <span class="label-text">条款</span>
              <input v-model="limitForm.clause" />
            </label>
            <label class="form-field">
              <span class="label-text">优先级</span>
              <input v-model="limitForm.priority" type="number" min="0" max="10000" />
            </label>
            <label class="form-field limit-basis">
              <span class="label-text">依据说明</span>
              <input v-model="limitForm.basis_text" />
            </label>
            <div class="form-actions limit-actions">
              <button type="button" class="btn-secondary" @click="showLimitForm = false">取消</button>
              <button type="submit" class="btn-primary">
                <Icon name="save" :size="14" />
                保存
              </button>
            </div>
          </form>
        </section>
        <div class="task-table-wrap">
          <table class="task-table">
            <thead>
              <tr>
                <th>因子</th>
                <th>介质</th>
                <th>类型</th>
                <th>限值</th>
                <th>标准</th>
                <th style="width: 120px; text-align: right">操作</th>
              </tr>
            </thead>
            <tbody>
              <tr v-if="!limits.length" class="empty-row">
                <td colspan="6">{{ limitsBusy ? '加载中...' : '暂无限值' }}</td>
              </tr>
              <tr v-for="limit in limits" :key="limit.id">
                <td>
                  <span class="task-filename">{{ limit.indicator_name }}</span>
                  <small v-if="limit.cas_no" class="subtle-line">{{ limit.cas_no }}</small>
                </td>
                <td>{{ labelOf(MEDIUMS, limit.medium) }}</td>
                <td>{{ limit.limit_type }}</td>
                <td>
                  <template v-if="limit.limit_type === 'RANGE'">
                    {{ formatNumber(limit.limit_min) }} - {{ formatNumber(limit.limit_max) }} {{ limit.unit }}
                  </template>
                  <template v-else>{{ formatNumber(limit.limit_value) }} {{ limit.unit }}</template>
                </td>
                <td>
                  <span>{{ limit.standard_code }}</span>
                  <small class="subtle-line">{{ limit.clause || '-' }}</small>
                </td>
                <td style="text-align: right">
                  <button class="btn-icon-sm" title="编辑" @click="openEditLimit(limit)">
                    <Icon name="edit" :size="14" />
                  </button>
                  <button
                    class="btn-icon-sm"
                    title="删除"
                    style="color: var(--danger)"
                    @click="removeLimit(limit)"
                  >
                    <Icon name="trash" :size="14" />
                  </button>
                </td>
              </tr>
            </tbody>
          </table>
        </div>
        <div class="task-list-header">
          <span class="task-count"></span>
          <div class="pagination">
            <template v-if="limitPages > 1">
              <button class="page-btn" :disabled="limitPage <= 1" @click="goLimitPage(limitPage - 1)">
                &lt;
              </button>
              <span class="page-info">{{ limitPage }} / {{ limitPages }}</span>
              <button
                class="page-btn"
                :disabled="limitPage >= limitPages"
                @click="goLimitPage(limitPage + 1)"
              >
                &gt;
              </button>
            </template>
          </div>
        </div>
      </template>
    </section>

    <Transition name="drawer">
      <aside v-if="drawerOpen" class="task-drawer detection-drawer open">
        <div class="drawer-header">
          <h2>{{ activeReport?.filename || '报告详情' }}</h2>
          <div class="drawer-actions">
            <button
              type="button"
              class="btn-primary"
              :disabled="calculateBusy"
              @click="calculateActiveReport"
            >
              <Icon name="play" :size="14" />
              {{ calculateBusy ? '判定中' : '运行判定' }}
            </button>
            <button type="button" class="btn-icon-sm" @click="closeDrawer">
              <Icon name="close" />
            </button>
          </div>
        </div>
        <div class="drawer-body">
          <template v-if="activeReport">
            <dl class="detail-meta">
              <dt>报告 ID</dt>
              <dd>{{ activeReport.id }}</dd>
              <dt>类型</dt>
              <dd>{{ labelOf(REPORT_TYPES, activeReport.report_type) }}</dd>
              <dt>状态</dt>
              <dd>
                <span :class="['status-badge', activeReport.status]">{{
                  statusText(activeReport.status)
                }}</span>
              </dd>
              <dt>样品</dt>
              <dd>{{ activeSampleCount }}</dd>
              <dt>检测项</dt>
              <dd>{{ activeMeasurementCount }}</dd>
            </dl>

            <div class="metric-grid">
              <div class="metric-tile">
                <span>{{ resultSummary.total }}</span>
                <small>结果</small>
              </div>
              <div class="metric-tile danger">
                <span>{{ resultSummary.exceeded }}</span>
                <small>超标</small>
              </div>
              <div class="metric-tile warn">
                <span>{{ resultSummary.borderline }}</span>
                <small>临界</small>
              </div>
              <div class="metric-tile info">
                <span>{{ resultSummary.insufficient + resultSummary.needsReview }}</span>
                <small>待复核</small>
              </div>
            </div>

            <div class="detail-section">
              <h3>判定结果</h3>
              <p v-if="!activeResults.length" class="empty-state compact">尚未运行合规判定</p>
              <div v-else class="result-list">
                <div v-for="result in activeResults" :key="result.id" class="result-row">
                  <div>
                    <span :class="['compliance-badge', result.status]">{{
                      complianceText(result.status)
                    }}</span>
                    <strong>{{ result.standard_code || '未匹配限值' }}</strong>
                    <small>{{ result.message }}</small>
                  </div>
                  <div class="result-values">
                    <span
                      >{{ formatNumber(result.calculated_value) }} {{ result.calculated_unit || '' }}</span
                    >
                    <span>限值 {{ formatNumber(result.limit_value) }} {{ result.limit_unit || '' }}</span>
                  </div>
                </div>
              </div>
            </div>

            <div class="detail-section">
              <h3>结构化数据</h3>
              <div v-for="sample in activeReport.samples" :key="sample.id" class="sample-block">
                <div class="sample-title">
                  <strong>{{ sample.sample_point }}</strong>
                  <span>{{ labelOf(MEDIUMS, sample.medium) }}</span>
                </div>
                <table class="mini-table">
                  <thead>
                    <tr>
                      <th>因子</th>
                      <th>原始值</th>
                      <th>归一值</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="measurement in sample.measurements" :key="measurement.id">
                      <td>{{ measurement.indicator_name }}</td>
                      <td>{{ formatNumber(measurement.raw_value) }} {{ measurement.raw_unit || '' }}</td>
                      <td>
                        {{ formatNumber(measurement.normalized_value) }}
                        {{ measurement.normalized_unit || '' }}
                      </td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>
          </template>
        </div>
      </aside>
    </Transition>
  </div>
</template>

<style scoped>
.tab-strip {
  display: inline-flex;
  gap: 4px;
  padding: 4px;
  margin-bottom: 18px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--panel);
}
.tab-pill {
  min-width: 92px;
  min-height: 34px;
  padding: 7px 14px;
  border: 0;
  border-radius: 6px;
  background: transparent;
  color: var(--text-secondary);
  font-weight: 600;
  transition: all var(--transition);
}
.tab-pill.active {
  background: var(--accent);
  color: #fff;
}
.tab-pill:disabled {
  opacity: 0.4;
  cursor: not-allowed;
}
.detection-filters {
  grid-template-columns: minmax(180px, 1.2fr) 160px 150px auto;
}
.limit-form-panel {
  padding: 18px 20px 8px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-subtle);
}
.limit-form-panel h3 {
  margin-bottom: 14px;
  font-size: 15px;
}
.limit-form-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(130px, 1fr));
  gap: 12px;
}
.limit-basis {
  grid-column: span 3;
}
.limit-actions {
  align-self: end;
}
.subtle-line {
  display: block;
  margin-top: 2px;
  color: var(--text-tertiary);
  font-size: 12px;
}
.metric-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 10px;
  margin-bottom: 22px;
}
.metric-tile {
  min-height: 74px;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--panel);
}
.metric-tile span {
  display: block;
  color: var(--text);
  font-size: 24px;
  font-weight: 700;
  line-height: 1;
}
.metric-tile small {
  display: block;
  margin-top: 8px;
  color: var(--text-secondary);
  font-size: 12px;
}
.metric-tile.danger span {
  color: var(--danger);
}
.metric-tile.warn span {
  color: var(--warning);
}
.metric-tile.info span {
  color: var(--info);
}
.result-list {
  display: grid;
  gap: 10px;
}
.result-row {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 170px;
  gap: 12px;
  align-items: start;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--bg-subtle);
}
.result-row strong {
  display: block;
  margin-top: 6px;
  font-size: 13px;
}
.result-row small {
  display: block;
  margin-top: 3px;
  color: var(--text-secondary);
  line-height: 1.4;
}
.result-values {
  display: grid;
  gap: 5px;
  color: var(--text-secondary);
  font-size: 12px;
  text-align: right;
}
.compliance-badge {
  display: inline-flex;
  padding: 2px 8px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
}
.compliance-badge.COMPLIANT {
  background: var(--success-bg);
  color: var(--success);
}
.compliance-badge.EXCEEDED {
  background: var(--danger-bg);
  color: var(--danger);
}
.compliance-badge.BORDERLINE {
  background: var(--warning-bg);
  color: var(--warning);
}
.compliance-badge.INSUFFICIENT_DATA,
.compliance-badge.NEEDS_REVIEW {
  background: var(--info-bg);
  color: var(--info);
}
.sample-block {
  margin-bottom: 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  overflow: hidden;
}
.sample-title {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  border-bottom: 1px solid var(--border);
  background: var(--bg-subtle);
}
.sample-title span {
  color: var(--text-secondary);
  font-size: 12px;
}
.mini-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.mini-table th,
.mini-table td {
  padding: 8px 10px;
  border-bottom: 1px solid var(--border-subtle);
  text-align: left;
}
.mini-table th {
  color: var(--text-tertiary);
  font-weight: 700;
}
.empty-state.compact {
  padding: 22px 12px;
}

@media (max-width: 1024px) {
  .detection-filters,
  .limit-form-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .limit-basis {
    grid-column: span 2;
  }
}

@media (max-width: 768px) {
  .detection-filters,
  .limit-form-grid,
  .metric-grid,
  .result-row {
    grid-template-columns: 1fr;
  }
  .limit-basis {
    grid-column: span 1;
  }
  .result-values {
    text-align: left;
  }
}
</style>
