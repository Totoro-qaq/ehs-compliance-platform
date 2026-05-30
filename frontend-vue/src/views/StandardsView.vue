<script setup>
import { computed, onMounted, reactive, ref } from 'vue';
import { createStandardSource, listStandardSources, reviewStandardSource } from '../api/standards';
import { formatApiError } from '../api/client';
import Icon from '../components/Icon.vue';
import { useToastStore } from '../stores/toast';
import { formatTime } from '../utils/format';

const toast = useToastStore();

const SOURCE_TYPES = [
  { value: 'OFFICIAL_PUBLIC', label: '官方公开' },
  { value: 'AUTHORIZED_PURCHASE', label: '授权采购' },
  { value: 'CUSTOMER_PROVIDED', label: '客户提供' },
  { value: 'INTERNAL', label: '内部资料' },
];

const REVIEW_STATUSES = [
  { value: 'PENDING', label: '待审核' },
  { value: 'APPROVED', label: '已授权' },
  { value: 'REJECTED', label: '已拒绝' },
  { value: 'EXPIRED', label: '已过期' },
];

const PERMISSION_FIELDS = [
  { key: 'allow_storage', label: '允许存储', hint: '可入库存档' },
  { key: 'allow_vectorization', label: '允许向量化', hint: '可生成索引' },
  { key: 'allow_ai_retrieval', label: '允许 AI 检索', hint: '可参与回答' },
  { key: 'allow_excerpt_export', label: '允许摘录导出', hint: '可进入报告' },
];

const sources = ref([]);
const loading = ref(false);
const showCreateForm = ref(false);
const activeSource = ref(null);
const reviewBusy = ref(false);
const filters = reactive({
  reviewStatus: '',
  sourceType: '',
});

const createForm = reactive({
  source_name: '',
  source_type: 'CUSTOMER_PROVIDED',
  provider_name: '',
  license_no: '',
  license_scope: '',
  organization_id: '',
  allow_storage: false,
  allow_vectorization: false,
  allow_ai_retrieval: false,
  allow_excerpt_export: false,
  effective_from: '',
  effective_to: '',
  notes: '',
});

const reviewForm = reactive({
  review_status: 'PENDING',
  allow_storage: false,
  allow_vectorization: false,
  allow_ai_retrieval: false,
  allow_excerpt_export: false,
  effective_from: '',
  effective_to: '',
  notes: '',
});

const sourceCountText = computed(() => `${sources.value.length} 条来源授权`);
const approvedCount = computed(
  () => sources.value.filter((item) => item.review_status === 'APPROVED').length,
);
const aiRetrievalCount = computed(() => sources.value.filter((item) => item.allow_ai_retrieval).length);
const exportAllowedCount = computed(() => sources.value.filter((item) => item.allow_excerpt_export).length);
const activeSourceTitle = computed(() => activeSource.value?.source_name || '来源审批');

function optionLabel(options, value) {
  return options.find((item) => item.value === value)?.label || value || '-';
}

function sourceTypeLabel(value) {
  return optionLabel(SOURCE_TYPES, value);
}

function reviewStatusLabel(value) {
  return optionLabel(REVIEW_STATUSES, value);
}

function yesNo(value) {
  return value ? '是' : '否';
}

function toNullableText(value) {
  const text = String(value || '').trim();
  return text || null;
}

function toNullableDate(value) {
  return value || null;
}

function resetCreateForm() {
  createForm.source_name = '';
  createForm.source_type = 'CUSTOMER_PROVIDED';
  createForm.provider_name = '';
  createForm.license_no = '';
  createForm.license_scope = '';
  createForm.organization_id = '';
  createForm.allow_storage = false;
  createForm.allow_vectorization = false;
  createForm.allow_ai_retrieval = false;
  createForm.allow_excerpt_export = false;
  createForm.effective_from = '';
  createForm.effective_to = '';
  createForm.notes = '';
}

function createPayload() {
  return {
    source_name: createForm.source_name.trim(),
    source_type: createForm.source_type,
    provider_name: toNullableText(createForm.provider_name),
    license_no: toNullableText(createForm.license_no),
    license_scope: toNullableText(createForm.license_scope),
    organization_id: toNullableText(createForm.organization_id),
    allow_storage: createForm.allow_storage,
    allow_vectorization: createForm.allow_vectorization,
    allow_ai_retrieval: createForm.allow_ai_retrieval,
    allow_excerpt_export: createForm.allow_excerpt_export,
    effective_from: toNullableDate(createForm.effective_from),
    effective_to: toNullableDate(createForm.effective_to),
    notes: toNullableText(createForm.notes),
  };
}

