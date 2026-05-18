from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import init_db
from app.api.exception_handlers import register_exception_handlers
from app.api.v1.router import include_api_v1
from app.core.config import settings
from app.core.logging_setup import configure_logging
from app.middleware.json_envelope import JsonEnvelopeMiddleware


@asynccontextmanager
async def lifespan(app: FastAPI):
    configure_logging(
        log_dir=settings.log_dir,
        log_file=settings.log_file,
        log_level=settings.log_level,
        max_bytes=settings.log_max_bytes,
        backup_count=settings.log_backup_count,
    )
    init_db()
    yield


def create_app() -> FastAPI:
    application = FastAPI(
        title=settings.app_name,
        redirect_slashes=False,
        description=(
            'EHS compliance assessment backend API. Successful 2xx JSON responses are wrapped as '
            '`{ success, code, message, data, details }`; errors use the same envelope shape.'
        ),
        debug=settings.app_debug,
        lifespan=lifespan,
        openapi_tags=[
            {'name': '认证', 'description': '用户注册、登录、修改密码。'},
            {'name': '评价任务', 'description': '资料上传、任务列表、任务详情、软删除和进度推送。'},
            {'name': '公司', 'description': '公司新增、列表、详情、更新和软删除。'},
            {'name': '系统管理', 'description': '管理员恢复数据、查询删除记录和重置密码。'},
            {'name': '运维与探测', 'description': '健康检查等无需登录接口。'},
        ],
    )

    application.add_middleware(JsonEnvelopeMiddleware, enable=True)
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials='*' not in settings.cors_origin_list,
        allow_methods=['*'],
        allow_headers=['*'],
        expose_headers=['X-Captcha-Id'],
    )

    register_exception_handlers(application)

    @application.get('/healthz', tags=['运维与探测'], summary='根路径健康检查')
    async def healthz():
        return {'status': 'ok'}

    include_api_v1(application)
    return application


app = create_app()
