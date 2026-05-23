<script setup>
import { computed, onMounted, onUnmounted, ref } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { useSessionStore } from '../stores/session';
import { useToastStore } from '../stores/toast';
import Icon from './Icon.vue';
import AppFooter from './AppFooter.vue';

const session = useSessionStore();
const toast = useToastStore();
const router = useRouter();
const route = useRoute();

const RELEASES_URL = 'https://github.com/Totoro-qaq/ehs-compliance-platform/releases';

const navItems = computed(() => {
  if (!session.token) {
    return [
      { key: 'home', label: '首页', view: 'home' },
      { key: 'release', label: '版本', external: RELEASES_URL },
    ];
  }
  return [
    { key: 'home', label: '首页', view: 'home', query: { view: 'home' } },
    { key: 'workbench', label: '工作台', view: 'home', query: { view: 'workbench' } },
    { key: 'tasks', label: '评价任务', view: 'tasks' },
    { key: 'detection', label: '检测合规', view: 'detection' },
    { key: 'agent', label: 'AI 助手', view: 'agent' },
  ];
});

const userMenuOpen = ref(false);

function onNavClick(item) {
  if (item.external) {
    window.open(item.external, '_blank', 'noopener');
    return;
  }
  if (item.view) {
    router.push({ name: item.view, query: item.query });
  }
}

function isNavActive(item) {
  if (!item.view || route.name !== item.view) return false;
  if (item.key === 'home' && session.token) return route.query.view !== 'workbench';
  if (item.key === 'workbench') return route.query.view === 'workbench';
  return true;
}

function gotoLogin() {
  router.push({ name: 'login', query: route.fullPath !== '/' ? { redirect: route.fullPath } : undefined });
}

function goto(view) {
  userMenuOpen.value = false;
  router.push({ name: view });
}

function toggleUserMenu() {
  userMenuOpen.value = !userMenuOpen.value;
}

function closeMenuOnOutside(event) {
  if (!event.target.closest?.('.topbar-user')) {
    userMenuOpen.value = false;
  }
}

function logout() {
  userMenuOpen.value = false;
  session.clear();
  toast.show('已退出登录', 'info');
  router.replace({ name: 'home', query: { view: 'home' } });
}

const isAdminVisible = computed(() => session.token && session.isAdmin);

onMounted(() => document.addEventListener('click', closeMenuOnOutside));
onUnmounted(() => document.removeEventListener('click', closeMenuOnOutside));
</script>

<template>
  <div class="app-shell">
    <header class="topbar">
      <div class="topbar-inner">
        <a class="topbar-brand" @click="router.push({ name: 'home' })">
          <svg width="22" height="22" viewBox="0 0 32 32" fill="none">
            <rect width="32" height="32" rx="8" fill="#d97706" />
            <path
              d="M8 16l5 5 11-11"
              stroke="#fff"
              stroke-width="3"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
          </svg>
          <span>Totoro EHS 合规评价系统</span>
        </a>

        <nav class="topbar-nav">
          <button
            v-for="item in navItems"
            :key="item.key"
            type="button"
            :class="['topbar-link', { active: isNavActive(item) }]"
            @click="onNavClick(item)"
          >
            {{ item.label }}
            <svg
              v-if="item.external"
              width="10"
              height="10"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2.5"
              style="margin-left: 4px; opacity: 0.6"
            >
              <path d="M7 17L17 7M9 7h8v8" />
            </svg>
          </button>
        </nav>

        <div class="topbar-actions">
          <template v-if="!session.token">
            <button type="button" class="btn-primary btn-sm" @click="gotoLogin">登录</button>
          </template>
          <template v-else>
            <div class="topbar-user">
              <button type="button" class="user-trigger" @click.stop="toggleUserMenu">
                <span class="user-avatar">{{ session.avatarInitial }}</span>
                <span class="user-name-inline">{{ session.username }}</span>
                <svg
                  width="12"
                  height="12"
                  viewBox="0 0 24 24"
                  fill="none"
                  stroke="currentColor"
                  stroke-width="2"
                >
                  <polyline points="6 9 12 15 18 9" />
                </svg>
              </button>
              <div v-if="userMenuOpen" class="user-menu">
                <div class="user-menu-header">
                  <span class="user-menu-name">{{ session.username }}</span>
                  <span class="user-menu-role">{{ session.roleText }}</span>
                </div>
                <div class="user-menu-list">
                  <button
                    type="button"
                    class="user-menu-item"
                    @click="userMenuOpen = false; router.push({ name: 'home', query: { view: 'home' } })"
                  >
                    <Icon name="home" :size="14" />
                    <span>首页</span>
                  </button>
                  <button
                    type="button"
                    class="user-menu-item"
                    @click="userMenuOpen = false; router.push({ name: 'home', query: { view: 'workbench' } })"
                  >
                    <Icon name="grid" :size="14" />
                    <span>工作台</span>
                  </button>
                  <button type="button" class="user-menu-item" @click="goto('tasks')">
                    <Icon name="clipboard" :size="14" />
                    <span>评价任务</span>
                  </button>
                  <button type="button" class="user-menu-item" @click="goto('detection')">
                    <Icon name="database" :size="14" />
                    <span>检测合规</span>
                  </button>
                  <button type="button" class="user-menu-item" @click="goto('agent')">
                    <Icon name="message" :size="14" />
                    <span>AI 助手</span>
                  </button>
                  <button v-if="isAdminVisible" type="button" class="user-menu-item" @click="goto('orgs')">
                    <Icon name="building" :size="14" />
                    <span>公司管理</span>
                  </button>
                  <button type="button" class="user-menu-item" @click="goto('settings')">
                    <Icon name="settings" :size="14" />
                    <span>账户设置</span>
                  </button>
                </div>
                <div class="user-menu-footer">
                  <button type="button" class="user-menu-item danger" @click="logout">
                    <Icon name="logout" :size="14" />
                    <span>退出登录</span>
                  </button>
                </div>
              </div>
            </div>
          </template>
        </div>
      </div>
    </header>

    <main class="main-wrapper">
      <slot />
    </main>

    <AppFooter />
  </div>
</template>
