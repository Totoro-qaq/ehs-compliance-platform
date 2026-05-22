<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue';
import {
  calculateDetectionReport,
  createDetectionReport,
  getDetectionReport,
  importDetectionDocumentPreview,
  listDetectionReports,
  listDetectionResults,
  listRegulatoryLimits,
  previewDetectionDocument,
} from '../api/detection';
import { formatApiError } from '../api/client';
import { listOrganizations } from '../api/organizations';
import Icon from '../components/Icon.vue';
import { useSessionStore } from '../stores/session';
import { useToastStore } from '../stores/toast';
import { formatTime } from '../utils/format';

const MAX_FILE_BYTES = 50 * 1024 * 1024;
const ALLOWED_EXTENSIONS = new Set(['csv', 'xlsx', 'xlsm']);
const DOCUMENT_EXTENSIONS = new Set(['pdf', 'docx', 'doc', 'txt', 'zip']);

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
    filename: '职业卫生检测样例.csv',
    reportType: 'OCCUPATIONAL_HEALTH',
    // 职业病危害因素含化学因素和物理因素，列名均支持中英文，非必填列可留空
    content:
      '检测点,车间,岗位,检测因子,检测值,单位,介质,采样时长(分钟),班次时长\n' +
      /* 化学因素 */ '喷漆岗,涂装车间,喷漆工,苯,50000,μg/m3,工作场所空气,60,\n' +
      '喷漆岗,涂装车间,喷漆工,甲苯,20,mg/m3,工作场所空气,60,\n' +
      '打磨岗,机加工车间,打磨工,其他粉尘,6,mg/m3,工作场所空气,240,\n' +
      /* 物理因素 */ '空压机房,动力车间,巡检工,噪声,88,dB(A),噪声,,8\n' +
      '包装线,成品车间,包装工,噪声,84,dB(A),噪声,,8\n' +
      '炼钢平台,炼钢车间,炉前工,高温WBGT-I级-100%,31,WBGT(℃),高温,,\n' +
      '巡检通道,公辅车间,巡检工,高温WBGT-II级-50%,29,WBGT(℃),高温,,\n',
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

const showDocumentPreview = ref(false);
const documentInput = ref(null);
const selectedDocument = ref(null);
const documentLabel = ref('点击选择 PDF / DOCX / DOC / TXT / ZIP 文件');
const documentReportType = ref('OCCUPATIONAL_HEALTH');
const documentPreviewBusy = ref(false);
const documentImportBusy = ref(false);
const documentPreview = ref(null);

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

// ---- 人工确认：行选择 + 行内编辑 ----
const selectedRowIndices = ref(new Set());
const rowEdits = ref({});

function _ensureRowEdit(rowIndex) {
  if (!rowEdits.value[rowIndex]) {
    rowEdits.value[rowIndex] = {};
  }
}

function getEditValue(row, field) {
  const edits = rowEdits.value[row.row_index];
  if (edits && field in edits) return edits[field];
  return row[field];
}

function setEditValue(row, field, value) {
  _ensureRowEdit(row.row_index);
  rowEdits.value[row.row_index][field] = value;
}

function isRowModified(row) {
  const edits = rowEdits.value[row.row_index];
  return !!edits && Object.keys(edits).length > 0;
}

function isRowSelected(row) {
  return selectedRowIndices.value.has(row.row_index);
}

function toggleRow(rowIndex) {
  const next = new Set(selectedRowIndices.value);
  if (next.has(rowIndex)) {
    next.delete(rowIndex);
  } else {
    next.add(rowIndex);
  }
  selectedRowIndices.value = next;
}

const allPreviewRowsSelected = computed(() => {
  const rows = documentPreview.value?.rows || [];
  return rows.length > 0 && rows.every((r) => selectedRowIndices.value.has(r.row_index));
});

function toggleAllRows() {
  const rows = documentPreview.value?.rows || [];
  if (allPreviewRowsSelected.value) {
    selectedRowIndices.value = new Set();
  } else {
    selectedRowIndices.value = new Set(rows.map((r) => r.row_index));
  }
}

