<script setup>
import { computed, onMounted, reactive, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
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
const DETECTION_SERVICE_TYPES = [
  { value: '定期检测', label: '定期检测' },
  { value: '控制效果评价检测', label: '控制效果评价检测' },
  { value: '现状评价检测', label: '现状评价检测' },
  { value: '环保', label: '环保' },
  { value: '安全', label: '安全' },
];
const DEFAULT_DETECTION_SERVICE_TYPE = DETECTION_SERVICE_TYPES[0].value;
const SERVICE_TYPE_REPORT_TYPES = {
  定期检测: 'OCCUPATIONAL_HEALTH',
  控制效果评价检测: 'OCCUPATIONAL_HEALTH',
  现状评价检测: 'OCCUPATIONAL_HEALTH',
  环保: 'WASTEWATER',
  安全: 'OCCUPATIONAL_HEALTH',
};
const SAMPLE_FILES = [
  {
    key: 'occupational',
    label: '职业卫生样例',
    filename: '职业卫生检测样例.csv',
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
const route = useRoute();
const router = useRouter();

const activeTab = ref(route.query.tab === 'limits' ? 'limits' : 'reports');
const organizations = ref([]);
const organizationId = ref('');

const reports = ref([]);
const reportPage = ref(1);
const reportPageSize = 15;
const reportTotal = ref(0);
const reportPages = ref(0);
const reportStatusFilter = ref('');
const reportClientNameFilter = ref('');
const reportProjectNameFilter = ref('');
const reportProjectCodeFilter = ref('');
const reportServiceTypeFilter = ref('');
const reportsBusy = ref(false);
const detectionStats = reactive({
  total: '-',
  calculated: '-',
  pending: '-',
  failed: '-',
});

const showUpload = ref(false);
const fileInput = ref(null);
const selectedFile = ref(null);
const fileLabel = ref('点击选择 CSV / XLSX / PDF / DOCX 文件');
const uploadBusy = ref(false);
const uploadReportName = ref('');
const uploadClientName = ref('');
const uploadProjectName = ref('');
const uploadProjectCode = ref('');
const uploadServiceType = ref(DEFAULT_DETECTION_SERVICE_TYPE);

const showDocumentPreview = ref(false);
const documentInput = ref(null);
const selectedDocument = ref(null);
const documentLabel = ref('点击选择 PDF / DOCX / DOC / TXT / ZIP 文件');
const documentReportName = ref('');
const documentClientName = ref('');
const documentProjectName = ref('');
const documentProjectCode = ref('');
const documentServiceType = ref(DEFAULT_DETECTION_SERVICE_TYPE);
const documentPreviewBusy = ref(false);
const documentImportBusy = ref(false);
const documentPreview = ref(null);
const previewReviewOnly = ref(false);

const drawerOpen = ref(false);
const activeReport = ref(null);
const activeResults = ref([]);
const calculateBusy = ref(false);
const RESULT_PREVIEW_LIMIT = 20;
const RESULT_STATUS_FILTERS = [
  { value: 'abnormal', label: '只看异常' },
  { value: 'all', label: '全部' },
  { value: 'EXCEEDED', label: '超标' },
  { value: 'BORDERLINE', label: '临界' },
  { value: 'review', label: '待复核/数据不足' },
  { value: 'COMPLIANT', label: '合规' },
];
const resultStatusFilter = ref('abnormal');
const resultShowAll = ref(false);

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
const detectionStatItems = computed(() => [
  { label: '检测任务', value: detectionStats.total, tone: 'accent' },
  { label: '已判定', value: detectionStats.calculated, tone: 'success' },
  { label: '待处理', value: detectionStats.pending, tone: 'info' },
  { label: '失败报告', value: detectionStats.failed, tone: 'danger' },
]);
const selectedOrgName = computed(
  () => organizations.value.find((item) => item.id === organizationId.value)?.name || '',
);
const uploadReportType = computed(() => reportTypeForServiceType(uploadServiceType.value));
const documentReportType = computed(() => reportTypeForServiceType(documentServiceType.value));
const defaultReportName = computed(() => {
  const orgName = selectedOrgName.value || '公司';
  const businessType = uploadServiceType.value || DEFAULT_DETECTION_SERVICE_TYPE;
  return `${orgName} ${businessType}报告 ${new Date().toISOString().slice(0, 10)}`;
});
const defaultDocumentReportName = computed(() => {
  const orgName = selectedOrgName.value || '公司';
  const businessType = documentServiceType.value || DEFAULT_DETECTION_SERVICE_TYPE;
  return `${orgName} ${businessType}报告 ${new Date().toISOString().slice(0, 10)}`;
});
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
    compliant: rows.filter((item) => item.status === 'COMPLIANT').length,
  };
});
const sortedActiveResults = computed(() => {
  const rank = { EXCEEDED: 0, BORDERLINE: 1, NEEDS_REVIEW: 2, INSUFFICIENT_DATA: 3, COMPLIANT: 4 };
  return [...(activeResults.value || [])].sort((a, b) => (rank[a.status] ?? 9) - (rank[b.status] ?? 9));
});
const filteredActiveResults = computed(() => {
  const rows = sortedActiveResults.value;
  const filter = resultStatusFilter.value;
  if (filter === 'all') return rows;
  if (filter === 'abnormal') {
    return rows.filter((item) => ['EXCEEDED', 'BORDERLINE', 'NEEDS_REVIEW', 'INSUFFICIENT_DATA'].includes(item.status));
  }
  if (filter === 'review') {
    return rows.filter((item) => ['NEEDS_REVIEW', 'INSUFFICIENT_DATA'].includes(item.status));
  }
  return rows.filter((item) => item.status === filter);
});
const visibleActiveResults = computed(() =>
  resultShowAll.value ? filteredActiveResults.value : filteredActiveResults.value.slice(0, RESULT_PREVIEW_LIMIT),
);
const hiddenResultCount = computed(() =>
  Math.max(filteredActiveResults.value.length - visibleActiveResults.value.length, 0),
);
const resultDisplayCountText = computed(() => {
  const visible = visibleActiveResults.value.length;
  const filtered = filteredActiveResults.value.length;
  const total = sortedActiveResults.value.length;
  if (filtered === total) return `显示 ${visible} / ${total} 条`;
  return `显示 ${visible} / ${filtered} 条，全部 ${total} 条`;
});
const resultToggleText = computed(() =>
  resultShowAll.value ? `收起到 ${RESULT_PREVIEW_LIMIT} 条` : `显示全部剩余 ${hiddenResultCount.value} 条`,
);
watch(resultStatusFilter, () => {
  resultShowAll.value = false;
});

