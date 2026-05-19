<script setup>
import { reactive } from 'vue';
import { useRouter } from 'vue-router';
import { changePassword } from '../api/auth';
import { formatApiError } from '../api/client';
import { useSessionStore } from '../stores/session';
import { useToastStore } from '../stores/toast';

const session = useSessionStore();
const toast = useToastStore();
const router = useRouter();

const pwd = reactive({ old: '', next: '', confirm: '' });

async function submitPassword() {
  if (pwd.next !== pwd.confirm) {
    toast.show('两次输入的新密码不一致', 'error');
    return;
  }
  try {
    await changePassword(pwd.old, pwd.next);
    pwd.old = '';
    pwd.next = '';
    pwd.confirm = '';
    toast.show('密码修改成功，请使用新密码重新登录', 'success');
    setTimeout(() => {
      session.clear();
      router.replace({ name: 'login' });
    }, 1500);
  } catch (err) {
    toast.show(formatApiError(err), 'error');
  }
}

function logout() {
  session.clear();
  toast.show('已退出登录', 'info');
  router.replace({ name: 'login' });
}
</script>

<template>
  <div class="view-container">
    <header class="view-header">
      <div>
        <h1>账户设置</h1>
        <p class="view-desc">管理您的个人信息和安全设置</p>
      </div>
    </header>

    <div class="settings-grid">
      <section class="settings-card">
        <div class="settings-card-header"><h3>个人信息</h3></div>
        <div class="settings-card-body">
          <div class="profile-info">
            <div class="profile-avatar">{{ session.avatarInitial }}</div>
            <div class="profile-fields">
              <div class="field-row">
                <span class="field-label">用户名</span
                ><span class="field-value">{{ session.username || '-' }}</span>
              </div>
              <div class="field-row">
                <span class="field-label">角色</span><span class="field-value">{{ session.roleText }}</span>
              </div>
              <div class="field-row">
                <span class="field-label">所属公司</span
                ><span class="field-value">{{ session.orgName || '默认组织' }}</span>
              </div>
            </div>
          </div>
        </div>
      </section>

      <section class="settings-card">
        <div class="settings-card-header">
          <h3>安全设置</h3>
          <span class="settings-badge">密码认证</span>
        </div>
        <div class="settings-card-body">
          <form class="settings-form" @submit.prevent="submitPassword">
            <label class="form-field"
              ><span class="label-text">当前密码</span
              ><input v-model="pwd.old" type="password" autocomplete="current-password" required
            /></label>
            <label class="form-field"
              ><span class="label-text">新密码</span
              ><input
                v-model="pwd.next"
                type="password"
                autocomplete="new-password"
                required
                placeholder="8位以上，含大小写字母和数字"
            /></label>
            <label class="form-field"
              ><span class="label-text">确认新密码</span
              ><input v-model="pwd.confirm" type="password" autocomplete="new-password" required
            /></label>
            <div class="form-actions"><button type="submit" class="btn-primary">更新密码</button></div>
          </form>
        </div>
      </section>

      <section class="settings-card">
        <div class="settings-card-header"><h3>会话管理</h3></div>
        <div class="settings-card-body">
          <div class="session-info">
            <div class="field-row">
              <span class="field-label">登录状态</span><span class="field-value session-active">已登录</span>
            </div>
            <div class="field-row">
              <span class="field-label">令牌有效期</span><span class="field-value">1 小时</span>
            </div>
          </div>
          <button type="button" class="btn-danger-ghost btn-full" @click="logout">退出当前会话</button>
        </div>
      </section>
    </div>
  </div>
</template>
