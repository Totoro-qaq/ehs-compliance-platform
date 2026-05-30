<script setup>
import { computed, onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import {
  chatWithAgent,
  clearAgentSessions,
  deleteAgentSession,
  getAgentControlState,
  listAgentMessages,
  listAgentPrompts,
  listAgentRuns,
  listAgentSessions,
  listAgentSecurityEvents,
  listAgentToolCalls,
} from '../api/agent';
import { formatApiError } from '../api/client';
import Icon from '../components/Icon.vue';
import { useSessionStore } from '../stores/session';
import { formatTime } from '../utils/format';

const router = useRouter();
const session = useSessionStore();

const sessions = ref([]);
const messages = ref([]);
const activeSessionId = ref('');
const activePane = ref('chat');
const input = ref('');
const loadingSessions = ref(false);
const loadingMessages = ref(false);
const loadingControl = ref(false);
const sending = ref(false);
const deletingSessionId = ref('');
const clearingSessions = ref(false);
const error = ref('');
const controlError = ref('');
const degraded = ref(false);
const responseMode = ref('model');
const controlState = ref(null);
const runs = ref([]);
const toolCalls = ref([]);
const securityEvents = ref([]);
const prompts = ref([]);

const quickPrompts = [
  '总结当前工作台',
  '有哪些待处理事项',
  '最近失败的任务是什么',
  '检测报告还有哪些没判定',
  '查询 测试因子甲 限值',
];

const activeSession = computed(() => sessions.value.find((item) => item.id === activeSessionId.value) || null);
const modeLabel = computed(() => (degraded.value || responseMode.value === 'rules' ? '规则摘要' : '模型生成'));
const canViewControlCenter = computed(() => session.canManageOrganizations);

const sortedMessages = computed(() => [...messages.value].sort((a, b) => {
  const left = new Date(a.created_at).getTime() || 0;
  const right = new Date(b.created_at).getTime() || 0;
  return left - right;
}));
const agentStatItems = computed(() => [
  { label: '历史会话', value: sessions.value.length, tone: 'accent' },
  { label: '当前模式', value: modeLabel.value, tone: responseMode.value === 'model' && !degraded.value ? 'success' : 'info' },
  { label: '当前消息', value: sortedMessages.value.length, tone: 'info' },
  { label: '工具权限', value: '只读', tone: 'active-work' },
]);
const allowedToolCount = computed(() => (controlState.value?.tools || []).filter((item) => item.allowed_by_policy).length);
const controlStatItems = computed(() => [
  { label: '运行记录', value: runs.value.length, tone: 'accent' },
  { label: '工具调用', value: toolCalls.value.length, tone: 'info' },
  { label: '安全事件', value: securityEvents.value.length, tone: securityEvents.value.length ? 'warning' : 'success' },
  { label: '可用工具', value: allowedToolCount.value, tone: 'active-work' },
]);
const activePrompt = computed(() => prompts.value.find((item) => item.is_active) || prompts.value[0] || null);

function messageRoleText(role) {
  if (role === 'USER') return '你';
  if (role === 'ASSISTANT') return 'AI 助手';
  return role || '-';
}

function messageClass(role) {
  return role === 'USER' ? 'user' : 'assistant';
}

function shortId(value) {
  return value ? String(value).slice(0, 8) : '-';
}

function statusTone(status) {
  if (status === 'SUCCEEDED') return 'success';
  if (status === 'FAILED') return 'danger';
  return 'info';
}

function decisionTone(value) {
  if (value === 'allowed') return 'success';
  if (value === 'blocked') return 'danger';
  return 'info';
}

function runElapsed(run) {
  if (!run?.started_at || !run?.finished_at) return '-';
  const started = new Date(run.started_at).getTime();
  const finished = new Date(run.finished_at).getTime();
  if (!Number.isFinite(started) || !Number.isFinite(finished) || finished < started) return '-';
  return `${finished - started}ms`;
}

function jsonSummary(value) {
  if (!value) return '-';
  try {
    const parsed = JSON.parse(value);
    return Object.keys(parsed).slice(0, 4).join(' / ') || '-';
  } catch {
    return String(value).slice(0, 80);
  }
}

async function showPane(pane) {
  activePane.value = pane;
  if (pane === 'control' && canViewControlCenter.value) {
    await loadControlCenter();
  }
}

async function loadControlCenter() {
  loadingControl.value = true;
  controlError.value = '';
  try {
    const [stateData, runsData, callsData, eventsData, promptsData] = await Promise.all([
      getAgentControlState(),
      listAgentRuns(1, 20),
      listAgentToolCalls(1, 20),
      listAgentSecurityEvents(1, 20),
      listAgentPrompts(1, 20, { activeOnly: true }),
    ]);
    controlState.value = stateData || null;
    runs.value = runsData?.items || [];
    toolCalls.value = callsData?.items || [];
    securityEvents.value = eventsData?.items || [];
    prompts.value = promptsData?.items || [];
  } catch (err) {
    controlError.value = formatApiError(err);
  } finally {
    loadingControl.value = false;
  }
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
  activePane.value = 'chat';
  activeSessionId.value = '';
  messages.value = [];
  degraded.value = false;
  responseMode.value = 'model';
  input.value = '';
  error.value = '';
}

async function removeSession(sessionId) {
  if (!sessionId || deletingSessionId.value || sending.value) return;
  const confirmed = window.confirm('删除这条 AI 会话历史？删除后不可在列表中恢复。');
  if (!confirmed) return;

  deletingSessionId.value = sessionId;
  error.value = '';
  try {
    await deleteAgentSession(sessionId);
    if (activeSessionId.value === sessionId) {
      startNewSession();
    }
    await loadSessions();
  } catch (err) {
    error.value = formatApiError(err);
  } finally {
    deletingSessionId.value = '';
  }
}

async function clearHistory() {
  if (!sessions.value.length || clearingSessions.value || sending.value) return;
  const confirmed = window.confirm('清空当前账号的全部 AI 会话历史？清空后不可在列表中恢复。');
  if (!confirmed) return;

  clearingSessions.value = true;
  error.value = '';
  try {
    await clearAgentSessions();
    startNewSession();
    await loadSessions();
  } catch (err) {
    error.value = formatApiError(err);
  } finally {
    clearingSessions.value = false;
  }
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
    <header class="view-header">
      <div>
        <h1>AI 助手</h1>
        <p class="view-desc">按当前账号权限读取工作台、评价任务、检测报告和限值库摘要</p>
      </div>
      <div class="header-actions">
        <button type="button" class="btn-secondary" @click="goWorkbench">
          <Icon name="home" :size="16" />
          工作台
        </button>
        <button type="button" class="btn-primary" @click="startNewSession">
          <Icon name="plus" :size="16" />
          新会话
        </button>
      </div>
    </header>

    <div class="agent-pane-tabs">
      <button
        type="button"
        :class="{ active: activePane === 'chat' }"
        @click="showPane('chat')"
      >
        对话
      </button>
      <button
        v-if="canViewControlCenter"
        type="button"
        :class="{ active: activePane === 'control' }"
        @click="showPane('control')"
      >
        控制中心
      </button>
    </div>

    <template v-if="activePane === 'chat'">
      <div class="task-stat-strip agent-stat-strip">
        <div
          v-for="item in agentStatItems"
          :key="item.label"
          :class="['task-stat-card', item.tone]"
        >
          <span>{{ item.value }}</span>
          <small>{{ item.label }}</small>
        </div>
      </div>

      <div class="agent-layout">
      <aside class="agent-sidebar">
        <div class="agent-sidebar-head">
          <div>
            <span class="section-kicker">AI 合规助手</span>
            <h1>会话</h1>
          </div>
          <button
            type="button"
            class="btn-secondary btn-sm agent-clear-btn"
            :disabled="!sessions.length || clearingSessions || sending"
            @click="clearHistory"
          >
            <Icon name="trash" :size="14" />
            {{ clearingSessions ? '清空中' : '清空' }}
          </button>
        </div>

        <div v-if="loadingSessions" class="empty-state compact">加载会话...</div>
        <div v-else-if="!sessions.length" class="agent-empty-sidebar">
          <strong>暂无历史会话</strong>
          <span>从右侧快捷问题开始。</span>
        </div>
        <div v-else class="agent-session-list">
          <div
            v-for="item in sessions"
            :key="item.id"
            :class="['agent-session-item', { active: item.id === activeSessionId }]"
          >
            <button type="button" class="agent-session-main" @click="selectSession(item.id)">
              <strong>{{ item.title }}</strong>
              <span>{{ formatTime(item.last_message_at || item.updated_at) }}</span>
            </button>
            <button
              type="button"
              class="agent-session-delete"
              title="删除会话"
              :disabled="deletingSessionId === item.id || sending"
              @click="removeSession(item.id)"
            >
              <Icon name="trash" :size="14" />
            </button>
          </div>
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
            <Icon name="message" :size="16" />
            {{ sending ? '分析中' : '发送' }}
          </button>
        </form>
      </section>
      </div>
    </template>

    <section v-else class="agent-control-center">
      <div class="control-head">
        <div>
          <span class="section-kicker">Agent Control</span>
          <h2>运行审计</h2>
        </div>
        <button type="button" class="btn-secondary btn-sm" :disabled="loadingControl" @click="loadControlCenter">
          <Icon name="refresh" :size="14" />
          {{ loadingControl ? '刷新中' : '刷新' }}
        </button>
      </div>

      <div v-if="controlError" class="agent-page-error">{{ controlError }}</div>
      <div v-if="loadingControl" class="empty-state compact">加载控制中心...</div>

      <template v-else>
        <div class="task-stat-strip agent-stat-strip">
          <div
            v-for="item in controlStatItems"
            :key="item.label"
            :class="['task-stat-card', item.tone]"
          >
            <span>{{ item.value }}</span>
            <small>{{ item.label }}</small>
          </div>
        </div>

        <div class="control-grid">
          <section class="control-panel">
            <header>
              <h3>当前策略</h3>
              <span>{{ controlState?.policy?.policy_id || '-' }}</span>
            </header>
            <dl class="control-kv">
              <div>
                <dt>版本</dt>
                <dd>{{ controlState?.policy?.policy_version || '-' }}</dd>
              </div>
              <div>
                <dt>上下文</dt>
                <dd>{{ controlState?.policy?.max_context_chars || '-' }}</dd>
              </div>
              <div>
                <dt>工具上限</dt>
                <dd>{{ controlState?.policy?.max_tool_calls || '-' }}</dd>
              </div>
              <div>
                <dt>沙箱</dt>
                <dd>{{ controlState?.policy ? (controlState.policy.read_only ? '只读' : '可写') : '-' }}</dd>
              </div>
            </dl>
          </section>

          <section class="control-panel">
            <header>
              <h3>提示词版本</h3>
              <span>{{ activePrompt?.version || '-' }}</span>
            </header>
            <dl class="control-kv">
              <div>
                <dt>场景</dt>
                <dd>{{ activePrompt?.scenario || '-' }}</dd>
              </div>
              <div>
                <dt>状态</dt>
                <dd>{{ activePrompt?.is_active ? '启用' : '未启用' }}</dd>
              </div>
              <div>
                <dt>审批</dt>
                <dd>{{ formatTime(activePrompt?.approved_at) }}</dd>
              </div>
            </dl>
          </section>
        </div>

        <section class="control-panel wide">
          <header>
            <h3>运行记录</h3>
            <span>最近 {{ runs.length }} 条</span>
          </header>
          <div class="control-table-wrap">
            <table class="control-table">
              <thead>
                <tr>
                  <th>Run</th>
                  <th>模型</th>
                  <th>状态</th>
                  <th>策略</th>
                  <th>耗时</th>
                  <th>时间</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="run in runs" :key="run.id">
                  <td>{{ shortId(run.id) }}</td>
                  <td>{{ run.provider }} / {{ run.model_name }}</td>
                  <td><span :class="['control-badge', statusTone(run.status)]">{{ run.status }}</span></td>
                  <td>{{ run.policy_version || '-' }}</td>
                  <td>{{ runElapsed(run) }}</td>
                  <td>{{ formatTime(run.created_at) }}</td>
                </tr>
                <tr v-if="!runs.length">
                  <td colspan="6">暂无运行记录</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section class="control-panel wide">
          <header>
            <h3>工具调用</h3>
            <span>最近 {{ toolCalls.length }} 条</span>
          </header>
          <div class="control-table-wrap">
            <table class="control-table">
              <thead>
                <tr>
                  <th>工具</th>
                  <th>版本</th>
                  <th>决策</th>
                  <th>权限</th>
                  <th>摘要</th>
                  <th>耗时</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="call in toolCalls" :key="call.id">
                  <td>{{ call.tool_name }}</td>
                  <td>{{ call.tool_version || '-' }}</td>
                  <td><span :class="['control-badge', decisionTone(call.policy_decision)]">{{ call.policy_decision || '-' }}</span></td>
                  <td>{{ call.permission_level || '-' }} / {{ call.side_effect_level || '-' }}</td>
                  <td>{{ jsonSummary(call.result_summary_json) }}</td>
                  <td>{{ call.elapsed_ms ?? '-' }}ms</td>
                </tr>
                <tr v-if="!toolCalls.length">
                  <td colspan="6">暂无工具调用</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>

        <section class="control-panel wide">
          <header>
            <h3>安全事件</h3>
            <span>最近 {{ securityEvents.length }} 条</span>
          </header>
          <div class="control-table-wrap">
            <table class="control-table">
              <thead>
                <tr>
                  <th>级别</th>
                  <th>类型</th>
                  <th>工具</th>
                  <th>消息</th>
                  <th>时间</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="event in securityEvents" :key="event.id">
                  <td><span class="control-badge danger">{{ event.severity }}</span></td>
                  <td>{{ event.event_type }}</td>
                  <td>{{ event.tool_name || '-' }}</td>
                  <td>{{ event.message }}</td>
                  <td>{{ formatTime(event.created_at) }}</td>
                </tr>
                <tr v-if="!securityEvents.length">
                  <td colspan="5">暂无安全事件</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
      </template>
    </section>
  </div>
</template>