function deselectLowConfidence(threshold = 0.7) {
  const rows = documentPreview.value?.rows || [];
  const next = new Set(selectedRowIndices.value);
  for (const r of rows) {
    if (Number(r.confidence || 0) < threshold) next.delete(r.row_index);
  }
  selectedRowIndices.value = next;
}

const selectedImportCount = computed(() => {
  const rows = documentPreview.value?.rows || [];
  return rows.filter((r) => {
    if (!selectedRowIndices.value.has(r.row_index)) return false;
    const bg = rowEdits.value[r.row_index]?.is_background;
    const isBg = bg !== undefined ? bg : r.is_background;
    const raw = rowEdits.value[r.row_index]?.raw_value;
    const val = raw !== undefined ? raw : r.raw_value;
    return !isBg && val !== null && val !== '';
  }).length;
});

function buildImportRows() {
  const rows = documentPreview.value?.rows || [];
  return rows
    .filter((r) => selectedRowIndices.value.has(r.row_index))
    .filter((r) => {
      const bg = rowEdits.value[r.row_index]?.is_background;
      const isBg = bg !== undefined ? bg : r.is_background;
      const raw = rowEdits.value[r.row_index]?.raw_value;
      const val = raw !== undefined ? raw : r.raw_value;
      return !isBg && val !== null && val !== '';
    })
    .map((r) => {
      const base = { ...r };
      const edits = rowEdits.value[r.row_index] || {};
      for (const [key, val] of Object.entries(edits)) {
        base[key] = val;
      }
      return base;
    });
}

function confidenceClass(row) {
  const c = Number(row.confidence || 0);
  if (c >= 0.85) return 'conf-high';
  if (c >= 0.7) return 'conf-medium';
  return 'conf-low';
}

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

function formatPreviewLimit(row) {
  if (!row?.report_limit_value) return '';
  return `${formatNumber(row.report_limit_value)} ${row.report_limit_unit || ''}`.trim();
}

function resetUpload() {
  if (fileInput.value) fileInput.value.value = '';
  selectedFile.value = null;
  fileLabel.value = '点击选择 CSV / XLSX / XLSM 文件';
}

