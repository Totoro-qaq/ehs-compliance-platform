import { createRouter, createWebHashHistory } from 'vue-router';
import { useSessionStore } from '../stores/session';

const routes = [
  {
    path: '/login',
    name: 'login',
    component: () => import('../views/LoginView.vue'),
    meta: { public: true, layout: 'blank' },
  },
  { path: '/', redirect: '/home' },
  { path: '/home', name: 'home', component: () => import('../views/HomeView.vue'), meta: { public: true } },
  { path: '/tasks', name: 'tasks', component: () => import('../views/TasksView.vue') },
  { path: '/detection', name: 'detection', component: () => import('../views/DetectionView.vue') },
  { path: '/agent', name: 'agent', component: () => import('../views/AgentView.vue') },
  {
    path: '/orgs',
    name: 'orgs',
    component: () => import('../views/OrgsView.vue'),
    meta: { orgManagement: true },
  },
  { path: '/settings', name: 'settings', component: () => import('../views/SettingsView.vue') },
  { path: '/:pathMatch(.*)*', redirect: '/home' },
];

const router = createRouter({
  history: createWebHashHistory(),
  routes,
});

router.beforeEach((to) => {
  const session = useSessionStore();
  if (!session.token && !to.meta?.public) {
    return { name: 'login', query: to.fullPath !== '/' ? { redirect: to.fullPath } : undefined };
  }
  if (to.meta?.orgManagement && !session.canManageOrganizations) {
    return { name: 'home', query: { view: 'workbench' } };
  }
  if (session.token && to.name === 'login') {
    return { name: 'home', query: { view: 'workbench' } };
  }
  return true;
});

export default router;
