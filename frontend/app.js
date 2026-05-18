const store = {
  apiBase: localStorage.getItem('ehs.apiBase') || 'http://127.0.0.1:8000',
  token: localStorage.getItem('ehs.token') || '',
  username: localStorage.getItem('ehs.username') || '',
  role: localStorage.getItem('ehs.role') || '',
  orgName: localStorage.getItem('ehs.orgName') || '',
  selectedTaskId: localStorage.getItem('ehs.selectedTaskId') || '',
  captchaId: '',
};

const state = {
  organizations: [],
  tasks: [],
  activeTask: null,
  currentPage: 1,
  pageSize: 15,
  totalTasks: 0,
  totalPages: 0,
  orgPage: 1,
  orgPageSize: 15,
  totalOrgs: 0,
  totalOrgPages: 0,
  currentView: 'home',
};

const el = {};

function $(selector) { return document.querySelector(selector); }

function bootElements() {
  Object.assign(el, {
    cursorRing: $('#cursorRing'),
    cursorDot: $('#cursorDot'),
    loginView: $('#loginView'),
    appView: $('#appView'),
    apiBaseInput: $('#apiBaseInput'),
    testApiBtn: $('#testApiBtn'),
    apiStatus: $('#apiStatus'),
    loginTab: $('#loginTab'),
    registerTab: $('#registerTab'),
    loginForm: $('#loginForm'),
    registerForm: $('#registerForm'),
    captchaImage: $('#captchaImage'),
    homeView: $('#homeView'),
    tasksView: $('#tasksView'),
    orgsView: $('#orgsView'),
    settingsView: $('#settingsView'),
    statTotalTasks: $('#statTotalTasks'),
    statSuccessTasks: $('#statSuccessTasks'),
    statOrgs: $('#statOrgs'),
    refreshBtn: $('#refreshBtn'),
    newTaskBtn: $('#newTaskBtn'),
    uploadPanel: $('#uploadPanel'),
    cancelUploadBtn: $('#cancelUploadBtn'),
    uploadForm: $('#uploadForm'),
    organizationSelect: $('#organizationSelect'),
    fileInput: $('#fileInput'),
    fileDrop: $('#fileDrop'),
    taskRows: $('#taskRows'),
    taskCount: $('#taskCount'),
    taskPagination: $('#taskPagination'),
    taskDrawer: $('#taskDrawer'),
    detailTitle: $('#detailTitle'),
    taskDetail: $('#taskDetail'),
    deleteTaskBtn: $('#deleteTaskBtn'),
    closeDrawerBtn: $('#closeDrawerBtn'),
    refreshOrgsBtn: $('#refreshOrgsBtn'),
    newOrgBtn: $('#newOrgBtn'),
    orgFormPanel: $('#orgFormPanel'),
    cancelOrgBtn: $('#cancelOrgBtn'),
    orgForm: $('#orgForm'),
    orgFormTitle: $('#orgFormTitle'),
    orgEditId: $('#orgEditId'),
    orgNameInput: $('#orgName'),
    orgRows: $('#orgRows'),
    orgCount: $('#orgCount'),
    orgPagination: $('#orgPagination'),
    passwordForm: $('#passwordForm'),
    logoutBtn: $('#logoutBtn'),
    logoutBtnSettings: $('#logoutBtnSettings'),
    sidebarUsername: $('#sidebarUsername'),
    sidebarRole: $('#sidebarRole'),
    userAvatar: $('#userAvatar'),
    settingsAvatar: $('#settingsAvatar'),
    profileUsername: $('#profileUsername'),
    profileRole: $('#profileRole'),
    profileOrg: $('#profileOrg'),
    toast: $('#toast'),
  });
}