function resetDocumentPreview() {
  if (documentInput.value) documentInput.value.value = '';
  selectedDocument.value = null;
  documentLabel.value = '点击选择 PDF / DOCX / DOC / TXT 文件';
  documentPreview.value = null;
  selectedRowIndices.value = new Set();
  rowEdits.value = {};
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

function onDocumentChange(event) {
  const file = event.target.files?.[0];
  selectedDocument.value = file || null;
  documentPreview.value = null;
  if (!file) {
    resetDocumentPreview();
    return;
  }
  const ext = file.name.split('.').pop()?.toLowerCase() || '';
  if (!DOCUMENT_EXTENSIONS.has(ext)) {
    toast.show('仅支持 PDF、DOCX、DOC、TXT 文件', 'error');
    resetDocumentPreview();
    return;
  }
  if (file.size > MAX_FILE_BYTES) {
    toast.show('文件大小不能超过 50MB', 'error');
    resetDocumentPreview();
    return;
  }
  documentLabel.value = file.name;
}

async function submitDocumentPreview() {
  if (documentPreviewBusy.value) return;
  const file = selectedDocument.value || documentInput.value?.files?.[0];
  if (!file) {
    toast.show('请选择需要解析预览的报告文件', 'error');
    return;
  }
  documentPreviewBusy.value = true;
  try {
    documentPreview.value = await previewDetectionDocument(file, {
      reportType: documentReportType.value,
    });
    // 默认全选所有候选行
    const rows = documentPreview.value?.rows || [];
    selectedRowIndices.value = new Set(rows.map((r) => r.row_index));
    rowEdits.value = {};
    toast.show(`识别到 ${rows.length} 条候选检测行`, 'success');
  } catch (err) {
    toast.show(formatApiError(err), 'error');
  } finally {
    documentPreviewBusy.value = false;
  }
}

async function importDocumentPreview() {
  if (documentImportBusy.value || !documentPreview.value) return;
  const importRows = buildImportRows();
  if (!importRows.length) {
    toast.show('没有可入库的候选检测行（请勾选至少一条非背景含数值行）', 'error');
    return;
  }
  documentImportBusy.value = true;
  try {
    const data = await importDetectionDocumentPreview({
      filename: documentPreview.value.filename,
      report_type: documentPreview.value.report_type || documentReportType.value,
      organization_id: organizationId.value || null,
      rows: importRows,
      warnings: documentPreview.value.warnings || [],
    });
    resetDocumentPreview();
    showDocumentPreview.value = false;
    reportStatusFilter.value = '';
    reportPage.value = 1;
    await loadReports();
    toast.show(`已确认入库 ${data.measurement_count || 0} 条检测结果`, 'success');
    await openReport(data.report_id);
  } catch (err) {
    toast.show(formatApiError(err), 'error');
  } finally {
    documentImportBusy.value = false;
  }
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

function useSampleCsv() {
  const sample = SAMPLE_FILES[0];
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
  await loadLimits({ silent: true });
});

watch(organizationId, async (next, previous) => {
  const org = organizations.value.find((item) => item.id === next);
  session.setOrgName(org?.name || '');
  if (next === previous) return;
  reportPage.value = 1;
  await loadReports({ silent: true });
});

watch(activeTab, (next) => {
  if (next === 'limits') loadLimits({ silent: true });
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
        <button type="button" class="btn-secondary" @click="refreshReports">
          <Icon name="refresh" :size="14" />
          刷新
        </button>
        <button type="button" class="btn-secondary" @click="showDocumentPreview = !showDocumentPreview">
          <Icon name="search" :size="14" />
          解析预览
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
        @click="activeTab = 'limits'"
      >
        限值库
      </button>
    </div>

    <section v-if="showUpload" class="upload-panel">
      <div class="upload-panel-inner">
        <h3>导入检测数据</h3>
        <details class="upload-guide" open>
          <summary><span>上传须知</span><small>点击展开/收起</small></summary>
          <div class="upload-guide-body">
            <h4>支持格式</h4>
            <ul>
              <li><strong>CSV</strong> — UTF-8 编码，可用 Excel / WPS 另存为 CSV(UTF-8)</li>
              <li><strong>XLSX / XLSM</strong> — Excel 工作簿，取第一个 Sheet</li>
            </ul>
            <h4>文件限制</h4>
            <ul>
              <li>单文件 ≤ <strong>50MB</strong></li>
              <li>检测行为单位，单次导入无行数上限</li>
            </ul>
            <h4>必需字段</h4>
            <ul>
              <li><code>sample_point</code> — 检测点名称</li>
              <li><code>indicator_name</code> — 检测因子名称</li>
              <li><code>raw_value</code> — 检测值（数字或 <code>&lt;检出限</code> 等标记）</li>
              <li><code>raw_unit</code> — 单位（如 mg/m³、dB(A)、WBGT(℃)）</li>
            </ul>
            <h4>可选字段</h4>
            <ul>
              <li><code>workplace</code> — 车间/场所</li>
              <li><code>post_name</code> — 岗位名称</li>
              <li><code>duration_minutes</code> — 接触时长（分钟），≤15min 会自动修正限值类型为 PC_STEL</li>
              <li><code>shift_hours</code> — 班次时长（小时）</li>
              <li><code>medium</code> — 介质类型</li>
            </ul>
            <h4>行为边界</h4>
            <ul>
              <li>导入后系统自动创建检测报告（状态：已上传）</li>
              <li><strong>不会自动判定合规</strong>——需在报告详情中手动点击「合规判定」触发对标分析</li>
              <li>判定结果不可编辑，如需修正请重新导入</li>
            </ul>
          </div>
        </details>
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

    <section v-if="showDocumentPreview" class="upload-panel">
      <div class="upload-panel-inner">
        <h3>报告解析预览</h3>
        <details class="upload-guide" open>
          <summary><span>解析须知</span><small>点击展开/收起</small></summary>
          <div class="upload-guide-body">
            <h4>支持格式</h4>
            <ul>
              <li><strong>PDF</strong> — 文本层 PDF 直接提取，扫描件需 OCR 服务（Docker 可选启用）</li>
              <li><strong>DOCX / DOC / TXT</strong> — Word 文档和纯文本文件</li>
              <li>
                <strong>ZIP</strong> — 压缩包（含多个 PDF/DOCX/TXT），自动解压并逐文件解析，结果标注来源文件
              </li>
            </ul>
            <h4>文件限制</h4>
            <ul>
              <li>单文件 ≤ <strong>50MB</strong></li>
              <li>仅解析前 60,000 字符</li>
            </ul>
            <h4>解析范围</h4>
            <ul>
              <li>自动识别检测报告中的结构化表格</li>
              <li>提取：检测点、检测因子、数值、单位、限值(如有)、接触时长</li>
              <li>支持职业卫生、废水、废气、噪声、高温 WBGT 五类报告</li>
            </ul>
            <h4>已知局限</h4>
            <ul>
              <li>手写批注、印章遮盖区域无法识别</li>
              <li>扫描件 PDF 未启用 OCR 时文本层为空，会进入「待人工确认」流程</li>
              <li>多层合并表头、跨页断行可能导致部分字段缺失</li>
              <li>报告内嵌标准限值与系统限值库可能不一致，以系统限值库为准</li>
            </ul>
            <h4>行为边界</h4>
            <ul>
              <li>预览页<strong>仅展示解析结果，不会直接写入数据库</strong></li>
              <li>必须进入人工确认页：逐行核对、修正错误字段、勾选需要入库的数据行</li>
              <li>未勾选的行不会入库（含背景行、空白行、错误识别行）</li>
              <li>低置信度行（confidence &lt; 0.7）会有黄色标记，建议重点核对</li>
              <li>入库后与结构化导入流程一致：状态为已上传，需手动触发「合规判定」</li>
              <li>如需重新导入同一份文件，请先删除旧报告避免数据重复</li>
            </ul>
          </div>
        </details>
        <form class="upload-form" @submit.prevent="submitDocumentPreview">
          <div class="form-row">
            <label class="form-field">
              <span class="label-text">报告类型</span>
              <select v-model="documentReportType">
                <option v-for="item in REPORT_TYPES" :key="item.value" :value="item.value">
                  {{ item.label }}
                </option>
              </select>
            </label>
            <label class="form-field file-field">
              <span class="label-text">报告文件</span>
              <div :class="['file-drop', { 'has-file': selectedDocument }]">
                <input
                  ref="documentInput"
                  type="file"
                  accept=".pdf,.docx,.doc,.txt,.zip"
                  @change="onDocumentChange"
                />
                <Icon name="search" :size="24" :stroke="1.5" />
                <span class="file-drop-text">{{ documentLabel }}</span>
                <span class="file-drop-hint">先抽取文本并识别候选检测行，不直接入库</span>
              </div>
            </label>
          </div>
          <div class="form-actions">
            <button type="button" class="btn-secondary" @click="showDocumentPreview = false">关闭</button>
            <button type="button" class="btn-secondary" @click="resetDocumentPreview">清空</button>
            <button type="submit" class="btn-primary" :disabled="documentPreviewBusy || !selectedDocument">
              {{ documentPreviewBusy ? '解析中...' : '解析预览' }}
            </button>
          </div>
        </form>

        <div v-if="documentPreview" class="preview-panel">
          <div class="preview-summary">
            <span>{{ documentPreview.filename }}</span>
            <span>{{ documentPreview.text_char_count }} 字符</span>
            <span>{{ documentPreview.rows?.length || 0 }} 条候选行</span>
          </div>
          <div v-if="documentPreview.warnings?.length" class="preview-warnings">
            <span v-for="warning in documentPreview.warnings" :key="warning">{{ warning }}</span>
          </div>
          <div v-if="documentPreview.rows?.length" class="preview-toolbar">
            <button type="button" class="btn-link-sm" @click="toggleAllRows">
              {{ allPreviewRowsSelected ? '取消全选' : '全选' }}
            </button>
            <button type="button" class="btn-link-sm" @click="deselectLowConfidence(0.7)">
              取消低置信度(&lt;70%)
            </button>
            <span class="preview-toolbar-count"> 已选 {{ selectedImportCount }} 条可入库 </span>
          </div>
          <div class="preview-table-wrap">
            <table class="mini-table preview-edit-table">
              <thead>
                <tr>
                  <th class="col-check">
                    <input type="checkbox" :checked="allPreviewRowsSelected" @change="toggleAllRows" />
                  </th>
                  <th class="col-idx">行</th>
                  <th v-if="documentPreview.source_files?.length > 1" class="col-source">来源文件</th>
                  <th class="col-point">检测点</th>
                  <th class="col-medium">介质</th>
                  <th class="col-indicator">因子</th>
                  <th class="col-value">检测值</th>
                  <th class="col-unit">单位</th>
                  <th class="col-limit-type">限值类型</th>
                  <th class="col-bg">背景</th>
                  <th class="col-status">预判</th>
                  <th class="col-conf">置信度</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="!documentPreview.rows?.length" class="empty-row">
                  <td :colspan="documentPreview.source_files?.length > 1 ? 12 : 11">未识别到候选检测行</td>
                </tr>
                <tr
                  v-for="row in documentPreview.rows"
                  :key="`${row.row_index}-${row.indicator_name}`"
                  :class="{
                    'row-selected': isRowSelected(row),
                    'row-modified': isRowModified(row),
                    'row-low-conf': Number(row.confidence || 0) < 0.7,
                  }"
                >
                  <td class="col-check">
                    <input type="checkbox" :checked="isRowSelected(row)" @change="toggleRow(row.row_index)" />
                  </td>
                  <td class="col-idx">{{ row.row_index }}</td>
                  <td v-if="documentPreview.source_files?.length > 1" class="col-source">
                    {{ row.source_file || '-' }}
                  </td>
                  <td class="col-point">
                    <input
                      type="text"
                      class="cell-input"
                      :value="getEditValue(row, 'sample_point')"
                      @input="setEditValue(row, 'sample_point', $event.target.value)"
                    />
                    <small v-if="row.warnings?.length" class="subtle-line">{{
                      row.warnings.join('；')
                    }}</small>
                  </td>
                  <td class="col-medium">
                    <select
                      class="cell-select"
                      :value="getEditValue(row, 'medium')"
                      @change="setEditValue(row, 'medium', $event.target.value)"
                    >
                      <option v-for="item in MEDIUMS" :key="item.value" :value="item.value">
                        {{ item.label }}
                      </option>
                    </select>
                  </td>
                  <td class="col-indicator">
                    <input
                      type="text"
                      class="cell-input"
                      :value="getEditValue(row, 'indicator_name')"
                      @input="setEditValue(row, 'indicator_name', $event.target.value)"
                    />
                    <small v-if="row.measurement_kind" class="subtle-line">{{ row.measurement_kind }}</small>
                  </td>
                  <td class="col-value">
                    <input
                      type="text"
                      class="cell-input cell-input-num"
                      :value="getEditValue(row, 'raw_value')"
                      @input="setEditValue(row, 'raw_value', $event.target.value)"
                    />
                    <small v-if="getEditValue(row, 'is_below_detection_limit')" class="subtle-line"
                      >低于检出限</small
                    >
                  </td>
                  <td class="col-unit">
                    <input
                      type="text"
                      class="cell-input cell-input-unit"
                      :value="getEditValue(row, 'raw_unit')"
                      @input="setEditValue(row, 'raw_unit', $event.target.value)"
                    />
                  </td>
                  <td class="col-limit-type">
                    <select
                      class="cell-select"
                      :value="getEditValue(row, 'limit_type')"
                      @change="setEditValue(row, 'limit_type', $event.target.value || null)"
                    >
                      <option value="">--</option>
                      <option v-for="item in LIMIT_TYPES" :key="item" :value="item">{{ item }}</option>
                    </select>
                  </td>
                  <td class="col-bg">
                    <input
                      type="checkbox"
                      :checked="getEditValue(row, 'is_background')"
                      @change="setEditValue(row, 'is_background', $event.target.checked)"
                    />
                  </td>
                  <td class="col-status">
                    {{ row.preliminary_status ? complianceText(row.preliminary_status) : '-' }}
                    <small v-if="row.report_limit_value" class="subtle-line">
                      报告限值 {{ formatPreviewLimit(row) }}
                    </small>
                    <small v-if="row.preliminary_message" class="subtle-line">
                      {{ row.preliminary_message }}
                    </small>
                  </td>
                  <td class="col-conf">
                    <span :class="['conf-badge', confidenceClass(row)]">
                      {{ formatNumber(Number(row.confidence) * 100) }}%
                    </span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <details class="text-excerpt">
            <summary>查看抽取文本片段</summary>
            <pre>{{ documentPreview.text_excerpt }}</pre>
          </details>
          <div class="form-actions preview-actions">
            <span class="preview-actions-hint">
              将导入 {{ selectedImportCount }} 条（已勾选 {{ selectedRowIndices.size }} 行）
              <template v-if="documentPreview.rows?.some((r) => isRowModified(r))">
                ·
                <span class="modified-hint"
                  >已修改 {{ documentPreview.rows.filter((r) => isRowModified(r)).length }} 行</span
                >
              </template>
            </span>
            <button
              type="button"
              class="btn-primary"
              :disabled="documentImportBusy || !selectedImportCount"
              @click="importDocumentPreview"
            >
              {{ documentImportBusy ? '入库中...' : '确认入库' }}
            </button>
          </div>
        </div>
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
                <span class="task-filename">{{ labelOf(REPORT_TYPES, report.report_type) }}</span>
                <small v-if="report.report_date" class="subtle-line">检测日期 {{ report.report_date }}</small>
                <small v-else class="subtle-line">上传于 {{ formatTime(report.created_at) }}</small>
                <small class="subtle-line" style="color: var(--text-tertiary)">{{ report.filename }}</small>
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
      <div
        v-if="
          !limits.length &&
          !limitsBusy &&
          limitFilter.indicatorName === '' &&
          limitFilter.medium === '' &&
          limitFilter.standardCode === ''
        "
        class="empty-state"
      >
        限值库为空，请通过种子脚本导入国家标准限值
      </div>
      <div class="task-filters detection-filters">
        <label class="filter-field">
          <span class="label-text">因子</span>
          <input
            v-model="limitFilter.indicatorName"
            placeholder="苯 / pH / 噪声 / 高温WBGT"
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
            placeholder="GBZ 2.1-2019"
            @keydown.enter="applyLimitFilters"
          />
        </label>
        <button type="button" class="btn-secondary filter-reset" @click="applyLimitFilters">查询</button>
      </div>
      <div class="task-list-header">
        <span class="task-count">{{ limitCountText }}</span>
      </div>
      <div class="task-table-wrap">
        <table class="task-table">
          <thead>
            <tr>
              <th>因子</th>
              <th>介质</th>
              <th>限值类型</th>
              <th>限值</th>
              <th>来源依据</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!limits.length" class="empty-row">
              <td colspan="5">{{ limitsBusy ? '加载中...' : '暂无限值' }}</td>
            </tr>
            <tr v-for="limit in limits" :key="limit.id">
              <td>
                <span class="task-filename">{{ limit.indicator_name }}</span>
                <small v-if="limit.cas_no" class="subtle-line">CAS: {{ limit.cas_no }}</small>
                <small v-if="limit.aliases?.length" class="subtle-line"
                  >别名: {{ limit.aliases.slice(0, 3).join(', ')
                  }}{{ limit.aliases.length > 3 ? ' 等' : '' }}</small
                >
              </td>
              <td>{{ labelOf(MEDIUMS, limit.medium) }}</td>
              <td>{{ limit.limit_type }}</td>
              <td class="col-limit-value">
                <template v-if="limit.limit_type === 'RANGE'">
                  <span class="limit-number">{{ formatNumber(limit.limit_min) }}</span>
                  <span class="limit-sep">~</span>
                  <span class="limit-number">{{ formatNumber(limit.limit_max) }}</span>
                </template>
                <template v-else>
                  <span class="limit-number">{{ formatNumber(limit.limit_value) }}</span>
                </template>
                <span class="limit-unit">{{ limit.unit }}</span>
              </td>
              <td class="col-limit-source">
                <span class="limit-source-code">{{ limit.standard_code || '-' }}</span>
                <small v-if="limit.standard_name" class="subtle-line">{{ limit.standard_name }}</small>
                <small v-if="limit.clause" class="subtle-line">条款 {{ limit.clause }}</small>
                <small v-if="limit.basis_text" class="subtle-line basis-text">{{ limit.basis_text }}</small>
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
            <button class="page-btn" :disabled="limitPage >= limitPages" @click="goLimitPage(limitPage + 1)">
              &gt;
            </button>
          </template>
        </div>
      </div>
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
.preview-panel {
  display: grid;
  gap: 12px;
  margin-top: 16px;
}
.preview-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  color: var(--text-secondary);
  font-size: 12px;
}
.preview-summary span,
.preview-warnings span {
  padding: 4px 8px;
  border: 1px solid var(--border);
  border-radius: 999px;
  background: var(--panel);
}
.preview-warnings {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  color: var(--warning);
  font-size: 12px;
}
.preview-table-wrap {
  max-height: 320px;
  overflow: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius);
}
.text-excerpt {
  color: var(--text-secondary);
  font-size: 12px;
}
.text-excerpt summary {
  cursor: pointer;
  font-weight: 700;
}
.text-excerpt pre {
  max-height: 220px;
  margin-top: 8px;
  padding: 12px;
  overflow: auto;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--bg-subtle);
  color: var(--text);
  white-space: pre-wrap;
  word-break: break-word;
}
.preview-actions {
  margin-top: 12px;
  align-items: center;
  justify-content: flex-end;
  gap: 12px;
}
.preview-actions-hint {
  margin-right: auto;
  color: var(--text-secondary);
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

/* ---- 人工确认：工具栏 ---- */
.preview-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
}
.btn-link-sm {
  padding: 3px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--panel);
  color: var(--accent);
  font-size: 11px;
  cursor: pointer;
  transition: all var(--transition);
}
.btn-link-sm:hover {
  background: var(--accent-bg);
  border-color: var(--accent);
}
.preview-toolbar-count {
  margin-left: auto;
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 600;
}
.modified-hint {
  color: var(--warning);
}

