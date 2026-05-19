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
  {
    path: '/orgs',
    name: 'orgs',
    component: () => import('../views/OrgsView.vue'),
    meta: { adminOnly: true },
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
  if (to.meta?.adminOnly && !session.isAdmin) {
    return { name: 'home' };
  }
  if (session.token && to.name === 'login') {
    return { name: 'home' };
  }
  return true;
});

export default router;
