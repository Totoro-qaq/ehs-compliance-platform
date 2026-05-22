<script setup>
import { computed, onMounted, reactive, ref } from 'vue';
import {
  createOrganization,
  deleteOrganization,
  listOrganizations,
  updateOrganization,
} from '../api/organizations';
import { listTasks } from '../api/assessment';
import { listDetectionReports } from '../api/detection';
import { formatApiError } from '../api/client';
import { useSessionStore } from '../stores/session';
import { useToastStore } from '../stores/toast';
import { formatTime } from '../utils/format';
import Icon from '../components/Icon.vue';

const session = useSessionStore();
const toast = useToastStore();

const orgs = ref([]);
const totalOrgs = ref(0);
const totalPages = ref(0);
const page = ref(1);
const pageSize = 15;
const orgSearch = ref('');
const overviewOpen = ref(false);
const overviewBusy = ref(false);
const activeOrg = ref(null);
const orgTasks = ref([]);
const orgReports = ref([]);
const orgTaskTotal = ref(0);
const orgReportTotal = ref(0);

const showForm = ref(false);
const form = reactive({
  id: '',
  name: '',
  unified_social_credit_code: '',
  industry: '',
  address: '',
  contact_name: '',
  contact_phone: '',
  notes: '',
});
const formTitle = computed(() => (form.id ? '编辑公司' : '新建公司'));
const orgCountText = computed(() => `${totalOrgs.value} 家公司`);
const filteredOrgs = computed(() => {
  const q = orgSearch.value.trim().toLowerCase();
  if (!q) return orgs.value;
  return orgs.value.filter((org) => org.name?.toLowerCase().includes(q) || org.id?.toLowerCase().includes(q));
});
const orgOverviewTitle = computed(() => activeOrg.value?.name || '公司概览');

async function loadPage() {
  try {
    const data = await listOrganizations(page.value, pageSize);
    orgs.value = data?.items || [];
    totalOrgs.value = data?.total || 0;
    totalPages.value = data?.pages || 1;
  } catch (err) {
    toast.show(formatApiError(err), 'error');
  }
}

async function refresh() {
  await loadPage();
  toast.show('已刷新', 'success');
}

function openCreate() {
  if (!session.isAdmin) {
    toast.show('仅管理员可创建公司', 'error');
    return;
  }
  resetForm();
  showForm.value = true;
}

function openEdit(org) {
  form.id = org.id;
  form.name = org.name || '';
  form.unified_social_credit_code = org.unified_social_credit_code || '';
  form.industry = org.industry || '';
  form.address = org.address || '';
  form.contact_name = org.contact_name || '';
  form.contact_phone = org.contact_phone || '';
  form.notes = org.notes || '';
  showForm.value = true;
}

function resetForm() {
  form.id = '';
  form.name = '';
  form.unified_social_credit_code = '';
  form.industry = '';
  form.address = '';
  form.contact_name = '';
  form.contact_phone = '';
  form.notes = '';
}

function formPayload() {
  return {
    name: form.name.trim(),
    unified_social_credit_code: form.unified_social_credit_code.trim() || null,
    industry: form.industry.trim() || null,
    address: form.address.trim() || null,
    contact_name: form.contact_name.trim() || null,
    contact_phone: form.contact_phone.trim() || null,
    notes: form.notes.trim() || null,
  };
}

async function openOverview(org) {
  activeOrg.value = org;
  overviewOpen.value = true;
  overviewBusy.value = true;
  try {
    const [tasks, reports] = await Promise.all([
      listTasks(1, 5, { organizationId: org.id }),
      listDetectionReports(1, 5, { organizationId: org.id }),
    ]);
    orgTasks.value = tasks?.items || [];
    orgReports.value = reports?.items || [];
    orgTaskTotal.value = tasks?.total || 0;
    orgReportTotal.value = reports?.total || 0;
  } catch (err) {
    toast.show(formatApiError(err), 'error');
  } finally {
    overviewBusy.value = false;
  }
}

function closeOverview() {
  overviewOpen.value = false;
  activeOrg.value = null;
  orgTasks.value = [];
  orgReports.value = [];
  orgTaskTotal.value = 0;
  orgReportTotal.value = 0;
}