// ---- 人工确认：行选择 + 行内编辑 ----
const selectedRowIndices = ref(new Set());
const rowEdits = ref({});
const previewVisibleColumns = reactive({
  source: true,
  medium: true,
  limitType: true,
  exclude: true,
  status: true,
  confidence: true,
});
const previewColumnOptions = [
  { key: 'source', label: '来源' },
  { key: 'medium', label: '介质' },
  { key: 'limitType', label: '限值类型' },
  { key: 'exclude', label: '排除' },
  { key: 'status', label: '预判' },
  { key: 'confidence', label: '核对' },
];
const hasPreviewSourceColumn = computed(
  () => previewVisibleColumns.source && documentPreview.value?.source_files?.length > 1,
);
const previewColspan = computed(() => {
  let count = 6;
  if (hasPreviewSourceColumn.value) count += 1;
  if (previewVisibleColumns.medium) count += 1;
  if (previewVisibleColumns.limitType) count += 1;
  if (previewVisibleColumns.exclude) count += 1;
  if (previewVisibleColumns.status) count += 1;
  if (previewVisibleColumns.confidence) count += 1;
  return count;
});

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
  const rows = displayedPreviewRows.value || [];
  return rows.length > 0 && rows.every((r) => selectedRowIndices.value.has(r.row_index));
});

function toggleAllRows() {
  const rows = displayedPreviewRows.value || [];
  const next = new Set(selectedRowIndices.value);
  if (allPreviewRowsSelected.value) {
    for (const r of rows) next.delete(r.row_index);
  } else {
    for (const r of rows) next.add(r.row_index);
  }
  selectedRowIndices.value = next;
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
  return rows.filter((r) => selectedRowIndices.value.has(r.row_index) && isImportablePreviewRow(r)).length;
});
const previewRows = computed(() => documentPreview.value?.rows || []);
const previewRowCount = computed(() => previewRows.value.length);
const selectedPreviewCount = computed(() => selectedRowIndices.value.size);
const lowConfidenceCount = computed(() =>
  previewRows.value.filter((r) => Number(r.confidence || 0) < 0.7).length,
);
const backgroundRowCount = computed(
  () => previewRows.value.filter((r) => getEditValue(r, 'is_background')).length,
);
const modifiedPreviewCount = computed(() => previewRows.value.filter((r) => isRowModified(r)).length);
const previewWarningCount = computed(() => documentPreview.value?.warnings?.length || 0);
const previewImportableTotal = computed(() => previewRows.value.filter((r) => isImportablePreviewRow(r)).length);
const displayedPreviewRows = computed(() => {
  if (!previewReviewOnly.value) return previewRows.value;
  return previewRows.value.filter(
    (row) =>
      Number(row.confidence || 0) < 0.7 ||
      row.warnings?.length ||
      !isImportablePreviewRow(row) ||
      row.preliminary_status === 'NEEDS_REVIEW',
  );
});

function isImportablePreviewRow(row) {
  const isBg = getEditValue(row, 'is_background');
  const raw = getEditValue(row, 'raw_value');
  const samplePoint = String(getEditValue(row, 'sample_point') || '').trim();
  const indicatorName = String(getEditValue(row, 'indicator_name') || '').trim();
  return !isBg && raw !== null && raw !== '' && samplePoint !== '' && indicatorName !== '';
}

