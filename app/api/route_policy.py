"""
API v1 路由分层策略（白名单 = 挂在 public_api_v1 上的模块）。

- 身份获取类：auth_router（如 /api/v1/auth/register、/api/v1/auth/login）
- 运维与健康检查类：system_router（如 /api/v1/healthz）；应用根路径 /healthz 仍在 main 中
- 接口文档类：由 FastAPI 注册的 /docs、/redoc、/openapi.json，不在本前缀下
- 第三方回调类：暂无；后续新增公开回调 router 时，只加入 public_api_v1，勿挂 Depends(get_current_user)

需登录的接口统一挂在 business_api_v1（router 级 Depends(get_current_user)）。
管理员接口单独挂在 admin_api_v1，仅 Depends(require_admin)，以支持 X-Admin-Key 无 Bearer 场景。
"""

from __future__ import annotations