// ===== Cursor Follower =====
function bindCursor() {
  if (matchMedia('(hover: none)').matches) return;
  let mouseX = 0, mouseY = 0, ringX = 0, ringY = 0;

  document.addEventListener('mousemove', (e) => {
    mouseX = e.clientX; mouseY = e.clientY;
    el.cursorDot.style.transform = `translate(${mouseX}px, ${mouseY}px) translate(-50%, -50%)`;
    el.cursorRing.classList.add('active');
    el.cursorDot.classList.add('active');
  });

  document.addEventListener('mouseleave', () => {
    el.cursorRing.classList.remove('active');
    el.cursorDot.classList.remove('active');
  });

  function animate() {
    ringX += (mouseX - ringX) * 0.18;
    ringY += (mouseY - ringY) * 0.18;
    el.cursorRing.style.transform = `translate(${ringX}px, ${ringY}px) translate(-50%, -50%)`;
    requestAnimationFrame(animate);
  }
  animate();

  document.addEventListener('mouseover', (e) => {
    if (e.target.closest('button, a, [data-task-id], .feature-card, .file-drop, input, select, .nav-item, .captcha-image, .workflow-step')) {
      el.cursorRing.classList.add('hover');
    }
  });
  document.addEventListener('mouseout', (e) => {
    if (e.target.closest('button, a, [data-task-id], .feature-card, .file-drop, input, select, .nav-item, .captcha-image, .workflow-step')) {
      el.cursorRing.classList.remove('hover');
    }
  });
}

function normalizeBase(value) {
  let base = (value || '').trim().replace(/\/+$/, '');
  if (!base) return 'http://127.0.0.1:8000';
  if (!/^https?:\/\//i.test(base)) base = `http://${base}`;
  return base;
}

function apiUrl(path) { return `${normalizeBase(store.apiBase)}${path}`; }

function setSession(token, username, role) {
  store.token = token || '';
  store.username = username || '';
  store.role = role || '';
  if (store.token) {
    localStorage.setItem('ehs.token', store.token);
    localStorage.setItem('ehs.username', store.username);
    localStorage.setItem('ehs.role', store.role);
  } else {
    localStorage.removeItem('ehs.token');
    localStorage.removeItem('ehs.username');
    localStorage.removeItem('ehs.role');
    localStorage.removeItem('ehs.orgName');
    localStorage.removeItem('ehs.selectedTaskId');
    store.selectedTaskId = '';
    store.orgName = '';
  }
  renderShell();
}

function renderShell() {
  const loggedIn = Boolean(store.token);
  el.loginView.classList.toggle('hidden', loggedIn);
  el.appView.classList.toggle('hidden', !loggedIn);
  if (loggedIn) {
    const initial = (store.username || '?')[0].toUpperCase();
    const roleText = store.role === 'ADMIN' ? '管理员' : '普通用户';
    el.sidebarUsername.textContent = store.username;
    el.sidebarRole.textContent = roleText;
    el.userAvatar.textContent = initial;
    el.settingsAvatar.textContent = initial;
    el.profileUsername.textContent = store.username;
    el.profileRole.textContent = roleText;
    el.profileOrg.textContent = store.orgName || '默认组织';
  } else {
    refreshCaptcha();
  }
}

function showToast(message, type = 'info') {
  el.toast.textContent = message;
  el.toast.className = `toast ${type}`;
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => { el.toast.classList.add('hidden'); }, 3500);
}

function unwrapEnvelope(body) {
  if (body && typeof body === 'object' && Object.prototype.hasOwnProperty.call(body, 'success')) {
    if (!body.success) {
      const err = new Error(body.message || body.code || '请求失败');
      err.code = body.code;
      err.details = body.details;
      throw err;
    }
    return body.data;
  }
  return body;
}

async function request(path, options = {}) {
  const headers = new Headers(options.headers || {});
  if (store.token) headers.set('Authorization', `Bearer ${store.token}`);
  if (options.body && !(options.body instanceof FormData) && !headers.has('Content-Type')) {
    headers.set('Content-Type', 'application/json');
  }

  let response;
  try {
    response = await fetch(apiUrl(path), { ...options, headers });
  } catch (err) {
    throw new Error(`无法连接后端：${apiUrl(path)}`);
  }

  const ct = response.headers.get('content-type') || '';
  const body = ct.includes('application/json') ? await response.json() : await response.text();

  if (!response.ok) {
    if (response.status === 401 && store.token) {
      setSession('', '', '');
      showToast('登录已过期，请重新登录', 'error');
      throw new Error('登录已过期');
    }
    if (body && typeof body === 'object') throw new Error(body.message || body.code || `HTTP ${response.status}`);
    throw new Error(body || `HTTP ${response.status}`);
  }
  return unwrapEnvelope(body);
}