function reviewPayload() {
  return {
    review_status: reviewForm.review_status,
    allow_storage: reviewForm.allow_storage,
    allow_vectorization: reviewForm.allow_vectorization,
    allow_ai_retrieval: reviewForm.allow_ai_retrieval,
    allow_excerpt_export: reviewForm.allow_excerpt_export,
    effective_from: toNullableDate(reviewForm.effective_from),
    effective_to: toNullableDate(reviewForm.effective_to),
    notes: toNullableText(reviewForm.notes),
  };
}

function openCreate() {
  resetCreateForm();
  showCreateForm.value = true;
}

function closeCreate() {
  showCreateForm.value = false;
}

function fillReviewForm(source) {
  reviewForm.review_status = source.review_status || 'PENDING';
  reviewForm.allow_storage = Boolean(source.allow_storage);
  reviewForm.allow_vectorization = Boolean(source.allow_vectorization);
  reviewForm.allow_ai_retrieval = Boolean(source.allow_ai_retrieval);
  reviewForm.allow_excerpt_export = Boolean(source.allow_excerpt_export);
  reviewForm.effective_from = source.effective_from || '';
  reviewForm.effective_to = source.effective_to || '';
  reviewForm.notes = source.notes || '';
}

function openReview(source) {
  activeSource.value = source;
  fillReviewForm(source);
}

function closeReview() {
  activeSource.value = null;
}

async function loadSources({ quiet = false } = {}) {
  loading.value = true;
  try {
    sources.value = await listStandardSources({
      reviewStatus: filters.reviewStatus,
      sourceType: filters.sourceType,
      limit: 200,
    });
    if (!quiet) toast.show('已刷新', 'success');
  } catch (err) {
    toast.show(formatApiError(err), 'error');
  } finally {
    loading.value = false;
  }
}

async function submitCreate() {
  const payload = createPayload();
  if (!payload.source_name) {
    toast.show('来源名称不能为空', 'error');
    return;
  }
  try {
    await createStandardSource(payload);
    toast.show('来源已创建', 'success');
    showCreateForm.value = false;
    await loadSources({ quiet: true });
  } catch (err) {
    toast.show(formatApiError(err), 'error');
  }
}

async function submitReview() {
  if (!activeSource.value?.id || reviewBusy.value) return;
  reviewBusy.value = true;
  try {
    await reviewStandardSource(activeSource.value.id, reviewPayload());
    toast.show('审批已保存', 'success');
    await loadSources({ quiet: true });
    const updated = sources.value.find((item) => item.id === activeSource.value.id);
    if (updated) {
      activeSource.value = updated;
      fillReviewForm(updated);
    }
  } catch (err) {
    toast.show(formatApiError(err), 'error');
  } finally {
    reviewBusy.value = false;
  }
}

function resetFilters() {
  filters.reviewStatus = '';
  filters.sourceType = '';
  loadSources({ quiet: true });
}

onMounted(() => loadSources({ quiet: true }));
</script>

