<script setup>
import { onBeforeUnmount, onMounted, reactive, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { fetchCaptcha, formatApiError } from '../api/client';
import { login, register } from '../api/auth';
import { useSessionStore } from '../stores/session';
import { useToastStore } from '../stores/toast';

const session = useSessionStore();
const toast = useToastStore();
const router = useRouter();
const route = useRoute();

function gotoNext() {
  const target = typeof route.query.redirect === 'string' ? route.query.redirect : null;
  if (target && target.startsWith('/')) {
    router.replace(target);
  } else {
    router.replace({ name: 'home', query: { view: 'workbench' } });
  }
}

const tab = ref('login');
const loginBusy = ref(false);
const registerBusy = ref(false);

const loginForm = reactive({ identifier: '', password: '', captcha: '' });
const registerForm = reactive({ username: '', email: '', phone: '', password: '' });

const captchaUrl = ref('');
let lastBlobUrl = '';

async function refreshCaptcha() {
  try {
    const blob = await fetchCaptcha();
    if (lastBlobUrl) URL.revokeObjectURL(lastBlobUrl);
    lastBlobUrl = URL.createObjectURL(blob);
    captchaUrl.value = lastBlobUrl;
  } catch {
    captchaUrl.value = '';
  }
}

async function submitLogin() {
  if (loginBusy.value) return;
  loginBusy.value = true;
  try {
    if (!session.captchaId) {
      await refreshCaptcha();
      throw new Error('请输入新的验证码');
    }
    const data = await login({
      identifier: loginForm.identifier.trim(),
      password: loginForm.password,
      captcha_id: session.captchaId,
      captcha_code: loginForm.captcha.trim(),
    });
    session.setSession(data.access_token, loginForm.identifier.trim());
    toast.show('登录成功', 'success');
    gotoNext();
  } catch (err) {
    toast.show(formatApiError(err), 'error');
    refreshCaptcha();
    loginForm.captcha = '';
  } finally {
    loginBusy.value = false;
  }
}

async function submitRegister() {
  if (registerBusy.value) return;
  registerBusy.value = true;
  try {
    const data = await register({
      username: registerForm.username.trim(),
      email: registerForm.email.trim(),
      phone: registerForm.phone.trim(),
      password: registerForm.password,
    });
    session.setSession(data.access_token, registerForm.username.trim());
    toast.show('注册成功', 'success');
    gotoNext();
  } catch (err) {
    toast.show(formatApiError(err), 'error');
  } finally {
    registerBusy.value = false;
  }
}

onMounted(() => {
  refreshCaptcha();
});

onBeforeUnmount(() => {
  if (lastBlobUrl) URL.revokeObjectURL(lastBlobUrl);
});
</script>

<template>
  <section class="login-view">
    <div class="login-bg-decoration">
      <div class="bg-blob bg-blob-1"></div>
      <div class="bg-blob bg-blob-2"></div>
      <div class="bg-blob bg-blob-3"></div>
    </div>

    <div class="login-card">
      <div class="brand-block">
        <div class="brand-icon">
          <svg width="40" height="40" viewBox="0 0 32 32" fill="none">
            <rect width="32" height="32" rx="8" fill="#d97706" />
            <path
              d="M8 16l5 5 11-11"
              stroke="#fff"
              stroke-width="3"
              stroke-linecap="round"
              stroke-linejoin="round"
            />
          </svg>
        </div>
        <h1>EHS 合规评价系统</h1>
        <p class="brand-desc">智能环境健康安全合规分析平台</p>
      </div>

      <div class="tab-buttons" role="tablist">
        <button type="button" :class="['tab', { active: tab === 'login' }]" @click="tab = 'login'">
          登录
        </button>
        <button type="button" :class="['tab', { active: tab === 'register' }]" @click="tab = 'register'">
          注册
        </button>
      </div>

      <form v-if="tab === 'login'" class="auth-form" @submit.prevent="submitLogin">
        <label>
          <span class="label-text">账号 / 邮箱 / 手机</span>
          <input v-model="loginForm.identifier" autocomplete="username" required />
        </label>
        <label>
          <span class="label-text">密码</span>
          <input v-model="loginForm.password" type="password" autocomplete="current-password" required />
        </label>
        <label>
          <span class="label-text">验证码</span>
          <div class="captcha-row">
            <input
              v-model="loginForm.captcha"
              autocomplete="off"
              maxlength="6"
              required
              placeholder="请输入图中字符"
            />
            <img
              class="captcha-image"
              :src="captchaUrl"
              alt="点击刷新验证码"
              title="点击刷新"
              @click="refreshCaptcha"
            />
          </div>
          <small class="form-hint">看不清可点击验证码图片刷新</small>
        </label>
        <button type="submit" class="btn-primary btn-lg" :disabled="loginBusy">
          {{ loginBusy ? '登录中...' : '登录' }}
        </button>
      </form>

      <form v-else class="auth-form" @submit.prevent="submitRegister">
        <p class="form-note">注册后会自动登录；生产环境建议由管理员统一创建账号。</p>
        <label>
          <span class="label-text">用户名</span>
          <input
            v-model="registerForm.username"
            autocomplete="username"
            required
            placeholder="3-64位，字母数字下划线"
          />
        </label>
        <label>
          <span class="label-text">邮箱</span>
          <input v-model="registerForm.email" type="email" autocomplete="email" required />
        </label>
        <label>
          <span class="label-text">手机号</span>
          <input v-model="registerForm.phone" autocomplete="tel" required placeholder="中国大陆手机号" />
        </label>
        <label>
          <span class="label-text">密码</span>
          <input
            v-model="registerForm.password"
            type="password"
            autocomplete="new-password"
            required
            placeholder="8位以上，含大小写字母和数字"
          />
        </label>
        <button type="submit" class="btn-primary btn-lg" :disabled="registerBusy">
          {{ registerBusy ? '注册中...' : '注册' }}
        </button>
      </form>
    </div>
  </section>
</template>