async function refreshCaptcha() {
  try {
    const resp = await fetch(apiUrl('/api/v1/auth/captcha'), { cache: 'no-store' });
    if (!resp.ok) throw new Error('获取验证码失败');
    store.captchaId = resp.headers.get('X-Captcha-Id') || '';
    const blob = await resp.blob();
    if (el.captchaImage._lastUrl) URL.revokeObjectURL(el.captchaImage._lastUrl);
    const url = URL.createObjectURL(blob);
    el.captchaImage._lastUrl = url;
    el.captchaImage.src = url;
  } catch (err) {
    el.captchaImage.alt = '验证码加载失败，点击重试';
  }
}

// ===== Helpers =====
function escapeHtml(value) {
  return String(value ?? '').replaceAll('&', '&amp;').replaceAll('<', '&lt;').replaceAll('>', '&gt;').replaceAll('"', '&quot;');
}

function formatTime(value) {
  if (!value) return '-';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return value;
  return d.toLocaleString('zh-CN', { month: '2-digit', day: '2-digit', hour: '2-digit', minute: '2-digit' });
}

function statusText(status) {
  const map = { PENDING: '等待中', PARSING: '解析中', AI_ANALYZING: 'AI 分析', VALIDATING: '校验中', PERSISTING: '保存中', SUCCESS: '已完成', FAILED: '失败' };
  return map[status] || status || '-';
}

// ===== View Switching =====
function switchView(view) {
  state.currentView = view;
  el.homeView.classList.toggle('hidden', view !== 'home');
  el.tasksView.classList.toggle('hidden', view !== 'tasks');
  el.orgsView.classList.toggle('hidden', view !== 'orgs');
  el.settingsView.classList.toggle('hidden', view !== 'settings');
  document.querySelectorAll('.nav-item').forEach(btn => {
    btn.classList.toggle('active', btn.dataset.view === view);
  });
  if (view === 'tasks') refreshData();
  else if (view === 'orgs') loadOrgsPage();
  else if (view === 'home') loadHomeStats();
}

// ===== Home Stats =====
async function loadHomeStats() {
  if (!store.token) return;
  try {
    const tasks = await request(`/api/v1/assessment?page=1&page_size=1`);
    el.statTotalTasks.textContent = tasks?.total ?? 0;

    const orgs = await request('/api/v1/organizations?page=1&page_size=1');
    el.statOrgs.textContent = orgs?.total ?? 0;

    // 估算成功任务数（取前 200 条）
    const sample = await request(`/api/v1/assessment?page=1&page_size=200`);
    const successCount = (sample?.items || []).filter(t => t.status === 'SUCCESS').length;
    el.statSuccessTasks.textContent = successCount;
  } catch (err) { /* 静默失败 */ }
}

// ===== Organizations =====
function renderOrgSelect() {
  el.organizationSelect.innerHTML = '';
  const orgs = state.organizations.length ? state.organizations : [{ id: '', name: '默认公司' }];
  for (const org of orgs) {
    const opt = document.createElement('option');
    opt.value = org.id;
    opt.textContent = org.name || org.id;
    el.organizationSelect.append(opt);
  }
  if (state.organizations.length) {
    store.orgName = state.organizations[0].name || '默认组织';
    localStorage.setItem('ehs.orgName', store.orgName);
    el.profileOrg.textContent = store.orgName;
  }
}

async function loadOrgsPage() {
  try {
    const page = await request(`/api/v1/organizations?page=${state.orgPage}&page_size=${state.orgPageSize}`);
    state.totalOrgs = page?.total || 0;
    state.totalOrgPages = page?.pages || 1;
    renderOrgsList(page?.items || []);
    renderOrgPagination();
  } catch (err) { showToast(err.message, 'error'); }
}

