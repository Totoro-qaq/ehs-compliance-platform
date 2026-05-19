import { defineStore } from 'pinia';

const MAX_VISIBLE = 3;
const DEFAULT_DURATION = 3500;

let nextId = 0;

export const useToastStore = defineStore('toast', {
  state: () => ({
    items: [],
  }),
  actions: {
    show(message, type = 'info', duration = DEFAULT_DURATION) {
      const id = ++nextId;
      this.items.push({ id, message, type });
      if (this.items.length > MAX_VISIBLE) {
        this.items.splice(0, this.items.length - MAX_VISIBLE);
      }
      setTimeout(() => this.dismiss(id), duration);
      return id;
    },
    dismiss(id) {
      const idx = this.items.findIndex((t) => t.id === id);
      if (idx !== -1) this.items.splice(idx, 1);
    },
    clear() {
      this.items = [];
    },
  },
});
