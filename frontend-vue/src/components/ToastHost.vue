<script setup>
import { storeToRefs } from 'pinia';
import { useToastStore } from '../stores/toast';

const toast = useToastStore();
const { items } = storeToRefs(toast);
</script>

<template>
  <div class="toast-stack" role="status" aria-live="polite">
    <TransitionGroup name="toast">
      <div
        v-for="item in items"
        :key="item.id"
        :class="['toast-item', item.type]"
        @click="toast.dismiss(item.id)"
      >
        {{ item.message }}
      </div>
    </TransitionGroup>
  </div>
</template>

<style scoped>
.toast-stack {
  position: fixed;
  top: 24px;
  right: 24px;
  z-index: 1000;
  display: flex;
  flex-direction: column;
  gap: 10px;
  pointer-events: none;
}

.toast-item {
  pointer-events: auto;
  min-width: 220px;
  max-width: 360px;
  padding: 12px 16px;
  border-radius: 10px;
  font-size: 14px;
  line-height: 1.4;
  color: #fff;
  background: #1f2937;
  box-shadow: 0 10px 24px -8px rgba(15, 23, 42, 0.4);
  cursor: pointer;
}

.toast-item.success {
  background: #059669;
}
.toast-item.error {
  background: #dc2626;
}
.toast-item.info {
  background: #2563eb;
}

.toast-enter-from,
.toast-leave-to {
  opacity: 0;
  transform: translateX(20px);
}
.toast-enter-active,
.toast-leave-active {
  transition:
    opacity 0.2s ease,
    transform 0.2s ease;
}
.toast-leave-active {
  position: absolute;
  right: 0;
}
</style>