<template>
  <div class="view-container standards-view">
    <header class="view-header">
      <div>
        <h1>标准来源授权</h1>
        <p class="view-desc">管理标准、导则、客户资料的存储、检索和报告摘录权限</p>
      </div>
      <div class="header-actions">
        <button type="button" class="btn-secondary" :disabled="loading" @click="loadSources()">
          <Icon name="refresh" :size="14" />
          刷新
        </button>
        <button type="button" class="btn-primary" @click="openCreate">
          <Icon name="plus" :size="14" />
          新建来源
        </button>
      </div>
    </header>

    <section v-if="showCreateForm" class="upload-panel">
      <div class="upload-panel-inner">
        <h3>新建来源授权</h3>
        <p>先登记授权边界，再导入标准 manifest；未审批通过的来源不会进入 AI 检索。</p>
        <form class="settings-form" @submit.prevent="submitCreate">
          <div class="form-row standards-form-row">
            <label class="form-field">
              <span class="label-text">来源名称</span>
              <input
                v-model="createForm.source_name"
                required
                maxlength="255"
                placeholder="如：GBZ 授权采购批次"
              />
            </label>
            <label class="form-field">
              <span class="label-text">来源类型</span>
              <select v-model="createForm.source_type">
                <option v-for="type in SOURCE_TYPES" :key="type.value" :value="type.value">
                  {{ type.label }}
                </option>
              </select>
            </label>
            <label class="form-field">
              <span class="label-text">提供方</span>
              <input v-model="createForm.provider_name" maxlength="255" placeholder="可选" />
            </label>
            <label class="form-field">
              <span class="label-text">授权编号</span>
              <input v-model="createForm.license_no" maxlength="128" placeholder="可选" />
            </label>
            <label class="form-field">
              <span class="label-text">公司 ID</span>
              <input
                v-model="createForm.organization_id"
                maxlength="36"
                placeholder="客户资料需绑定公司，可选"
              />
            </label>
            <label class="form-field">
              <span class="label-text">有效期起</span>
              <input v-model="createForm.effective_from" type="date" />
            </label>
            <label class="form-field">
              <span class="label-text">有效期止</span>
              <input v-model="createForm.effective_to" type="date" />
            </label>
            <label class="form-field">
              <span class="label-text">授权范围</span>
              <input v-model="createForm.license_scope" placeholder="如：仅内部评价报告使用" />
            </label>
          </div>
          <div class="permission-grid">
            <label v-for="field in PERMISSION_FIELDS" :key="field.key" class="permission-toggle">
              <input v-model="createForm[field.key]" type="checkbox" />
              <span>
                <strong>{{ field.label }}</strong>
                <small>{{ field.hint }}</small>
              </span>
            </label>
          </div>
          <label class="form-field">
            <span class="label-text">备注</span>
            <textarea
              v-model="createForm.notes"
              rows="3"
              maxlength="1000"
              placeholder="记录合同、采购、客户授权或限制条件"
            />
          </label>
          <div class="form-actions">
            <button type="button" class="btn-secondary" @click="closeCreate">取消</button>
            <button type="submit" class="btn-primary">保存</button>
          </div>
        </form>
      </div>
    </section>

    <section class="source-kpis">
      <div>
        <strong>{{ sources.length }}</strong>
        <span>当前列表</span>
      </div>
      <div>
        <strong>{{ approvedCount }}</strong>
        <span>已授权</span>
      </div>
      <div>
        <strong>{{ aiRetrievalCount }}</strong>
        <span>允许 AI 检索</span>
      </div>
      <div>
        <strong>{{ exportAllowedCount }}</strong>
        <span>允许报告摘录</span>
      </div>
    </section>

    <section class="task-list-section">
      <div class="task-filters standards-filters">
        <label class="filter-field">
          <span class="label-text">审批状态</span>
          <select v-model="filters.reviewStatus" @change="loadSources({ quiet: true })">
            <option value="">全部状态</option>
            <option v-for="status in REVIEW_STATUSES" :key="status.value" :value="status.value">
              {{ status.label }}
            </option>
          </select>
        </label>
        <label class="filter-field">
          <span class="label-text">来源类型</span>
          <select v-model="filters.sourceType" @change="loadSources({ quiet: true })">
            <option value="">全部类型</option>
            <option v-for="type in SOURCE_TYPES" :key="type.value" :value="type.value">
              {{ type.label }}
            </option>
          </select>
        </label>
        <button type="button" class="btn-secondary filter-reset" @click="resetFilters">重置</button>
      </div>
      <div class="task-list-header">
        <span class="task-count">{{ sourceCountText }}</span>
        <span v-if="loading" class="task-count">加载中...</span>
      </div>
      <div class="task-table-wrap">
        <table class="task-table standards-table">
          <thead>
            <tr>
              <th>来源</th>
              <th>类型</th>
              <th>授权</th>
              <th>AI</th>
              <th>导出</th>
              <th>有效期</th>
              <th>更新</th>
              <th style="width: 96px; text-align: right">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!sources.length" class="empty-row">
              <td colspan="8">{{ loading ? '加载中...' : '暂无来源授权记录' }}</td>
            </tr>
            <tr v-for="source in sources" :key="source.id">
              <td>
                <span class="task-filename">{{ source.source_name }}</span>
                <small class="subtle-line">
                  {{ source.provider_name || source.license_no || source.id }}
                </small>
              </td>
              <td>{{ sourceTypeLabel(source.source_type) }}</td>
              <td>
                <span :class="['status-badge', source.review_status]">
                  {{ reviewStatusLabel(source.review_status) }}
                </span>
              </td>
              <td>{{ yesNo(source.allow_ai_retrieval) }}</td>
              <td>{{ yesNo(source.allow_excerpt_export) }}</td>
              <td>{{ source.effective_from || '-' }} / {{ source.effective_to || '-' }}</td>
              <td>{{ formatTime(source.updated_at) }}</td>
              <td style="text-align: right">
                <button class="btn-icon-sm" title="审批" @click="openReview(source)">
                  <Icon name="edit" :size="14" />
                </button>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <Transition name="drawer">
      <aside v-if="activeSource" class="task-drawer open">
        <div class="drawer-header">
          <h2>{{ activeSourceTitle }}</h2>
          <div class="drawer-actions">
            <button type="button" class="btn-icon-sm" @click="closeReview">
              <Icon name="close" />
            </button>
          </div>
        </div>
        <div class="drawer-body">
          <dl class="detail-meta">
            <dt>来源 ID</dt>
            <dd>{{ activeSource.id }}</dd>
            <dt>来源类型</dt>
            <dd>{{ sourceTypeLabel(activeSource.source_type) }}</dd>
            <dt>提供方</dt>
            <dd>{{ activeSource.provider_name || '-' }}</dd>
            <dt>授权编号</dt>
            <dd>{{ activeSource.license_no || '-' }}</dd>
            <dt>公司 ID</dt>
            <dd>{{ activeSource.organization_id || '-' }}</dd>
            <dt>创建时间</dt>
            <dd>{{ formatTime(activeSource.created_at) }}</dd>
          </dl>

          <form class="settings-form" @submit.prevent="submitReview">
            <label class="form-field">
              <span class="label-text">审批状态</span>
              <select v-model="reviewForm.review_status">
                <option v-for="status in REVIEW_STATUSES" :key="status.value" :value="status.value">
                  {{ status.label }}
                </option>
              </select>
            </label>
            <div class="permission-grid drawer-permissions">
              <label v-for="field in PERMISSION_FIELDS" :key="field.key" class="permission-toggle">
                <input v-model="reviewForm[field.key]" type="checkbox" />
                <span>
                  <strong>{{ field.label }}</strong>
                  <small>{{ field.hint }}</small>
                </span>
              </label>
            </div>
            <div class="form-row">
              <label class="form-field">
                <span class="label-text">有效期起</span>
                <input v-model="reviewForm.effective_from" type="date" />
              </label>
              <label class="form-field">
                <span class="label-text">有效期止</span>
                <input v-model="reviewForm.effective_to" type="date" />
              </label>
            </div>
            <label class="form-field">
              <span class="label-text">审批备注</span>
              <textarea
                v-model="reviewForm.notes"
                rows="4"
                maxlength="1000"
                placeholder="记录审核依据、限制条件或拒绝原因"
              />
            </label>
            <div class="form-actions">
              <button type="button" class="btn-secondary" @click="closeReview">关闭</button>
              <button type="submit" class="btn-primary" :disabled="reviewBusy">
                <Icon name="save" :size="14" />
                保存审批
              </button>
            </div>
          </form>
        </div>
      </aside>
    </Transition>
  </div>
