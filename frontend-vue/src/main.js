import { createApp } from 'vue';
import { createPinia } from 'pinia';
import App from './App.vue';
import router from './router';
import { useSessionStore } from './stores/session';
import './styles.css';

const app = createApp(App);
app.use(createPinia());
app.use(router);

const session = useSessionStore();
session.hydrate();

app.mount('#app');