/* ---- 预览编辑表格 ---- */
.preview-edit-table {
  min-width: 980px;
}
.preview-edit-table th,
.preview-edit-table td {
  vertical-align: top;
}
.col-check {
  width: 32px;
  text-align: center;
}
.col-idx {
  width: 40px;
}
.col-source {
  min-width: 90px;
  max-width: 140px;
  font-size: 12px;
  color: var(--text-tertiary);
}
.col-point {
  min-width: 110px;
}
.col-medium {
  width: 90px;
}
.col-indicator {
  min-width: 100px;
}
.col-value {
  width: 80px;
}
.col-unit {
  width: 64px;
}
.col-limit-type {
  width: 100px;
}
.col-bg {
  width: 44px;
  text-align: center;
}
.col-status {
  min-width: 80px;
}
.col-conf {
  width: 64px;
  text-align: center;
}

.cell-input {
  width: 100%;
  padding: 3px 5px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--bg);
  color: var(--text);
  font-size: 12px;
  font-family: inherit;
  transition: border-color var(--transition);
}
.cell-input:focus {
  outline: none;
  border-color: var(--accent);
  box-shadow: 0 0 0 2px var(--accent-bg);
}
.cell-input-num {
  text-align: right;
  font-variant-numeric: tabular-nums;
}
.cell-input-unit {
  text-align: center;
}
.cell-select {
  width: 100%;
  padding: 2px 4px;
  border: 1px solid var(--border);
  border-radius: 4px;
  background: var(--bg);
  color: var(--text);
  font-size: 11px;
  font-family: inherit;
}
.cell-select:focus {
  outline: none;
  border-color: var(--accent);
}

