<script setup>
import { computed } from 'vue';
import { RouterView, useRoute } from 'vue-router';
import AppShell from './components/AppShell.vue';
import ToastHost from './components/ToastHost.vue';
import CursorFollower from './components/CursorFollower.vue';

const route = useRoute();
const isBlankLayout = computed(() => route.meta?.layout === 'blank');
</script>

<template>
  <CursorFollower />
  <RouterView v-if="isBlankLayout" />
  <AppShell v-else>
    <RouterView />
  </AppShell>
  <ToastHost />
</template>
