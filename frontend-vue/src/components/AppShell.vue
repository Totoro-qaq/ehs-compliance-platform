<script setup>
import { useRouter, useRoute } from 'vue-router';
import { useSessionStore } from '../stores/session';
import { useToastStore } from '../stores/toast';
import Icon from './Icon.vue';

const session = useSessionStore();
const toast = useToastStore();
const router = useRouter();
const route = useRoute();

const navItems = [
  { view: 'home', label: '首页', icon: 'home' },
  { view: 'tasks', label: '评估任务', icon: 'clipboard' },
  { view: 'orgs', label: '公司管理', icon: 'building', adminOnly: true },
  { view: 'settings', label: '账户设置', icon: 'settings' },
];

function goto(view) {
  router.push({ name: view });
}

function logout() {
  session.clear();
  toast.show('已退出登录', 'info');
  router.replace({ name: 'login' });
}
</script>

<template>
  <div class="app-shell">
    <aside class="sidebar">
      <div class="sidebar-header">
        <div class="sidebar-brand">
          <svg width="24" height="24" viewBox="0 0 32 32" fill="none">
            <rect width="32" height="32" rx="8" fill="#d97706" />
            <path
              d="M8 16l5 5 11-11"
              stroke="#fff"
              stroke-width="3"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
          </svg>
          <span>EHS</span>
        </div>
      </div>
      <nav class="sidebar-nav">
        <button
          v-for="item in navItems.filter((nav) => !nav.adminOnly || session.isAdmin)"
          :key="item.view"
          type="button"
          :class="['nav-item', { active: route.name === item.view }]"
          @click="goto(item.view)"
        >
          <Icon :name="item.icon" />
          <span>{{ item.label }}</span>
        </button>
      </nav>
      <div class="sidebar-footer">
        <div class="user-avatar">{{ session.avatarInitial }}</div>
        <div class="user-info">
          <span class="user-name">{{ session.username }}</span>
          <span class="user-role">{{ session.roleText }}</span>
        </div>
        <button type="button" class="btn-icon-sm" title="退出登录" @click="logout">
          <Icon name="logout" :size="16" />
        </button>
      </div>
    </aside>
    <div class="main-wrapper">
      <slot />
    </div>
  </div>
</template>
