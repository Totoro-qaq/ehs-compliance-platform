<script setup>
import { computed, onMounted, reactive, ref } from 'vue';
import {
  createOrganization,
  deleteOrganization,
  listOrganizations,
  updateOrganization,
} from '../api/organizations';
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

const showForm = ref(false);
const form = reactive({ id: '', name: '' });
const formTitle = computed(() => (form.id ? '编辑公司' : '新建公司'));
const orgCountText = computed(() => `${totalOrgs.value} 家公司`);

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
  form.id = '';
  form.name = '';
  showForm.value = true;
}

function openEdit(org) {
  form.id = org.id;
  form.name = org.name;
  showForm.value = true;
}

async function submitForm() {
  const name = form.name.trim();
  if (!name) return;
  try {
    if (form.id) {
      await updateOrganization(form.id, name);
      toast.show('公司已更新', 'success');
    } else {
      await createOrganization(name);
      toast.show('公司已创建', 'success');
    }
    showForm.value = false;
    await loadPage();
  } catch (err) {
    toast.show(formatApiError(err), 'error');
  }
}

async function removeOrg(org) {
  if (!confirm(`确认删除公司「${org.name}」？该公司下的用户和任务将被保留。`)) return;
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
          <label class="form-field">
            <span class="label-text">公司名称</span>
            <input v-model="form.name" required maxlength="255" placeholder="请输入公司名称" />
          </label>
          <div class="form-actions">
            <button type="button" class="btn-secondary" @click="showForm = false">取消</button>
            <button type="submit" class="btn-primary">保存</button>
          </div>
        </form>
      </div>
    </section>

    <section class="task-list-section">
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
              <th>公司 ID</th>
              <th>创建时间</th>
              <th style="width: 140px; text-align: right">操作</th>
            </tr>
          </thead>
          <tbody>
            <tr v-if="!orgs.length" class="empty-row">
              <td colspan="4">暂无公司数据</td>
            </tr>
            <tr v-for="org in orgs" :key="org.id">
              <td>
                <span class="task-filename">{{ org.name }}</span>
              </td>
              <td>
                <code style="font-size: 12px; color: var(--text-tertiary)">{{ org.id }}</code>
              </td>
              <td>{{ formatTime(org.created_at) }}</td>
              <td style="text-align: right">
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
  </div>
</template>
