<script setup>
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { chatWithAgent, listAgentMessages, listAgentSessions } from '../api/agent';
import { formatApiError } from '../api/client';
import { formatTime } from '../utils/format';

const router = useRouter();

const sessions = ref([]);
const messages = ref([]);
const activeSessionId = ref('');
const input = ref('');
const loadingSessions = ref(false);
const loadingMessages = ref(false);
const sending = ref(false);
const error = ref('');
const degraded = ref(false);
const responseMode = ref('model');

const quickPrompts = [
  '总结当前工作台',
  '有哪些待处理事项',
  '最近失败的任务是什么',
  '检测报告还有哪些没判定',
  '帮我查一下苯的职业接触限值',
];

const activeSession = computed(() => sessions.value.find((item) => item.id === activeSessionId.value) || null);

const sortedMessages = computed(() => [...messages.value].sort((a, b) => {
  const left = new Date(a.created_at).getTime() || 0;
  const right = new Date(b.created_at).getTime() || 0;
  return left - right;
}));

function messageRoleText(role) {
  if (role === 'USER') return '你';
  if (role === 'ASSISTANT') return 'AI 助手';
  return role || '-';
}

function messageClass(role) {
  return role === 'USER' ? 'user' : 'assistant';
}

async function loadSessions({ selectFirst = false } = {}) {
  loadingSessions.value = true;
  error.value = '';
  try {
    const data = await listAgentSessions(1, 50);
    sessions.value = data?.items || [];
    if (selectFirst && sessions.value.length && !activeSessionId.value) {
      await selectSession(sessions.value[0].id);
    }
  } catch (err) {
    error.value = formatApiError(err);
  } finally {
    loadingSessions.value = false;
  }
}

async function selectSession(sessionId) {
  if (!sessionId) return;
  activeSessionId.value = sessionId;
  loadingMessages.value = true;
  error.value = '';
  try {
    messages.value = await listAgentMessages(sessionId);
  } catch (err) {
    error.value = formatApiError(err);
  } finally {
    loadingMessages.value = false;
  }
}

function startNewSession() {
  activeSessionId.value = '';
  messages.value = [];
  degraded.value = false;
  responseMode.value = 'model';
  input.value = '';
  error.value = '';
}

async function sendMessage(content = input.value) {
  const question = (content || '').trim();
  if (!question || sending.value) return;

  sending.value = true;
  error.value = '';
  messages.value = [
    ...messages.value,
    {
      id: `local-${Date.now()}`,
      role: 'USER',
      content: question,
      created_at: new Date().toISOString(),
    },
  ];
  input.value = '';

  try {
    const data = await chatWithAgent({
      content: question,
      sessionId: activeSessionId.value,
    });
    activeSessionId.value = data?.session?.id || activeSessionId.value;
    degraded.value = Boolean(data?.degraded);
    responseMode.value = data?.run?.provider === 'rules' || data?.run?.model_name === 'fast-summary' ? 'rules' : 'model';
    await loadSessions();
    if (activeSessionId.value) {
      await selectSession(activeSessionId.value);
    } else if (data?.assistant_message) {
      messages.value = [data.user_message, data.assistant_message].filter(Boolean);
    }
  } catch (err) {
    error.value = formatApiError(err);
  } finally {
    sending.value = false;
  }
}

function usePrompt(prompt) {
  input.value = prompt;
  sendMessage(prompt);
}

function goWorkbench() {
  router.push({ name: 'home', query: { view: 'workbench' } });
}

onMounted(() => loadSessions({ selectFirst: true }));
</script>

<template>
  <div class="view-container agent-view">
    <div class="agent-layout">
      <aside class="agent-sidebar">
        <div class="agent-sidebar-head">
          <div>
            <span class="section-kicker">AI 合规助手</span>
            <h1>会话</h1>
          </div>
          <button type="button" class="btn-primary btn-sm" @click="startNewSession">新会话</button>
        </div>

        <div v-if="loadingSessions" class="empty-state compact">加载会话...</div>
        <div v-else-if="!sessions.length" class="agent-empty-sidebar">
          <strong>暂无历史会话</strong>
          <span>从右侧快捷问题开始。</span>
        </div>
        <div v-else class="agent-session-list">
          <button
            v-for="item in sessions"
            :key="item.id"
            type="button"
            :class="['agent-session-item', { active: item.id === activeSessionId }]"
            @click="selectSession(item.id)"
          >
            <strong>{{ item.title }}</strong>
            <span>{{ formatTime(item.last_message_at || item.updated_at) }}</span>
          </button>
        </div>
      </aside>

      <section class="agent-chat">
        <header class="agent-chat-head">
          <div>
            <span class="section-kicker">只读分析</span>
            <h2>{{ activeSession?.title || '新的 Agent 会话' }}</h2>
            <p>当前阶段只读取工作台、评价任务、检测报告和限值库摘要，不执行写操作。</p>
          </div>
          <div class="agent-chat-actions">
            <span v-if="degraded || responseMode === 'rules'" class="agent-mode-badge">规则摘要</span>
            <span v-else class="agent-mode-badge model">模型生成</span>
            <button type="button" class="btn-secondary btn-sm" @click="goWorkbench">工作台</button>
          </div>
        </header>

        <div v-if="error" class="agent-page-error">{{ error }}</div>

        <div class="agent-chat-body">
          <div v-if="loadingMessages" class="empty-state compact">加载消息...</div>
          <template v-else-if="sortedMessages.length">
            <article
              v-for="message in sortedMessages"
              :key="message.id"
              :class="['agent-message', messageClass(message.role)]"
            >
              <div class="agent-message-meta">
                <strong>{{ messageRoleText(message.role) }}</strong>
                <span>{{ formatTime(message.created_at) }}</span>
              </div>
              <p>{{ message.content }}</p>
            </article>
            <div v-if="sending" class="agent-message assistant pending">
              <div class="agent-message-meta">
                <strong>AI 助手</strong>
                <span>处理中</span>
              </div>
              <p>正在读取业务数据并生成摘要...</p>
            </div>
          </template>
          <div v-else class="agent-start-panel">
            <h3>从一个业务问题开始</h3>
            <p>它会按当前登录账号的权限读取数据，并把工具调用写入审计记录。</p>
            <div class="agent-start-prompts">
              <button
                v-for="prompt in quickPrompts"
                :key="prompt"
                type="button"
                :disabled="sending"
                @click="usePrompt(prompt)"
              >
                {{ prompt }}
              </button>
            </div>
          </div>
        </div>

        <form class="agent-compose" @submit.prevent="sendMessage()">
          <textarea
            v-model="input"
            placeholder="询问工作台、失败任务、检测判定、限值库..."
            :disabled="sending"
            rows="3"
            @keydown.enter.exact.prevent="sendMessage()"
          ></textarea>
          <button type="submit" class="btn-primary" :disabled="sending || !input.trim()">
            {{ sending ? '分析中' : '发送' }}
          </button>
        </form>
      </section>
    </div>
  </div>
</template>
