<script setup>
import { onMounted, ref } from 'vue';
import { useRouter } from 'vue-router';
import { listTasks } from '../api/assessment';
import { listOrganizations } from '../api/organizations';

const router = useRouter();
const totalTasks = ref('-');
const successTasks = ref('-');
const totalOrgs = ref('-');

async function loadStats() {
  try {
    const [tasks, success, orgs] = await Promise.all([
      listTasks(1, 1),
      listTasks(1, 1, { status: 'SUCCESS' }),
      listOrganizations(1, 1),
    ]);
    totalTasks.value = tasks?.total ?? 0;
    successTasks.value = success?.total ?? 0;
    totalOrgs.value = orgs?.total ?? 0;
  } catch {
    /* 静默失败 */
  }
}

function nav(view) {
  router.push({ name: view });
}

onMounted(loadStats);
</script>

<template>
  <div class="view-container home-view">
    <section class="hero">
      <div class="hero-content">
        <div class="hero-badge">智能 EHS 合规评估</div>
        <h1 class="hero-title">让<span class="hero-accent">安全合规</span><br />更智能、更高效</h1>
        <p class="hero-desc">
          基于 AI 大模型的环境健康安全合规评估平台，自动识别风险点、生成整改建议、对齐国家标准。
        </p>
        <div class="hero-actions">
          <button class="btn-primary btn-lg" @click="nav('tasks')">
            <svg
              width="16"
              height="16"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <line x1="12" y1="5" x2="12" y2="19" />
              <line x1="5" y1="12" x2="19" y2="12" />
            </svg>
            开始评估
          </button>
          <button class="btn-secondary btn-lg">了解更多</button>
        </div>
        <div class="hero-stats">
          <div class="stat-item">
            <span class="stat-number">{{ totalTasks }}</span>
            <span class="stat-label">累计评估任务</span>
          </div>
          <div class="stat-divider"></div>
          <div class="stat-item">
            <span class="stat-number">{{ successTasks }}</span>
            <span class="stat-label">已完成任务</span>
          </div>
          <div class="stat-divider"></div>
          <div class="stat-item">
            <span class="stat-number">{{ totalOrgs }}</span>
            <span class="stat-label">服务公司</span>
          </div>
        </div>
      </div>
      <div class="hero-visual">
        <div class="hero-orb"></div>
        <div class="hero-card hero-card-1">
          <div class="hero-card-icon" style="background: #fef3c7; color: #d97706">
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <path d="M12 2L2 7l10 5 10-5-10-5z" />
              <path d="M2 17l10 5 10-5" />
              <path d="M2 12l10 5 10-5" />
            </svg>
          </div>
          <div>
            <div class="hero-card-title">AI 智能分析</div>
            <div class="hero-card-desc">秒级风险识别</div>
          </div>
        </div>
        <div class="hero-card hero-card-2">
          <div class="hero-card-icon" style="background: #ecfdf5; color: #059669">
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <path d="M9 12l2 2 4-4" />
              <path d="M21 12c0 4.97-4.03 9-9 9s-9-4.03-9-9 4.03-9 9-9 9 4.03 9 9z" />
            </svg>
          </div>
          <div>
            <div class="hero-card-title">合规对标</div>
            <div class="hero-card-desc">国标实时同步</div>
          </div>
        </div>
        <div class="hero-card hero-card-3">
          <div class="hero-card-icon" style="background: #eff6ff; color: #2563eb">
            <svg
              width="20"
              height="20"
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              stroke-width="2"
            >
              <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z" />
              <polyline points="14 2 14 8 20 8" />
            </svg>
          </div>
          <div>
            <div class="hero-card-title">结构化报告</div>
            <div class="hero-card-desc">一键导出整改清单</div>
          </div>
        </div>
      </div>
    </section>

    <section class="features">
      <h2 class="section-title">核心功能</h2>
      <p class="section-subtitle">为企业提供端到端的 EHS 合规管理能力</p>
      <div class="features-grid">
        <div class="feature-card">
          <div class="feature-icon" style="background: linear-gradient(135deg, #fef3c7, #fde68a)">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#d97706" stroke-width="2">
              <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4" />
              <polyline points="17 8 12 3 7 8" />
              <line x1="12" y1="3" x2="12" y2="15" />
            </svg>
          </div>
          <h3>多格式材料上传</h3>
          <p>支持 PDF、Word、TXT、CSV 等多种格式，自动 OCR 提取，无缝接入 AI 工作流。</p>
        </div>
        <div class="feature-card">
          <div class="feature-icon" style="background: linear-gradient(135deg, #dbeafe, #bfdbfe)">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#2563eb" stroke-width="2">
              <circle cx="12" cy="12" r="10" />
              <polyline points="12 6 12 12 16 14" />
            </svg>
          </div>
          <h3>异步任务处理</h3>
          <p>Celery + Redis 后台任务队列，秒级响应，长任务实时跟踪进度，支持 SSE 推送。</p>
        </div>
        <div class="feature-card">
          <div class="feature-icon" style="background: linear-gradient(135deg, #fce7f3, #fbcfe8)">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#db2777" stroke-width="2">
              <path d="M12 2L2 7l10 5 10-5-10-5z" />
              <path d="M2 17l10 5 10-5" />
              <path d="M2 12l10 5 10-5" />
            </svg>
          </div>
          <h3>AI 智能识别</h3>
          <p>对接 Dify 工作流，结合 RAG 知识库召回国标条款，自动判定违规风险等级。</p>
        </div>
        <div class="feature-card">
          <div class="feature-icon" style="background: linear-gradient(135deg, #d1fae5, #a7f3d0)">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="#059669" stroke-width="2">
              <path d="M9 11l3 3L22 4" />
              <path d="M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11" />
            </svg>
          </div>
          <h3>结构化结果</h3>
          <p>风险项、违规条款、整改建议、现场证据一应俱全，按 HIGH/MEDIUM/LOW 分级展示。</p>
        </div>
      </div>
    </section>

    <section class="workflow">
      <h2 class="section-title">使用流程</h2>
      <div class="workflow-steps">
        <div class="workflow-step">
          <div class="step-number">1</div>
          <h4>上传材料</h4>
          <p>将 EHS 检查记录、现场照片说明等材料上传至系统</p>
        </div>
        <div class="workflow-arrow">→</div>
        <div class="workflow-step">
          <div class="step-number">2</div>
          <h4>AI 分析</h4>
          <p>系统自动解析、调用 AI 工作流匹配国标条款</p>
        </div>
        <div class="workflow-arrow">→</div>
        <div class="workflow-step">
          <div class="step-number">3</div>
          <h4>查看报告</h4>
          <p>结构化展示风险项、整改建议和现场证据</p>
        </div>
        <div class="workflow-arrow">→</div>
        <div class="workflow-step">
          <div class="step-number">4</div>
          <h4>导出整改</h4>
          <p>按风险等级生成整改清单，跟踪闭环</p>
        </div>
      </div>
    </section>
  </div>
</template>