/* ---- 行状态 ---- */
.preview-edit-table tbody tr.row-selected {
  background: var(--accent-bg);
}
.preview-edit-table tbody tr.row-modified {
  border-left: 3px solid var(--warning);
}
.preview-edit-table tbody tr.row-low-conf {
  --stripe: rgba(255 160 60 / 0.08);
  background: var(--stripe);
}
.preview-edit-table tbody tr.row-low-conf.row-selected {
  background: color-mix(in srgb, var(--accent-bg) 70%, var(--stripe));
}

/* ---- 置信度徽标 ---- */
.conf-badge {
  display: inline-block;
  padding: 1px 7px;
  border-radius: 999px;
  font-size: 11px;
  font-weight: 700;
}
.conf-high {
  background: var(--success-bg);
  color: var(--success);
}
.conf-medium {
  background: var(--warning-bg);
  color: var(--warning);
}
.conf-low {
  background: var(--danger-bg);
  color: var(--danger);
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

/* ---- 上传须知指引 ---- */
.upload-guide {
  margin-bottom: 14px;
  border: 1px solid #fcd34d;
  border-radius: var(--radius);
  background: #fffbeb;
  overflow: hidden;
}
.upload-guide summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  cursor: pointer;
  font-weight: 700;
  color: #92400e;
  background: linear-gradient(135deg, #fef3c7 0%, #fde68a 100%);
  list-style: none;
}
.upload-guide summary::-webkit-details-marker {
  display: none;
}
.upload-guide summary span {
  font-size: 14px;
}
.upload-guide summary small {
  font-size: 11px;
  color: #a16207;
  font-weight: 500;
}
.upload-guide-body {
  padding: 12px 16px 16px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-secondary);
}
.upload-guide-body h4 {
  margin: 12px 0 6px;
  font-size: 13px;
  font-weight: 700;
  color: var(--text);
}
.upload-guide-body h4:first-child {
  margin-top: 0;
}
.upload-guide-body ul {
  margin: 0 0 4px;
  padding-left: 18px;
  list-style: disc;
}
.upload-guide-body li {
  margin-bottom: 3px;
  color: var(--text-tertiary);
}
.upload-guide-body code {
  font-size: 12px;
  background: #fef3c7;
  padding: 1px 5px;
  border-radius: 3px;
  color: #92400e;
}
.upload-guide-body strong {
  color: var(--text);
}

/* ---- 限值表格优化 ---- */
.col-limit-value {
  white-space: nowrap;
}
.limit-number {
  font-weight: 700;
  font-variant-numeric: tabular-nums;
  font-family: 'SF Mono', 'Cascadia Code', 'Consolas', monospace;
  font-size: 13px;
}
.limit-sep {
  margin: 0 4px;
  color: var(--text-tertiary);
}
.limit-unit {
  margin-left: 4px;
  font-size: 12px;
  color: var(--text-tertiary);
}
.col-limit-source {
  min-width: 240px;
}
.limit-source-code {
  display: block;
  font-weight: 600;
  font-size: 13px;
}
.col-limit-source .subtle-line {
  display: block;
  margin-top: 2px;
  font-size: 11px;
  line-height: 1.4;
}
.col-limit-source .basis-text {
  color: var(--text-tertiary);
  font-style: italic;
}
</style>