function renderOrgsList(items) {
  el.orgRows.innerHTML = '';
  el.orgCount.textContent = `${state.totalOrgs} 家公司`;
  if (!items.length) {
    el.orgRows.innerHTML = '<tr class="empty-row"><td colspan="4">暂无公司数据</td></tr>';
    return;
  }
  const isAdmin = store.role === 'ADMIN';
  for (const org of items) {
    const row = document.createElement('tr');
    row.innerHTML = `
      <td><span class="task-filename">${escapeHtml(org.name)}</span></td>
      <td><code style="font-size:12px;color:var(--text-tertiary);">${escapeHtml(org.id)}</code></td>
      <td>${formatTime(org.created_at)}</td>
      <td style="text-align:right;">
        ${isAdmin ? `
          <button class="btn-icon-sm" data-action="edit" data-id="${org.id}" data-name="${escapeHtml(org.name)}" title="编辑">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M12 20h9"/><path d="M16.5 3.5a2.121 2.121 0 113 3L7 19l-4 1 1-4L16.5 3.5z"/></svg>
          </button>
          <button class="btn-icon-sm" data-action="delete" data-id="${org.id}" data-name="${escapeHtml(org.name)}" title="删除" style="color:var(--danger);">
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="3 6 5 6 21 6"/><path d="M19 6l-2 14a2 2 0 01-2 2H9a2 2 0 01-2-2L5 6m3 0V4a2 2 0 012-2h4a2 2 0 012 2v2"/></svg>
          </button>
        ` : '<span style="color:var(--text-tertiary);font-size:12px;">无权限</span>'}
      </td>
    `;
    el.orgRows.append(row);
  }
}

function renderOrgPagination() {
  el.orgPagination.innerHTML = '';
  if (state.totalOrgPages <= 1) return;
  const prev = document.createElement('button');
  prev.className = 'page-btn'; prev.textContent = '<';
  prev.disabled = state.orgPage <= 1;
  prev.onclick = () => { state.orgPage--; loadOrgsPage(); };
  el.orgPagination.append(prev);

  const info = document.createElement('span');
  info.className = 'page-info';
  info.textContent = `${state.orgPage} / ${state.totalOrgPages}`;
  el.orgPagination.append(info);

  const next = document.createElement('button');
  next.className = 'page-btn'; next.textContent = '>';
  next.disabled = state.orgPage >= state.totalOrgPages;
  next.onclick = () => { state.orgPage++; loadOrgsPage(); };
  el.orgPagination.append(next);
}

// ===== Task List =====
function renderTasks() {
  el.taskRows.innerHTML = '';
  el.taskCount.textContent = `${state.totalTasks} 条任务`;

  if (!state.tasks.length) {
    el.taskRows.innerHTML = '<tr class="empty-row"><td colspan="4">暂无评估任务</td></tr>';
    return;
  }

  for (const task of state.tasks) {
    const row = document.createElement('tr');
    row.className = task.task_id === store.selectedTaskId ? 'selected' : '';
    row.dataset.taskId = task.task_id;
    row.innerHTML = `
      <td><span class="task-filename">${escapeHtml(task.filename || task.task_id)}</span></td>
      <td><span class="status-badge ${task.status || ''}">${statusText(task.status)}</span></td>
      <td>
        <div class="progress-bar"><div class="progress-bar-fill" style="width:${task.progress ?? 0}%"></div></div>
        <span class="progress-text">${task.progress ?? 0}%</span>
      </td>
      <td>${formatTime(task.created_at)}</td>
    `;
    el.taskRows.append(row);
  }
}

function renderPagination() {
  el.taskPagination.innerHTML = '';
  if (state.totalPages <= 1) return;

  const prev = document.createElement('button');
  prev.className = 'page-btn'; prev.textContent = '<';
  prev.disabled = state.currentPage <= 1;
  prev.onclick = () => goToPage(state.currentPage - 1);
  el.taskPagination.append(prev);

  const info = document.createElement('span');
  info.className = 'page-info';
  info.textContent = `${state.currentPage} / ${state.totalPages}`;
  el.taskPagination.append(info);

  const next = document.createElement('button');
  next.className = 'page-btn'; next.textContent = '>';
  next.disabled = state.currentPage >= state.totalPages;
  next.onclick = () => goToPage(state.currentPage + 1);
  el.taskPagination.append(next);
}

async function goToPage(page) {
  if (page < 1 || page > state.totalPages) return;
  state.currentPage = page;
  await loadTasks();
}