function buildImportRows() {
  const rows = documentPreview.value?.rows || [];
  return rows
    .filter((r) => selectedRowIndices.value.has(r.row_index))
    .filter((r) => isImportablePreviewRow(r))
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

function confidenceLabel(row) {
  const c = Number(row.confidence || 0);
  if (c >= 0.85) return '较可靠';
  if (c >= 0.7) return '需核对';
  return '重点核对';
}

function labelOf(options, value) {
  return options.find((item) => item.value === value)?.label || value || '-';
}

function reportTypeForServiceType(serviceType) {
  return SERVICE_TYPE_REPORT_TYPES[serviceType] || 'OCCUPATIONAL_HEALTH';
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

function setResultFilter(filter) {
  resultStatusFilter.value = filter;
  resultShowAll.value = false;
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

function contextParts(record) {
  const parts = [];
  if (record?.client_name) parts.push(`客户：${record.client_name}`);
  if (record?.project_name) parts.push(`项目：${record.project_name}`);
  if (record?.project_code) parts.push(`编号：${record.project_code}`);
  if (record?.service_type) parts.push(`报告类别：${record.service_type}`);
  return parts;
}

function contextText(record) {
  return contextParts(record).join(' · ');
}

function resetUpload() {
  if (fileInput.value) fileInput.value.value = '';
  selectedFile.value = null;
  fileLabel.value = '点击选择 CSV / XLSX / PDF / DOCX 文件';
  uploadReportName.value = '';
  uploadClientName.value = '';
  uploadProjectName.value = '';
  uploadProjectCode.value = '';
  uploadServiceType.value = DEFAULT_DETECTION_SERVICE_TYPE;
}

function resetDocumentPreview() {
  if (documentInput.value) documentInput.value.value = '';
  selectedDocument.value = null;
  documentLabel.value = '点击选择 PDF / DOCX / DOC / TXT / ZIP 文件';
  documentReportName.value = '';
  documentClientName.value = '';
  documentProjectName.value = '';
  documentProjectCode.value = '';
  documentServiceType.value = DEFAULT_DETECTION_SERVICE_TYPE;
  documentPreview.value = null;
  previewReviewOnly.value = false;
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
  if (!ALLOWED_EXTENSIONS.has(ext) && !DOCUMENT_EXTENSIONS.has(ext)) {
    toast.show('仅支持 CSV、XLSX、XLSM、PDF、DOCX、DOC、TXT、ZIP 文件', 'error');
    resetUpload();
    return;
  }
  if (file.size > MAX_FILE_BYTES) {
    toast.show('文件大小不能超过 50MB', 'error');
    resetUpload();
    return;
  }
  if (DOCUMENT_EXTENSIONS.has(ext)) {
    selectedDocument.value = file;
    documentLabel.value = file.name;
    documentReportName.value = uploadReportName.value;
    documentClientName.value = uploadClientName.value;
    documentProjectName.value = uploadProjectName.value;
    documentProjectCode.value = uploadProjectCode.value;
    documentServiceType.value = uploadServiceType.value;
    documentPreview.value = null;
    previewReviewOnly.value = false;
    selectedRowIndices.value = new Set();
    rowEdits.value = {};
    resetUpload();
    showUpload.value = false;
    showDocumentPreview.value = true;
    toast.show('报告文件已切换到解析预览，请确认候选行后再入库', 'info');
    return;
  }
  fileLabel.value = file.name;
}

function onDocumentChange(event) {
  const file = event.target.files?.[0];
  selectedDocument.value = file || null;
  documentPreview.value = null;
  previewReviewOnly.value = false;
  if (!file) {
    resetDocumentPreview();
    return;
  }
  const ext = file.name.split('.').pop()?.toLowerCase() || '';
  if (!DOCUMENT_EXTENSIONS.has(ext)) {
    toast.show('仅支持 PDF、DOCX、DOC、TXT、ZIP 文件', 'error');
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
    previewReviewOnly.value = false;
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
      report_name: documentReportName.value.trim() || null,
      client_name: documentClientName.value.trim() || null,
      project_name: documentProjectName.value.trim() || null,
      project_code: documentProjectCode.value.trim() || null,
      service_type: documentServiceType.value.trim() || null,
      report_type: documentPreview.value.report_type || documentReportType.value,
      organization_id: organizationId.value || null,
      rows: importRows,
      warnings: documentPreview.value.warnings || [],
    });
    resetDocumentPreview();
    showDocumentPreview.value = false;
    reportStatusFilter.value = '';
    reportPage.value = 1;
    await Promise.all([loadReports(), loadDetectionStats({ silent: true })]);
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
    const selectedOrg = organizations.value.find((item) => item.id === organizationId.value);
    if (session.isAdmin) {
      if (!selectedOrg) organizationId.value = '';
      session.setOrgName(selectedOrg?.name || '');
    } else if (selectedOrg) {
      session.setOrgName(selectedOrg.name || '');
    } else if (organizations.value.length) {
      organizationId.value = organizations.value[0].id;
      session.setOrgName(organizations.value[0].name || '');
    } else {
      organizationId.value = '';
      session.setOrgName('');
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
      status: reportStatusFilter.value,
      clientName: reportClientNameFilter.value.trim(),
      projectName: reportProjectNameFilter.value.trim(),
      projectCode: reportProjectCodeFilter.value.trim(),
      serviceType: reportServiceTypeFilter.value,
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

async function loadDetectionStats({ silent = false } = {}) {
  try {
    const [total, calculated, failed] = await Promise.all([
      listDetectionReports(1, 1, { organizationId: organizationId.value }),
      listDetectionReports(1, 1, { organizationId: organizationId.value, status: 'CALCULATED' }),
      listDetectionReports(1, 1, { organizationId: organizationId.value, status: 'FAILED' }),
    ]);
    const totalCount = total?.total || 0;
    const calculatedCount = calculated?.total || 0;
    const failedCount = failed?.total || 0;
    detectionStats.total = totalCount;
    detectionStats.calculated = calculatedCount;
    detectionStats.failed = failedCount;
    detectionStats.pending = Math.max(totalCount - calculatedCount - failedCount, 0);
  } catch (err) {
    if (!silent) toast.show(formatApiError(err), 'error');
  }
}

async function refreshReports() {
  await Promise.all([loadReports(), loadDetectionStats({ silent: true })]);
  toast.show('报告列表已刷新', 'success');
}

async function submitUpload() {
  if (uploadBusy.value) return;
  const file = selectedFile.value || fileInput.value?.files?.[0];
  if (!file) {
    toast.show('请选择检测数据文件或报告文件', 'error');
    return;
  }
  uploadBusy.value = true;
  try {
    const data = await createDetectionReport(file, {
      organizationId: organizationId.value,
      reportType: uploadReportType.value,
      reportName: uploadReportName.value,
      clientName: uploadClientName.value,
      projectName: uploadProjectName.value,
      projectCode: uploadProjectCode.value,
      serviceType: uploadServiceType.value,
    });
    resetUpload();
    showUpload.value = false;
    reportStatusFilter.value = '';
    reportPage.value = 1;
    await Promise.all([loadReports(), loadDetectionStats({ silent: true })]);
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
    setResultFilter('abnormal');
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
    setResultFilter('abnormal');
    await Promise.all([loadReports({ silent: true }), loadDetectionStats({ silent: true })]);
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

function resetReportFilters() {
  reportStatusFilter.value = '';
  reportClientNameFilter.value = '';
  reportProjectNameFilter.value = '';
  reportProjectCodeFilter.value = '';
  reportServiceTypeFilter.value = '';
  applyReportFilters();
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
  uploadReportName.value = '';
  uploadClientName.value = '';
  uploadProjectName.value = '';
  uploadProjectCode.value = '';
  uploadServiceType.value = DEFAULT_DETECTION_SERVICE_TYPE;
  showUpload.value = true;
}

onMounted(async () => {
  await loadOrganizations();
  await Promise.all([loadReports(), loadDetectionStats({ silent: true })]);
  await loadLimits({ silent: true });
});

watch(organizationId, async (next, previous) => {
  const org = organizations.value.find((item) => item.id === next);
  session.setOrgName(org?.name || '');
  if (next === previous) return;
  reportPage.value = 1;
  await Promise.all([loadReports({ silent: true }), loadDetectionStats({ silent: true })]);
});

watch(activeTab, (next) => {
  const query = { ...route.query };
  if (next === 'limits') {
    query.tab = 'limits';
  } else {
    delete query.tab;
  }
  router.replace({ query });
  if (next === 'limits') loadLimits({ silent: true });
});

watch(
  () => route.query.tab,
  (tab) => {
    const next = tab === 'limits' ? 'limits' : 'reports';
    if (activeTab.value !== next) activeTab.value = next;
  },
);
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
        <button type="button" class="btn-primary" @click="showUpload = !showUpload">
          <Icon name="upload" :size="14" />
          导入数据/报告
        </button>
      </div>
    </header>

    <div class="task-stat-strip detection-stat-strip">
      <div
        v-for="item in detectionStatItems"
        :key="item.label"
        :class="['task-stat-card', item.tone]"
      >
        <span>{{ item.value }}</span>
        <small>{{ item.label }}</small>
      </div>
    </div>

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
        <h3>导入检测数据/报告</h3>
        <details class="upload-guide">
          <summary><span>上传须知</span><small>检测文件需要包含的信息</small></summary>
          <div class="upload-guide-body">
            <h4>支持格式</h4>
            <ul>
              <li><strong>CSV</strong> — UTF-8 编码，可用 Excel / WPS 另存为 CSV(UTF-8)</li>
              <li><strong>XLSX / XLSM</strong> — Excel 工作簿，取第一个 Sheet</li>
              <li><strong>PDF / DOCX / DOC / TXT / ZIP</strong> — 选择后自动进入报告解析预览</li>
            </ul>
            <h4>结构化表格必须包含</h4>
            <ul>
              <li><strong>检测点 / sample_point</strong> — 采样点、岗位或监测点名称</li>
              <li><strong>检测因子 / indicator_name</strong> — 如苯、甲苯、噪声、粉尘、WBGT</li>
              <li><strong>检测值 / raw_value</strong> — 实测数值；低于检出限可按检出限或原报告数值填写</li>
              <li><strong>单位 / raw_unit</strong> — 如 mg/m3、μg/m3、dB(A)、WBGT(℃)、mg/L</li>
            </ul>
            <h4>建议补充字段</h4>
            <ul>
              <li><strong>介质</strong>：工作场所空气、噪声、高温、废水、废气；不填时按报告类别推断</li>
              <li><strong>车间/岗位</strong>：用于定位问题和后续整改</li>
              <li><strong>采样时长</strong>：职业卫生化学因素 TWA/STEL、噪声 8h 等效计算会用到</li>
              <li><strong>班次时长</strong>：噪声和接触时间换算需要</li>
              <li><strong>CAS 号/别名</strong>：同名或易混淆因子可提高限值匹配准确率</li>
              <li><strong>报告内限值</strong>：系统限值库未命中时可作为兜底参考，并标记需复核</li>
            </ul>
            <h4>PDF / Word 报告建议包含</h4>
            <ul>
              <li>报告编号、委托单位、检测日期、检测机构</li>
              <li>检测点位、岗位/车间、检测因子、检测结果、单位、采样时长</li>
              <li>原报告中的评价标准、限值、结论或备注</li>
              <li>多文件 ZIP 建议按报告或附件拆分，系统会标注来源文件</li>
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
              <select v-if="session.isAdmin" v-model="organizationId">
                <option value="">默认公司</option>
                <option v-for="org in organizations" :key="org.id" :value="org.id">{{ org.name }}</option>
              </select>
              <input v-else :value="selectedOrgName || session.orgName || '默认公司'" disabled />
            </label>
            <label class="form-field">
              <span class="label-text">报告类别</span>
              <select v-model="uploadServiceType">
                <option v-for="item in DETECTION_SERVICE_TYPES" :key="item.value" :value="item.value">
                  {{ item.label }}
                </option>
              </select>
            </label>
            <label class="form-field">
              <span class="label-text">报告名称</span>
              <input
                v-model="uploadReportName"
                type="text"
                maxlength="255"
                :placeholder="defaultReportName"
              />
            </label>
            <label class="form-field">
              <span class="label-text">委托单位 / 客户公司</span>
              <input v-model="uploadClientName" type="text" maxlength="255" placeholder="例如：某某制造有限公司" />
            </label>
            <label class="form-field">
              <span class="label-text">项目名称</span>
              <input v-model="uploadProjectName" type="text" maxlength="255" placeholder="例如：年度职业卫生检测" />
            </label>
            <label class="form-field">
              <span class="label-text">项目编号</span>
              <input v-model="uploadProjectCode" type="text" maxlength="64" placeholder="可选" />
            </label>
            <label class="form-field file-field">
              <span class="label-text">数据/报告文件</span>
              <div :class="['file-drop', { 'has-file': selectedFile }]">
                <input ref="fileInput" type="file" accept=".csv,.xlsx,.xlsm,.pdf,.docx,.doc,.txt,.zip" @change="onFileChange" />
                <Icon name="upload" :size="24" :stroke="1.5" />
                <span class="file-drop-text">{{ fileLabel }}</span>
                <span class="file-drop-hint">结构化表格直接导入；报告文件先解析预览；最大 50MB</span>
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
        <details class="upload-guide">
          <summary><span>解析规则</span><small>查看格式和边界</small></summary>
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
        <div class="preview-flow">
          <div class="preview-step active">
            <span>1</span>
            <strong>上传报告</strong>
          </div>
          <div :class="['preview-step', { active: documentPreview }]">
            <span>2</span>
            <strong>核对数据</strong>
          </div>
          <div :class="['preview-step', { active: selectedImportCount > 0 }]">
            <span>3</span>
            <strong>确认入库</strong>
          </div>
        </div>
        <form class="upload-form" @submit.prevent="submitDocumentPreview">
          <div class="form-row">
            <label class="form-field">
              <span class="label-text">报告类别</span>
              <select v-model="documentServiceType">
                <option v-for="item in DETECTION_SERVICE_TYPES" :key="item.value" :value="item.value">
                  {{ item.label }}
                </option>
              </select>
            </label>
            <label class="form-field">
              <span class="label-text">报告名称</span>
              <input
                v-model="documentReportName"
                type="text"
                maxlength="255"
                :placeholder="defaultDocumentReportName"
              />
            </label>
            <label class="form-field">
              <span class="label-text">委托单位 / 客户公司</span>
              <input v-model="documentClientName" type="text" maxlength="255" placeholder="例如：某某制造有限公司" />
            </label>
            <label class="form-field">
              <span class="label-text">项目名称</span>
              <input v-model="documentProjectName" type="text" maxlength="255" placeholder="例如：年度职业卫生检测" />
            </label>
            <label class="form-field">
              <span class="label-text">项目编号</span>
              <input v-model="documentProjectCode" type="text" maxlength="64" placeholder="可选" />
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
          <div class="preview-result-head">
            <div>
              <span class="preview-kicker">解析结果</span>
              <h4>{{ documentReportName || defaultDocumentReportName }}</h4>
              <p>
                来源文件：{{ documentPreview.filename }}；已识别 {{ previewRowCount }} 行，当前将入库
                {{ selectedImportCount }} 条检测数据
              </p>
            </div>
            <div class="preview-result-actions">
              <button type="button" class="btn-secondary" :disabled="documentPreviewBusy" @click="submitDocumentPreview">
                重新解析
              </button>
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
          <div class="preview-stat-grid">
            <div class="preview-stat">
              <span>{{ previewRowCount }}</span>
              <small>识别行</small>
            </div>
            <div class="preview-stat strong">
              <span>{{ selectedImportCount }}</span>
              <small>将入库</small>
            </div>
            <div class="preview-stat warn">
              <span>{{ lowConfidenceCount }}</span>
              <small>需重点核对</small>
            </div>
            <div class="preview-stat muted">
              <span>{{ backgroundRowCount }}</span>
              <small>已排除</small>
            </div>
          </div>
          <details v-if="documentPreview.warnings?.length" class="preview-warnings">
            <summary>需要注意 {{ previewWarningCount }} 项</summary>
            <ul>
              <li v-for="warning in documentPreview.warnings" :key="warning">{{ warning }}</li>
            </ul>
          </details>
          <div v-if="documentPreview.rows?.length" class="preview-toolbar">
            <div class="preview-toolbar-main">
              <label class="preview-toggle">
                <input v-model="previewReviewOnly" type="checkbox" />
                <span>只看需核对行</span>
              </label>
              <label
                v-for="column in previewColumnOptions"
                :key="column.key"
                class="preview-toggle"
              >
                <input v-model="previewVisibleColumns[column.key]" type="checkbox" />
                <span>{{ column.label }}</span>
              </label>
              <button type="button" class="btn-link-sm" @click="toggleAllRows">
                {{ allPreviewRowsSelected ? '取消全选' : '全选' }}
              </button>
              <button type="button" class="btn-link-sm" @click="deselectLowConfidence(0.7)">
                取消需核对行
              </button>
            </div>
            <span class="preview-toolbar-count">
              已勾选 {{ selectedPreviewCount }} 行，可入库 {{ previewImportableTotal }} 条
            </span>
          </div>
          <div class="preview-table-wrap">
            <table class="mini-table preview-edit-table">
              <thead>
                <tr>
                  <th class="col-check">
                    <input type="checkbox" :checked="allPreviewRowsSelected" @change="toggleAllRows" />
                  </th>
                  <th class="col-idx">#</th>
                  <th v-if="hasPreviewSourceColumn" class="col-source">来源文件</th>
                  <th class="col-point">检测点</th>
                  <th v-if="previewVisibleColumns.medium" class="col-medium">介质</th>
                  <th class="col-indicator">因子</th>
                  <th class="col-value">检测值</th>
                  <th class="col-unit">单位</th>
                  <th v-if="previewVisibleColumns.limitType" class="col-limit-type">限值类型</th>
                  <th v-if="previewVisibleColumns.exclude" class="col-bg">排除</th>
                  <th v-if="previewVisibleColumns.status" class="col-status">预判</th>
                  <th v-if="previewVisibleColumns.confidence" class="col-conf">核对</th>
                </tr>
              </thead>
              <tbody>
                <tr v-if="!displayedPreviewRows.length" class="empty-row">
                  <td :colspan="previewColspan">
                    未识别到可确认数据
                  </td>
                </tr>
                <tr
                  v-for="row in displayedPreviewRows"
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
                  <td v-if="hasPreviewSourceColumn" class="col-source">
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
                  <td v-if="previewVisibleColumns.medium" class="col-medium">
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
                  <td v-if="previewVisibleColumns.limitType" class="col-limit-type">
                    <select
                      class="cell-select"
                      :value="getEditValue(row, 'limit_type')"
                      @change="setEditValue(row, 'limit_type', $event.target.value || null)"
                    >
                      <option value="">--</option>
                      <option v-for="item in LIMIT_TYPES" :key="item" :value="item">{{ item }}</option>
                    </select>
                  </td>
                  <td v-if="previewVisibleColumns.exclude" class="col-bg">
                    <input
                      type="checkbox"
                      :checked="getEditValue(row, 'is_background')"
                      @change="setEditValue(row, 'is_background', $event.target.checked)"
                    />
                  </td>
                  <td v-if="previewVisibleColumns.status" class="col-status">
                    {{ row.preliminary_status ? complianceText(row.preliminary_status) : '-' }}
                    <small v-if="row.report_limit_value" class="subtle-line">
                      报告限值 {{ formatPreviewLimit(row) }}
                    </small>
                    <small v-if="row.preliminary_message" class="subtle-line">
                      {{ row.preliminary_message }}
                    </small>
                  </td>
                  <td v-if="previewVisibleColumns.confidence" class="col-conf">
                    <span :class="['conf-badge', confidenceClass(row)]">
                      {{ confidenceLabel(row) }}
                    </span>
                    <small class="subtle-line">{{ formatNumber(Number(row.confidence) * 100) }}%</small>
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
              将导入 {{ selectedImportCount }} 条（已勾选 {{ selectedPreviewCount }} 行）
              <template v-if="modifiedPreviewCount">
                ·
                <span class="modified-hint">已修改 {{ modifiedPreviewCount }} 行</span>
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
      <div class="task-filters detection-filters report-filters">
        <label class="filter-field">
          <span class="label-text">公司</span>
          <select v-if="session.isAdmin" v-model="organizationId">
            <option value="">全部公司</option>
            <option v-for="org in organizations" :key="org.id" :value="org.id">{{ org.name }}</option>
          </select>
          <input v-else :value="selectedOrgName || session.orgName || '默认公司'" disabled />
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
        <label class="filter-field">
          <span class="label-text">客户</span>
          <input v-model="reportClientNameFilter" type="search" placeholder="委托单位" @keydown.enter="applyReportFilters" />
        </label>
        <label class="filter-field">
          <span class="label-text">项目</span>
          <input v-model="reportProjectNameFilter" type="search" placeholder="项目名称" @keydown.enter="applyReportFilters" />
        </label>
        <label class="filter-field">
          <span class="label-text">项目编号</span>
          <input v-model="reportProjectCodeFilter" type="search" placeholder="编号" @keydown.enter="applyReportFilters" />
        </label>
        <label class="filter-field">
          <span class="label-text">报告类别</span>
          <select v-model="reportServiceTypeFilter" @change="applyReportFilters">
            <option value="">全部类别</option>
            <option v-for="item in DETECTION_SERVICE_TYPES" :key="item.value" :value="item.value">
              {{ item.label }}
            </option>
          </select>
        </label>
        <button type="button" class="btn-secondary filter-reset" @click="applyReportFilters">查询</button>
        <button type="button" class="btn-secondary filter-reset" @click="resetReportFilters">重置</button>
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
              <th>报告名称</th>
              <th>客户 / 项目</th>
              <th>报告类别</th>
              <th>状态</th>
              <th>报告日期</th>
              <th>创建时间</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!reports.length" class="empty-row">
              <td colspan="6">{{ reportsBusy ? '加载中...' : '暂无检测报告' }}</td>
            </tr>
            <tr v-for="report in reports" :key="report.id" @click="openReport(report.id)">
              <td>
                <span class="task-filename">{{ report.report_name || report.service_type || '检测报告' }}</span>
                <small v-if="report.report_date" class="subtle-line">检测日期 {{ report.report_date }}</small>
                <small v-else class="subtle-line">上传于 {{ formatTime(report.created_at) }}</small>
                <small class="subtle-line" style="color: var(--text-tertiary)">来源文件：{{ report.filename }}</small>
              </td>
              <td>
                <span v-if="report.client_name || report.project_name" class="task-filename">
                  {{ report.client_name || '-' }}
                </span>
                <small v-if="contextText(report)" class="subtle-line">{{ contextText(report) }}</small>
                <span v-else>-</span>
              </td>
              <td>{{ report.service_type || '-' }}</td>
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
          <h2>{{ activeReport?.report_name || activeReport?.filename || '报告详情' }}</h2>
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
              <dt>来源文件</dt>
              <dd>{{ activeReport.filename || '-' }}</dd>
              <dt>委托单位</dt>
              <dd>{{ activeReport.client_name || '-' }}</dd>
              <dt>项目名称</dt>
              <dd>{{ activeReport.project_name || '-' }}</dd>
              <dt>项目编号</dt>
              <dd>{{ activeReport.project_code || '-' }}</dd>
              <dt>报告类别</dt>
              <dd>{{ activeReport.service_type || '-' }}</dd>
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
              <button
                type="button"
                :class="['metric-tile', { active: resultStatusFilter === 'all' }]"
                @click="setResultFilter('all')"
              >
                <span>{{ resultSummary.total }}</span>
                <small>结果</small>
              </button>
              <button
                type="button"
                :class="['metric-tile', 'danger', { active: resultStatusFilter === 'EXCEEDED' }]"
                @click="setResultFilter('EXCEEDED')"
              >
                <span>{{ resultSummary.exceeded }}</span>
                <small>超标</small>
              </button>
              <button
                type="button"
                :class="['metric-tile', 'warn', { active: resultStatusFilter === 'BORDERLINE' }]"
                @click="setResultFilter('BORDERLINE')"
              >
                <span>{{ resultSummary.borderline }}</span>
                <small>临界</small>
              </button>
              <button
                type="button"
                :class="['metric-tile', 'info', { active: resultStatusFilter === 'review' }]"
                @click="setResultFilter('review')"
              >
                <span>{{ resultSummary.insufficient + resultSummary.needsReview }}</span>
                <small>待复核</small>
              </button>
              <button
                type="button"
                :class="['metric-tile', 'success', { active: resultStatusFilter === 'COMPLIANT' }]"
                @click="setResultFilter('COMPLIANT')"
              >
                <span>{{ resultSummary.compliant }}</span>
                <small>合规</small>
              </button>
            </div>

            <div class="detail-section">
              <div class="section-title-row">
                <h3>判定结果</h3>
                <span v-if="activeResults.length" class="result-count">{{ resultDisplayCountText }}</span>
              </div>
              <p v-if="!activeResults.length" class="empty-state compact">尚未运行合规判定</p>
              <template v-else>
                <div class="result-toolbar">
                  <select v-model="resultStatusFilter" class="result-filter">
                    <option v-for="item in RESULT_STATUS_FILTERS" :key="item.value" :value="item.value">
                      {{ item.label }}
                    </option>
                  </select>
                  <button
                    type="button"
                    class="btn-link-sm"
                    :disabled="!hiddenResultCount && !resultShowAll"
                    @click="resultShowAll = !resultShowAll"
                  >
                    {{ resultToggleText }}
                  </button>
                </div>
                <p v-if="!visibleActiveResults.length" class="empty-state compact">当前筛选下没有判定结果</p>
                <div v-else class="result-list">
                  <div v-for="result in visibleActiveResults" :key="result.id" class="result-row">
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
              </template>
            </div>

            <div class="detail-section">
              <h3>结构化数据</h3>
              <div v-for="sample in activeReport.samples" :key="sample.id" class="sample-block">
                <div class="sample-title">
                  <strong>{{ sample.sample_point }}</strong>
                  <span>{{ labelOf(MEDIUMS, sample.medium) }}</span>
                </div>
                <table class="mini-table measurement-table">
                  <thead>
                    <tr>
                      <th>因子</th>
                      <th>检测结果</th>
                    </tr>
                  </thead>
                  <tbody>
                    <tr v-for="measurement in sample.measurements" :key="measurement.id">
                      <td>{{ measurement.indicator_name }}</td>
                      <td>
                        <div class="measurement-values">
                          <span class="measurement-value-chip">
                            <strong>原始</strong>
                            <span>{{ formatNumber(measurement.raw_value) }} {{ measurement.raw_unit || '' }}</span>
                          </span>
                          <span class="measurement-value-chip normalized">
                            <strong>归一</strong>
                            <span>
                              {{ formatNumber(measurement.normalized_value) }}
                              {{ measurement.normalized_unit || '' }}
                            </span>
                          </span>
                        </div>
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
.detection-filters.report-filters {
  grid-template-columns: minmax(160px, 1.1fr) 140px 140px minmax(150px, 1fr) minmax(150px, 1fr) 120px 120px auto auto;
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
.preview-flow {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 10px;
  margin: 0 0 16px;
}
.preview-step {
  display: flex;
  align-items: center;
  gap: 9px;
  min-height: 42px;
  padding: 10px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-subtle);
  color: var(--text-secondary);
}
.preview-step span {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 22px;
  height: 22px;
  border-radius: 50%;
  background: var(--panel);
  color: var(--text-tertiary);
  font-size: 12px;
  font-weight: 800;
}
.preview-step strong {
  font-size: 13px;
}
.preview-step.active {
  border-color: var(--accent);
  background: var(--accent-bg);
  color: var(--text);
}
.preview-step.active span {
  background: var(--accent);
  color: #fff;
}
.preview-panel {
  display: grid;
  gap: 14px;
  margin-top: 18px;
  padding-top: 16px;
  border-top: 1px solid var(--border);
}
.preview-result-head {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 16px;
}
.preview-kicker {
  display: block;
  margin-bottom: 4px;
  color: var(--accent);
  font-size: 12px;
  font-weight: 800;
}
.preview-result-head h4 {
  margin: 0;
  font-size: 16px;
  line-height: 1.35;
  word-break: break-word;
}
.preview-result-head p {
  margin: 4px 0 0;
  color: var(--text-secondary);
  font-size: 13px;
}
.preview-result-actions {
  display: flex;
  flex-wrap: wrap;
  justify-content: flex-end;
  gap: 8px;
}
.preview-stat-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
}
.preview-stat {
  min-height: 66px;
  padding: 11px 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-subtle);
}
.preview-stat span {
  display: block;
  color: var(--text);
  font-size: 22px;
  font-weight: 800;
  line-height: 1;
  font-variant-numeric: tabular-nums;
}
.preview-stat small {
  display: block;
  margin-top: 8px;
  color: var(--text-secondary);
  font-size: 12px;
}
.preview-stat.strong span {
  color: var(--success);
}
.preview-stat.warn span {
  color: var(--warning);
}
.preview-stat.muted span {
  color: var(--text-tertiary);
}
.preview-warnings {
  border: 1px solid #fde68a;
  border-radius: 8px;
  background: #fffbeb;
  color: #92400e;
  font-size: 12px;
  overflow: hidden;
}
.preview-warnings summary {
  padding: 9px 12px;
  cursor: pointer;
  font-weight: 800;
}
.preview-warnings ul {
  display: grid;
  gap: 5px;
  margin: 0;
  padding: 0 12px 12px 28px;
}
.preview-table-wrap {
  max-height: 430px;
  overflow: auto;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel);
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
  position: sticky;
  bottom: 0;
  z-index: 3;
  margin-top: 8px;
  padding: 12px 0 0;
  background: var(--panel);
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
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: 8px;
  margin-bottom: 22px;
}
.metric-tile {
  appearance: none;
  text-align: left;
  font: inherit;
  min-width: 0;
  min-height: 72px;
  padding: 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--panel);
  cursor: pointer;
  transition: all var(--transition);
}
.metric-tile:hover {
  border-color: var(--accent);
  background: var(--accent-bg);
}
.metric-tile.active {
  border-color: var(--accent);
  box-shadow: inset 0 0 0 1px var(--accent);
}
.metric-tile span {
  display: block;
  color: var(--text);
  font-size: 22px;
  font-weight: 700;
  line-height: 1;
}
.metric-tile small {
  display: block;
  margin-top: 8px;
  color: var(--text-secondary);
  font-size: 11px;
  line-height: 1.2;
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
.metric-tile.success span {
  color: var(--success);
}
.section-title-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  margin-bottom: 10px;
}
.section-title-row h3 {
  margin-bottom: 0;
}
.result-count {
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
}
.result-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 10px;
  margin-bottom: 10px;
  padding: 9px 10px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--bg-subtle);
}
.result-filter {
  min-width: 160px;
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
.measurement-table {
  table-layout: fixed;
}
.measurement-table th:first-child,
.measurement-table td:first-child {
  width: 38%;
  font-weight: 600;
  color: var(--text);
  word-break: break-word;
}
.measurement-values {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 6px;
}
.measurement-value-chip {
  display: inline-flex;
  align-items: baseline;
  gap: 6px;
  min-height: 28px;
  padding: 4px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--panel);
  color: var(--text);
  line-height: 1.3;
}
.measurement-value-chip.normalized {
  background: var(--bg-subtle);
}
.measurement-value-chip strong {
  color: var(--text-tertiary);
  font-size: 11px;
  font-weight: 700;
}
.preview-edit-table thead th {
  position: sticky;
  top: 0;
  z-index: 2;
  background: var(--panel);
  box-shadow: inset 0 -1px 0 var(--border);
}
.empty-state.compact {
  padding: 22px 12px;
}