</template>

<style scoped>
.standards-view {
  max-width: 1440px;
}

.standards-form-row {
  grid-template-columns: repeat(4, minmax(0, 1fr));
}

.standards-filters {
  grid-template-columns: minmax(180px, 240px) minmax(180px, 240px) auto;
}

.source-kpis {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin-bottom: 20px;
}

.source-kpis div {
  min-height: 76px;
  padding: 14px 16px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--panel);
}

.source-kpis strong,
.source-kpis span {
  display: block;
}

.source-kpis strong {
  font-size: 24px;
  line-height: 1;
}

.source-kpis span {
  margin-top: 8px;
  color: var(--text-secondary);
  font-size: 13px;
}

.permission-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 10px;
  margin-bottom: 16px;
}

.permission-toggle {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  min-height: 66px;
  padding: 12px;
  border: 1px solid var(--border);
  border-radius: 8px;
  background: var(--bg-subtle);
}

.permission-toggle input {
  width: 16px;
  height: 16px;
  margin-top: 2px;
  flex: 0 0 auto;
}

.permission-toggle strong,
.permission-toggle small {
  display: block;
}

.permission-toggle strong {
  color: var(--text);
  font-size: 13px;
}

.permission-toggle small {
  margin-top: 4px;
  color: var(--text-tertiary);
  font-size: 12px;
  line-height: 1.45;
}

.drawer-permissions {
  grid-template-columns: 1fr 1fr;
}

.standards-table th,
.standards-table td {
  white-space: nowrap;
}

.status-badge.APPROVED {
  background: var(--success-bg);
  color: var(--success);
}

.status-badge.APPROVED::before {
  background: var(--success);
}

.status-badge.REJECTED,
.status-badge.EXPIRED {
  background: var(--danger-bg);
  color: var(--danger);
}

.status-badge.REJECTED::before,
.status-badge.EXPIRED::before {
  background: var(--danger);
}

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

@media (max-width: 1024px) {
  .standards-form-row,
  .source-kpis,
  .permission-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}

@media (max-width: 640px) {
  .standards-filters,
  .standards-form-row,
  .source-kpis,
  .permission-grid,
  .drawer-permissions {
    grid-template-columns: 1fr;
  }
}
</style>
