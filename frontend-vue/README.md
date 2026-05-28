# EHS Frontend (Vue 3)

Vue 3 + Vite + Pinia + Vue Router 版本的 EHS 前端，从原 `frontend/` 静态版本迁移而来。当前前端覆盖工作台、评价任务、检测合规、AI 助手、组织管理和系统设置。

## 目录结构

```text
src/
  api/
    client.js          # fetch 封装、JSON 信封解包、requestFile 文件下载
    agent.js           # Agent 聊天、会话和消息接口
    assessment.js      # 评价任务接口
    auth.js            # 登录、验证码和当前用户接口
    detection.js       # 检测报告、限值库和判定结果接口
    organizations.js   # 组织管理接口
    reportPipeline.js  # 报告章节、readiness 和导出接口
  components/          # AppShell、ToastHost、CursorFollower
  router/index.js      # hash 路由和登录权限守卫
  stores/              # session、toast
  utils/format.js      # 时间、状态和错误格式化
  views/               # Login / Home / Tasks / Detection / Agent / Orgs / Settings
  styles.css           # 全局样式
  main.js              # 入口
  App.vue              # 顶层壳
```

## 主要能力

- 工作台：展示任务概览、检测概览和 Agent 快捷问答。
- 评价任务：上传文件、查看任务进度、查看详情、失败重试和软删除。
- 检测合规：导入结构化检测数据，解析 PDF / DOCX / DOC / TXT / ZIP 报告，运行合规判定，维护限值库。
- 报告流水线：在检测报告详情抽屉初始化章节、查看 readiness 阻塞原因、管理员审批或退回章节、下载 Markdown / TXT / DOCX / DOC。
- AI 助手：完整会话页支持会话列表、消息历史、删除会话和清空当前账号会话。
- 组织管理：按角色展示组织列表和管理入口。

## 本地启动

先启动后端：

```powershell
python -m uvicorn main:app --host 127.0.0.1 --port 8000
```

再启动前端：

```powershell
cd frontend-vue
npm install
npm run dev
```

默认端口为 `http://127.0.0.1:5173`。后端 API 地址优先读取 `VITE_API_BASE`，也可在登录页右上角输入框调整，运行时会写入 `localStorage.ehs.apiBase`。

## 环境变量

复制模板：

```powershell
Copy-Item .env.example .env.local
```

| 变量 | 说明 | 示例 |
|------|------|------|
| `VITE_API_BASE` | 后端 API 根地址，不带 `/api/v1` | `http://127.0.0.1:8000` |

## 构建与检查

```powershell
npm run lint
npm run build
```

构建产物输出到 `dist/`，可用 Nginx、Caddy、静态网站托管或对象存储部署。当前路由使用 hash history，刷新页面不需要额外 rewrite 配置。
