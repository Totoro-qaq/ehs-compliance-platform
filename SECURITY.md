# Security Policy / 安全策略

> 中英双语版本。English version follows.

---

## 中文版

### 支持的版本

本项目目前仍处于 **Alpha** 阶段，仅最新的 `develop` 分支接收安全更新。首个稳定版本（`v1.0.0`）发布后，本节将更新具体的支持矩阵。

| 分支 / 版本 | 是否接收安全更新 |
|-------------|------------------|
| `develop`   | ✅ 是            |
| 其他分支    | ❌ 否            |

### 报告漏洞

**请勿在公开 Issue 中提交安全漏洞**，以免被恶意利用。

请通过以下方式私下联系维护者：

1. **首选**：通过 GitHub 的 [Private vulnerability reporting](https://github.com/Totoro-qaq/ehs-compliance-platform/security/advisories/new) 提交 Security Advisory（推荐，自带保密通道）
2. **备用**：发送邮件至 **626836554@qq.com** 或 **msy626836554@gmail.com**，主题写明 `[SECURITY] EHS Platform - <漏洞简述>`

报告时请尽量包含：

- 受影响的组件、版本（commit SHA）
- 复现步骤（最小可复现示例）
- 漏洞影响：例如信息泄露、权限绕过、远程代码执行等
- 你建议的修复方向（可选）

### 处理流程与时限

| 阶段 | 时限 |
|------|------|
| 收到报告并确认 | **3 个工作日内** |
| 评估严重程度并给出初步反馈 | **7 个工作日内** |
| 发布修复（高危漏洞） | **30 天内** |
| 发布修复（中低危） | **90 天内** |
| 公开披露 | 修复发布后，按双方约定时间披露 |

我们会在 Security Advisory 中致谢报告者（除非你要求匿名）。

### 安全考量范围

本项目接受以下类型的漏洞报告：

- 认证 / 授权绕过（JWT、组织级数据隔离）
- SQL 注入、命令注入、XSS、CSRF
- 文件上传相关（路径穿越、类型绕过、超大文件 DoS）
- Dify Workflow 调用相关的密钥泄露与未授权访问
- 依赖链漏洞（仅当本项目代码以可被攻击者触发的方式使用时）

以下情况通常**不被视为安全漏洞**：

- 使用默认 `.env.example` 配置导致的弱口令（请遵循部署说明配置生产密钥）
- 仅在本地开发模式（`APP_DEBUG=true`）下成立的问题
- 第三方依赖的已公开 CVE（请直接升级 `requirements.txt`）

---

## English Version

### Supported Versions

This project is in **Alpha**. Only the latest `develop` branch receives security updates. After the first stable release (`v1.0.0`), the support matrix will be updated.

| Branch / Version | Supported |
|------------------|-----------|
| `develop`        | ✅ Yes    |
| Others           | ❌ No     |

### Reporting a Vulnerability

**Please do not file public GitHub issues for security vulnerabilities.**

Use one of the following private channels:

1. **Preferred**: open a [GitHub Private Security Advisory](https://github.com/Totoro-qaq/ehs-compliance-platform/security/advisories/new).
2. **Fallback**: email **626836554@qq.com** or **msy626836554@gmail.com** with the subject `[SECURITY] EHS Platform - <short description>`.

Please include:

- Affected component and version (commit SHA)
- Reproduction steps (minimal repro)
- Impact: information disclosure, auth bypass, RCE, etc.
- Suggested mitigation (optional)

### Response Timeline

| Stage | SLA |
|-------|-----|
| Acknowledge receipt | within **3 business days** |
| Initial severity assessment | within **7 business days** |
| Fix released (high severity) | within **30 days** |
| Fix released (medium / low) | within **90 days** |
| Public disclosure | after fix, by mutual agreement |

We will credit reporters in the Security Advisory unless you request anonymity.

### Scope

In scope:

- Authentication / authorization bypass (JWT, organization-level isolation)
- SQL injection, command injection, XSS, CSRF
- File-upload issues (path traversal, type confusion, oversized-payload DoS)
- Secret leakage or unauthorized access related to the Dify Workflow integration
- Dependency-chain vulnerabilities, when reachable via this project

Out of scope:

- Weak credentials caused by using `.env.example` defaults (follow deployment docs to set production secrets)
- Issues that only reproduce in local dev mode (`APP_DEBUG=true`)
- Already-published CVEs in third-party dependencies (please upgrade `requirements.txt` directly)