/* ---- 人工确认：工具栏 ---- */
.preview-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-height: 40px;
  padding: 9px 10px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-subtle);
}
.preview-toolbar-main {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 8px;
}
.preview-toggle {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  min-height: 28px;
  padding: 4px 8px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--panel);
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 700;
}
.btn-link-sm {
  min-height: 28px;
  padding: 4px 9px;
  border: 1px solid var(--border);
  border-radius: 6px;
  background: var(--panel);
  color: var(--accent);
  font-size: 12px;
  font-weight: 700;
  cursor: pointer;
  transition: all var(--transition);
}
.btn-link-sm:hover {
  background: var(--accent-bg);
  border-color: var(--accent);
}
.btn-link-sm:disabled {
  opacity: 0.45;
  cursor: not-allowed;
}
.preview-toolbar-count {
  color: var(--text-secondary);
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
}
.modified-hint {
  color: var(--warning);
}

/* ---- 预览编辑表格 ---- */
.preview-edit-table {
  min-width: 1100px;
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
  width: 116px;
  min-width: 116px;
}
.col-medium {
  width: 128px;
  min-width: 128px;
}
.col-indicator {
  width: 72px;
  min-width: 72px;
}
.col-value {
  width: 80px;
}
.col-unit {
  width: 92px;
  min-width: 92px;
}
.preview-edit-table .col-check,
.preview-edit-table .col-idx,
.preview-edit-table .col-point,
.preview-edit-table .col-indicator {
  position: sticky;
  background: var(--panel);
  z-index: 1;
}
.preview-edit-table thead .col-check,
.preview-edit-table thead .col-idx,
.preview-edit-table thead .col-point,
.preview-edit-table thead .col-indicator {
  z-index: 4;
}
.preview-edit-table .col-check {
  left: 0;
}
.preview-edit-table .col-idx {
  left: 32px;
}
.preview-edit-table .col-point {
  left: 72px;
  width: 116px;
  min-width: 116px;
}
.preview-edit-table .col-indicator {
  left: 188px;
  width: 72px;
  min-width: 72px;
}
.col-limit-type {
  width: 100px;
}
.col-bg {
  width: 44px;
  text-align: center;
}
.col-status {
  width: 124px;
  min-width: 124px;
}
.col-conf {
  width: 86px;
  text-align: center;
}