function renderTaskDetail(task) {
  state.activeTask = task || null;
  el.deleteTaskBtn.disabled = !task;

  if (!task) {
    el.detailTitle.textContent = '任务详情';
    el.taskDetail.innerHTML = '<p class="empty-state">选择一个任务查看详情</p>';
    return;
  }

  el.detailTitle.textContent = task.filename || task.task_id;
  const risks = task.result?.risks || [];
  const summary = task.result?.summary || '';
  const parsedPreview = task.parsed_text ? task.parsed_text.slice(0, 2000) : '';

  el.taskDetail.innerHTML = `
    <dl class="detail-meta">
      <dt>任务 ID</dt><dd>${escapeHtml(task.task_id)}</dd>
      <dt>状态</dt><dd><span class="status-badge ${task.status || ''}">${statusText(task.status)}</span></dd>
      <dt>进度</dt><dd>${task.progress ?? 0}%</dd>
      <dt>创建时间</dt><dd>${formatTime(task.created_at)}</dd>
      ${task.error_message ? `<dt>错误信息</dt><dd style="color:var(--danger)">${escapeHtml(task.error_message)}</dd>` : ''}
    </dl>
    ${summary ? `<div class="detail-section"><h3>评估摘要</h3><p style="font-size:14px;line-height:1.7;color:var(--text-secondary)">${escapeHtml(summary)}</p></div>` : ''}
    <div class="detail-section"><h3>风险项 (${risks.length})</h3>${risks.length ? risks.map(renderRisk).join('') : '<p class="empty-state">暂无风险项</p>'}</div>
    ${parsedPreview ? `<div class="detail-section"><h3>解析文本预览</h3><div class="parsed-text-block">${escapeHtml(parsedPreview)}</div></div>` : ''}
  `;
}

function renderRisk(risk, index) {
  const title = risk.description || risk.violated_standard || `风险 ${index + 1}`;
  const severity = risk.severity || risk.risk_level || 'MEDIUM';
  const recommendation = risk.recommendation || risk.rectification_advice || '';
  const evidence = risk.evidence || '';
  return `
    <div class="risk-card">
      <div class="risk-card-header">
        <span class="risk-card-title">${escapeHtml(title)}</span>
        <span class="risk-severity ${severity}">${severity}</span>
      </div>
      <div class="risk-card-body">
        ${recommendation ? `<p><span class="risk-label">整改建议：</span>${escapeHtml(recommendation)}</p>` : ''}
        ${evidence ? `<p><span class="risk-label">现场证据：</span>${escapeHtml(evidence)}</p>` : ''}
      </div>
    </div>
  `;
}

function openDrawer(task) {
  renderTaskDetail(task);
  el.taskDrawer.classList.remove('hidden');
  requestAnimationFrame(() => el.taskDrawer.classList.add('open'));
}

function closeDrawer() {
  el.taskDrawer.classList.remove('open');
  setTimeout(() => el.taskDrawer.classList.add('hidden'), 260);
}

async function loadOrganizations() {
  const page = await request('/api/v1/organizations?page=1&page_size=200');
  state.organizations = page?.items || [];
  renderOrgSelect();
}

async function loadTasks() {
  const page = await request(`/api/v1/assessment?page=${state.currentPage}&page_size=${state.pageSize}`);
  state.tasks = page?.items || [];
  state.totalTasks = page?.total || 0;
  state.totalPages = page?.pages || 1;
  renderTasks();
  renderPagination();
}

async function selectTask(taskId) {
  if (!taskId) return;
  store.selectedTaskId = taskId;
  localStorage.setItem('ehs.selectedTaskId', taskId);
  renderTasks();
  const task = await request(`/api/v1/assessment/${encodeURIComponent(taskId)}`);
  openDrawer(task);
}

async function refreshData() {
  if (!store.token) return;
  try {
    await loadOrganizations();
    await loadTasks();
  } catch (err) { showToast(err.message, 'error'); }
}

function switchAuthTab(tab) {
  const isLogin = tab === 'login';
  el.loginTab.classList.toggle('active', isLogin);
  el.registerTab.classList.toggle('active', !isLogin);
  el.loginForm.classList.toggle('hidden', !isLogin);
  el.registerForm.classList.toggle('hidden', isLogin);
}

function parseJwtRole(token) {
  try {
    const payload = JSON.parse(atob(token.split('.')[1]));
    return payload.role || 'USER';
  } catch { return 'USER'; }
}

