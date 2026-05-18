# EHS Frontend (Vue 3)

Vue 3 + Vite + Pinia + Vue Router 版本的 EHS 前端，从原 `frontend/` 静态版本迁移而来，UI 和接口契约保持一致。

## 目录结构

```text
src/
  api/client.js       # fetch 封装、响应包装解构、API URL 拼接
  components/         # AppShell（侧边栏）、ToastHost、CursorFollower
  router/index.js     # 4 个主视图路由（hash 模式）
  stores/             # session（token / 用户信息）、toast
  utils/format.js     # 时间、状态等格式化
  views/              # LoginView / HomeView / TasksView / OrgsView / SettingsView
  styles.css          # 全局样式（直接复用原项目）
  main.js             # 入口
  App.vue             # 顶层壳，根据登录态切换 LoginView / AppShell
```

## 本地启动

先把后端跑起来：

```powershell
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

然后在 `frontend-vue/` 安装依赖并启动 dev server：

```powershell
cd frontend-vue
npm install
npm run dev
```

默认端口 `http://127.0.0.1:5173`。后端 API 地址通过登录页右上角输入框配置，存在 `localStorage.ehs.apiBase`。

## 构建

```powershell
npm run build
```

产物输出到 `dist/`，可以用任意静态服务器（含 nginx）部署。