.cell-input {
  width: 100%;
  min-height: 30px;
  padding: 4px 6px;
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
  min-height: 30px;
  padding: 4px 6px;
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
.preview-edit-table tbody tr:hover {
  background: var(--bg-subtle);
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
  min-width: 54px;
  padding: 2px 7px;
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
  .limit-form-grid,
  .preview-stat-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .limit-basis {
    grid-column: span 2;
  }
  .preview-result-head {
    flex-direction: column;
  }
  .preview-result-actions {
    justify-content: flex-start;
  }
}

@media (max-width: 768px) {
  .detection-filters,
  .limit-form-grid,
  .result-row,
  .preview-flow,
  .preview-stat-grid {
    grid-template-columns: 1fr;
  }
  .limit-basis {
    grid-column: span 1;
  }
  .result-values {
    text-align: left;
  }
  .preview-toolbar,
  .result-toolbar,
  .preview-actions {
    align-items: stretch;
    flex-direction: column;
  }
  .section-title-row {
    align-items: flex-start;
    flex-direction: column;
  }
  .result-count {
    white-space: normal;
  }
  .result-filter {
    width: 100%;
  }
  .preview-toolbar-count,
  .preview-actions-hint {
    margin-right: 0;
    white-space: normal;
  }
}

/* ---- 上传须知指引 ---- */
.upload-guide {
  margin-bottom: 14px;
  border: 1px solid var(--border);
  border-radius: var(--radius);
  background: var(--bg-subtle);
  overflow: hidden;
}
.upload-guide summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  cursor: pointer;
  font-weight: 700;
  color: var(--text);
  background: var(--panel);
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
  color: var(--text-tertiary);
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