function bindEvents() {
  el.apiBaseInput.value = store.apiBase;

  el.testApiBtn.addEventListener('click', async () => {
    try {
      store.apiBase = normalizeBase(el.apiBaseInput.value);
      el.apiBaseInput.value = store.apiBase;
      localStorage.setItem('ehs.apiBase', store.apiBase);
      const health = await request('/healthz');
      if (health?.status !== 'ok') throw new Error('健康检查异常');
      el.apiStatus.textContent = '连接正常';
      el.apiStatus.style.color = 'var(--success)';
      showToast('后端连接正常', 'success');
      refreshCaptcha();
    } catch (err) {
      el.apiStatus.textContent = err.message;
      el.apiStatus.style.color = 'var(--danger)';
      showToast(err.message, 'error');
    }
  });

  el.loginTab.addEventListener('click', () => switchAuthTab('login'));
  el.registerTab.addEventListener('click', () => switchAuthTab('register'));
  el.captchaImage.addEventListener('click', refreshCaptcha);

  el.loginForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      const identifier = $('#loginIdentifier').value.trim();
      const password = $('#loginPassword').value;
      const captcha_code = $('#loginCaptcha').value.trim();
      if (!store.captchaId) { await refreshCaptcha(); throw new Error('请输入新的验证码'); }
      const data = await request('/api/v1/auth/login', {
        method: 'POST',
        body: JSON.stringify({ identifier, password, captcha_id: store.captchaId, captcha_code }),
      });
      setSession(data.access_token, identifier, parseJwtRole(data.access_token));
      showToast('登录成功', 'success');
      switchView('home');
      await refreshData();
    } catch (err) {
      showToast(err.message, 'error');
      refreshCaptcha();
      $('#loginCaptcha').value = '';
    }
  });

  el.registerForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      const username = $('#registerUsername').value.trim();
      const email = $('#registerEmail').value.trim();
      const phone = $('#registerPhone').value.trim();
      const password = $('#registerPassword').value;
      const data = await request('/api/v1/auth/register', {
        method: 'POST',
        body: JSON.stringify({ username, email, phone, password }),
      });
      setSession(data.access_token, username, parseJwtRole(data.access_token));
      showToast('注册成功', 'success');
      switchView('home');
      await refreshData();
    } catch (err) { showToast(err.message, 'error'); }
  });

  // Sidebar nav
  document.querySelectorAll('.nav-item').forEach(btn => {
    btn.addEventListener('click', () => switchView(btn.dataset.view));
  });

  // Hero buttons
  document.querySelectorAll('[data-nav]').forEach(btn => {
    btn.addEventListener('click', () => switchView(btn.dataset.nav));
  });

  // Logout
  const doLogout = () => { setSession('', '', ''); state.tasks = []; state.organizations = []; closeDrawer(); };
  el.logoutBtn.addEventListener('click', doLogout);
  el.logoutBtnSettings.addEventListener('click', doLogout);

  // Upload panel toggle
  el.newTaskBtn.addEventListener('click', () => el.uploadPanel.classList.toggle('hidden'));
  el.cancelUploadBtn.addEventListener('click', () => el.uploadPanel.classList.add('hidden'));

  el.fileInput.addEventListener('change', () => {
    el.fileDrop.classList.toggle('has-file', el.fileInput.files.length > 0);
    const text = el.fileDrop.querySelector('.file-drop-text');
    if (el.fileInput.files.length) text.textContent = el.fileInput.files[0].name;
    else text.textContent = '点击或拖拽文件到此处';
  });

  el.uploadForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    try {
      const file = el.fileInput.files[0];
      if (!file) throw new Error('请选择文件');
      const form = new FormData();
      form.append('file', file);
      if (el.organizationSelect.value) form.append('organization_id', el.organizationSelect.value);
      const data = await request('/api/v1/assessment', { method: 'POST', body: form });
      store.selectedTaskId = data.task_id;
      localStorage.setItem('ehs.selectedTaskId', data.task_id);
      el.uploadForm.reset();
      el.fileDrop.classList.remove('has-file');
      el.fileDrop.querySelector('.file-drop-text').textContent = '点击或拖拽文件到此处';
      el.uploadPanel.classList.add('hidden');
      showToast('任务已创建', 'success');
      state.currentPage = 1;
      await loadTasks();
    } catch (err) { showToast(err.message, 'error'); }
  });

  el.refreshBtn.addEventListener('click', async () => {
    try { await refreshData(); showToast('数据已刷新', 'success'); }
    catch (err) { showToast(err.message, 'error'); }
  });

  el.taskRows.addEventListener('click', async (e) => {
    const row = e.target.closest('tr[data-task-id]');
    if (!row) return;
    try { await selectTask(row.dataset.taskId); }
    catch (err) { showToast(err.message, 'error'); }
  });

  el.closeDrawerBtn.addEventListener('click', closeDrawer);

  el.deleteTaskBtn.addEventListener('click', async () => {
    if (!state.activeTask) return;
    if (!confirm('确认删除当前任务？此操作可由管理员恢复。')) return;
    try {
      await request(`/api/v1/assessment/${encodeURIComponent(state.activeTask.task_id)}`, { method: 'DELETE' });
      store.selectedTaskId = '';
      localStorage.removeItem('ehs.selectedTaskId');
      closeDrawer();
      showToast('任务已删除', 'success');
      await loadTasks();
    } catch (err) { showToast(err.message, 'error'); }
  });

  // Organizations
  el.refreshOrgsBtn.addEventListener('click', () => loadOrgsPage().then(() => showToast('已刷新', 'success')));
  el.newOrgBtn.addEventListener('click', () => {
    if (store.role !== 'ADMIN') { showToast('仅管理员可创建公司', 'error'); return; }
    el.orgFormTitle.textContent = '新建公司';
    el.orgEditId.value = '';
    el.orgNameInput.value = '';
    el.orgFormPanel.classList.remove('hidden');
  });
  el.cancelOrgBtn.addEventListener('click', () => el.orgFormPanel.classList.add('hidden'));

  el.orgForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const name = el.orgNameInput.value.trim();
    const editId = el.orgEditId.value;
    if (!name) return;
    try {
      if (editId) {
        await request(`/api/v1/organizations/${editId}`, { method: 'PATCH', body: JSON.stringify({ name }) });
        showToast('公司已更新', 'success');
      } else {
        await request('/api/v1/organizations', { method: 'POST', body: JSON.stringify({ name }) });
        showToast('公司已创建', 'success');
      }
      el.orgFormPanel.classList.add('hidden');
      await loadOrgsPage();
    } catch (err) { showToast(err.message, 'error'); }
  });

  el.orgRows.addEventListener('click', async (e) => {
    const btn = e.target.closest('button[data-action]');
    if (!btn) return;
    const action = btn.dataset.action;
    const id = btn.dataset.id;
    const name = btn.dataset.name;
    if (action === 'edit') {
      el.orgFormTitle.textContent = '编辑公司';
      el.orgEditId.value = id;
      el.orgNameInput.value = name;
      el.orgFormPanel.classList.remove('hidden');
    } else if (action === 'delete') {
      if (!confirm(`确认删除公司「${name}」？该公司下的用户和任务将被保留。`)) return;
      try {
        await request(`/api/v1/organizations/${id}`, { method: 'DELETE' });
        showToast('公司已删除', 'success');
        await loadOrgsPage();
      } catch (err) { showToast(err.message, 'error'); }
    }
  });

  // Password form
  el.passwordForm.addEventListener('submit', async (e) => {
    e.preventDefault();
    const oldPwd = $('#oldPassword').value;
    const newPwd = $('#newPassword').value;
    const confirmPwd = $('#confirmPassword').value;
    if (newPwd !== confirmPwd) { showToast('两次输入的新密码不一致', 'error'); return; }
    try {
      await request('/api/v1/auth/change-password', {
        method: 'POST',
        body: JSON.stringify({ old_password: oldPwd, new_password: newPwd }),
      });
      el.passwordForm.reset();
      showToast('密码修改成功，请使用新密码重新登录', 'success');
      setTimeout(() => { setSession('', '', ''); }, 1500);
    } catch (err) { showToast(err.message, 'error'); }
  });
}

async function init() {
  bootElements();
  bindCursor();
  bindEvents();
  renderShell();
  if (store.token) {
    try {
      switchView('home');
      await loadHomeStats();
    } catch (err) { showToast(err.message, 'error'); }
  } else {
    refreshCaptcha();
  }
}

init();