async function submitForm() {
  const payload = formPayload();
  if (!payload.name) return;
  try {
    if (form.id) {
      await updateOrganization(form.id, payload);
      toast.show('公司已更新', 'success');
    } else {
      await createOrganization(payload);
      toast.show('公司已创建', 'success');
    }
    showForm.value = false;
    await loadPage();
  } catch (err) {
    toast.show(formatApiError(err), 'error');
  }
}

async function removeOrg(org) {
  if (!confirm(`确认删除公司「${org.name}」？\n该公司下的用户和任务将被保留，但新任务不能再选择该公司。`)) return;
  try {
    await deleteOrganization(org.id);
    toast.show('公司已删除', 'success');
    if (orgs.value.length === 1 && page.value > 1) {
      page.value -= 1;
    }
    await loadPage();
  } catch (err) {
    toast.show(formatApiError(err), 'error');
  }
}

function gotoPage(p) {
  if (p < 1 || p > totalPages.value) return;
  page.value = p;
  loadPage();
}

onMounted(loadPage);
</script>

<template>
  <div class="view-container">
    <header class="view-header">
      <div>
        <h1>公司管理</h1>
        <p class="view-desc">管理企业组织信息（仅管理员可创建/修改）</p>
      </div>
      <div class="header-actions">
        <button type="button" class="btn-secondary" @click="refresh">
          <Icon name="refresh" :size="14" />
          刷新
        </button>
        <button type="button" class="btn-primary" @click="openCreate">
          <Icon name="plus" :size="14" />
          新建公司
        </button>
      </div>
    </header>

    <section v-if="showForm" class="upload-panel">
      <div class="upload-panel-inner">
        <h3>{{ formTitle }}</h3>
        <form class="settings-form" @submit.prevent="submitForm">
          <div class="form-row">
            <label class="form-field">
              <span class="label-text">公司名称</span>
              <input v-model="form.name" required maxlength="255" placeholder="请输入公司名称" />
            </label>
            <label class="form-field">
              <span class="label-text">统一社会信用代码</span>
              <input v-model="form.unified_social_credit_code" maxlength="32" placeholder="可选" />
            </label>
            <label class="form-field">
              <span class="label-text">所属行业</span>
              <input v-model="form.industry" maxlength="128" placeholder="如：制造业 / 化工 / 电子" />
            </label>
            <label class="form-field">
              <span class="label-text">联系人</span>
              <input v-model="form.contact_name" maxlength="64" placeholder="客户联系人" />
            </label>
            <label class="form-field">
              <span class="label-text">联系电话</span>
              <input v-model="form.contact_phone" maxlength="32" placeholder="客户联系电话" />
            </label>
            <label class="form-field">
              <span class="label-text">注册地址 / 经营地址</span>
              <input v-model="form.address" maxlength="500" placeholder="公司地址" />
            </label>
          </div>
          <label class="form-field">
            <span class="label-text">备注</span>
            <input v-model="form.notes" maxlength="1000" placeholder="客户侧补充信息，可选" />
          </label>
          <div class="form-actions">
            <button type="button" class="btn-secondary" @click="showForm = false">取消</button>
            <button type="submit" class="btn-primary">保存</button>
          </div>
        </form>
      </div>
    </section>

    <section class="task-list-section">
      <div class="org-overview">
        <div class="org-overview-card">
          <span>{{ totalOrgs }}</span>
          <small>公司总数</small>
        </div>
        <label class="filter-field org-search">
          <span class="label-text">搜索公司</span>
          <input v-model="orgSearch" type="search" placeholder="公司名称或 ID" />
        </label>
      </div>
      <div class="task-list-header">
        <span class="task-count">{{ orgCountText }}</span>
        <div class="pagination">
          <template v-if="totalPages > 1">
            <button class="page-btn" :disabled="page <= 1" @click="gotoPage(page - 1)">&lt;</button>
            <span class="page-info">{{ page }} / {{ totalPages }}</span>
            <button class="page-btn" :disabled="page >= totalPages" @click="gotoPage(page + 1)">&gt;</button>
          </template>
        </div>
      </div>
      <div class="task-table-wrap">
        <table class="task-table">
          <thead>
            <tr>
              <th>公司名称</th>
              <th>行业</th>
              <th>联系人</th>
              <th>公司 ID</th>
              <th>创建时间</th>
              <th style="width: 190px; text-align: right">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!filteredOrgs.length" class="empty-row">
              <td colspan="6">暂无公司数据</td>
            </tr>
            <tr v-for="org in filteredOrgs" :key="org.id">
              <td>
                <span class="task-filename">{{ org.name }}</span>
                <small v-if="org.unified_social_credit_code" class="subtle-line">{{
                  org.unified_social_credit_code
                }}</small>
              </td>
              <td>{{ org.industry || '-' }}</td>
              <td>
                {{ org.contact_name || '-' }}
                <small v-if="org.contact_phone" class="subtle-line">{{ org.contact_phone }}</small>
              </td>
              <td>
                <code style="font-size: 12px; color: var(--text-tertiary)">{{ org.id }}</code>
              </td>
              <td>{{ formatTime(org.created_at) }}</td>
              <td style="text-align: right">
                <button class="btn-icon-sm" title="概览" @click="openOverview(org)">
                  <Icon name="database" :size="14" />
                </button>
                <template v-if="session.isAdmin">
                  <button class="btn-icon-sm" title="编辑" @click="openEdit(org)">
                    <Icon name="edit" :size="14" />
                  </button>
                  <button
                    class="btn-icon-sm"
                    title="删除"
                    style="color: var(--danger)"
                    @click="removeOrg(org)"
                  >
                    <Icon name="trash" :size="14" />
                  </button>
                </template>
                <span v-else style="color: var(--text-tertiary); font-size: 12px">无权限</span>
              </td>
            </tr>
          </tbody>
        </table>
      </div>
    </section>

    <Transition name="drawer">
      <aside v-if="overviewOpen" class="task-drawer open">
        <div class="drawer-header">
          <h2>{{ orgOverviewTitle }}</h2>
          <div class="drawer-actions">
            <button type="button" class="btn-icon-sm" @click="closeOverview">
              <Icon name="close" />
            </button>
          </div>
        </div>
        <div class="drawer-body">
          <template v-if="activeOrg">
            <dl class="detail-meta">
              <dt>公司 ID</dt>
              <dd>{{ activeOrg.id }}</dd>
              <dt>信用代码</dt>
              <dd>{{ activeOrg.unified_social_credit_code || '-' }}</dd>
              <dt>所属行业</dt>
              <dd>{{ activeOrg.industry || '-' }}</dd>
              <dt>公司地址</dt>
              <dd>{{ activeOrg.address || '-' }}</dd>
              <dt>联系人</dt>
              <dd>{{ activeOrg.contact_name || '-' }}</dd>
              <dt>联系电话</dt>
              <dd>{{ activeOrg.contact_phone || '-' }}</dd>
              <dt>创建时间</dt>
              <dd>{{ formatTime(activeOrg.created_at) }}</dd>
              <dt>评价任务</dt>
              <dd>{{ orgTaskTotal }}</dd>
              <dt>检测报告</dt>
              <dd>{{ orgReportTotal }}</dd>
              <dt>备注</dt>
              <dd>{{ activeOrg.notes || '-' }}</dd>
            </dl>
            <div v-if="overviewBusy" class="empty-state compact">加载中...</div>
            <template v-else>
              <div class="detail-section">
                <h3>最近评价任务</h3>
                <p v-if="!orgTasks.length" class="empty-state compact">暂无评价任务</p>
                <div v-else class="result-list">
                  <div v-for="task in orgTasks" :key="task.task_id" class="result-row org-overview-row">
                    <div>
                      <strong>{{ task.task_name || task.filename || task.task_id }}</strong>
                      <small>{{ formatTime(task.created_at) }}</small>
                    </div>
                    <span :class="['status-badge', task.status || '']">{{ task.status }}</span>
                  </div>
                </div>
              </div>
              <div class="detail-section">
                <h3>最近检测报告</h3>
                <p v-if="!orgReports.length" class="empty-state compact">暂无检测报告</p>
                <div v-else class="result-list">
                  <div v-for="report in orgReports" :key="report.id" class="result-row org-overview-row">
                    <div>
                      <strong>{{ report.report_name || report.filename || report.id }}</strong>
                      <small>{{ formatTime(report.created_at) }}</small>
                    </div>
                    <span :class="['status-badge', report.status || '']">{{ report.status }}</span>
                  </div>
                </div>
              </div>
            </template>
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
.org-overview-row {
  grid-template-columns: minmax(0, 1fr) auto;
}
</style>
