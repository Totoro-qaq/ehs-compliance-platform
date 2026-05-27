from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

# 生产环境禁止使用的危险默认值
# 保留这些字面量是为了在校验时给出明确提示——它们 **本身** 不是密钥，仅用于比对
_DANGEROUS_DEFAULTS: dict[str, set[str]] = {
    'jwt_secret': {
        'change-me-in-production-use-long-random-secret',
        'please-change-me-to-a-long-random-string',
    },
    'mysql_password': {'123456', 'root', 'changeme', ''},
    'bootstrap_admin_password': {'Aa123456', 'admin', 'admin123', 'ChangeMe_Strong_Password'},
    'admin_api_key': {'dev-admin-change-me'},
    'dify_api_key': {'app-replace-with-your-dify-api-key', ''},
}


class ProductionConfigError(RuntimeError):
    """生产环境检测到不安全配置时抛出，阻止应用启动。"""


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file='.env', env_file_encoding='utf-8', extra='ignore')

    app_name: str = 'EHS Compliance API'
    app_env: str = 'dev'
    app_debug: bool = True

    mysql_host: str = '127.0.0.1'
    mysql_port: int = 3306
    mysql_user: str = 'root'
    mysql_password: str = ''
    mysql_db: str = 'ehs_system'

    # Dify 工作流（阻塞）；DIFY_API_KEY 为空时 Worker 将报错
    dify_api_key: str = ''
    dify_base_url: str = 'https://api.dify.ai/v1'
    # 与画布「结束」节点输出变量名一致（JSON 内含 risks / summary）
    dify_workflow_result_key: str = 'result'
    # 与画布「开始」节点中文本变量名一致
    dify_workflow_input_text_key: str = 'document_text'
    # 仅对 429、5xx、临时网络错误做保守重试；阻塞超时默认不自动重放，避免重复计费
    dify_retry_max_attempts: int = Field(default=3, ge=1, le=5)
    dify_retry_initial_delay_seconds: float = Field(default=2.0, ge=0.1, le=60.0)
    dify_retry_max_delay_seconds: float = Field(default=10.0, ge=0.1, le=300.0)
    dify_retry_jitter_seconds: float = Field(default=0.5, ge=0.0, le=30.0)
    dify_retry_on_timeout: bool = False

    # Agent MVP：优先调用本地 Ollama，失败时后端返回规则化摘要，避免前端卡死。
    agent_llm_provider: str = 'ollama'
    ollama_base_url: str = 'http://127.0.0.1:11434'
    ollama_chat_model: str = 'qwen2.5:7b'
    agent_request_timeout_seconds: float = Field(default=120.0, ge=3.0, le=300.0)
    agent_runtime_max_tool_calls: int = Field(default=12, ge=1, le=50)
    agent_runtime_timeout_seconds: float = Field(default=30.0, ge=1.0, le=300.0)

    # 预置默认公司 ID（init_db 会写入），上传评价未指定公司时使用
    default_organization_id: str = '00000000-0000-4000-8000-000000000001'

    # 对外 HTTP 请求（如 Dify）使用的 User-Agent，部分网关对默认 Python-urllib 不友好
    http_user_agent: str = (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    )
    pdf_ocr_enabled: bool = False

    redis_url: str = 'redis://127.0.0.1:6379/0'
    celery_broker_url: str = 'redis://127.0.0.1:6379/0'
    celery_result_backend: str = 'redis://127.0.0.1:6379/1'

    upload_dir: str = './uploads'

    # 标准原文不进入代码仓库；默认走 MinIO 私有 bucket，只由 manifest 接入元数据/切片。
    standard_storage_backend: str = 'minio'
    standard_library_root: str = ''
    minio_endpoint: str = '127.0.0.1:9000'
    minio_access_key: str = ''
    minio_secret_key: str = ''
    minio_bucket: str = 'ehs-standard-library'
    minio_secure: bool = False
    minio_region: str = ''
    milvus_uri: str = 'http://127.0.0.1:19530'
    milvus_token: str = ''
    milvus_collection: str = 'ehs_standard_chunks'
    standard_embedding_model: str = ''
    ragflow_base_url: str = ''
    ragflow_api_key: str = ''
    ragflow_dataset_ids: str = ''
    ragflow_timeout_seconds: float = Field(default=30.0, ge=1.0, le=300.0)

    # B 端：单文件上限（字节），可在 .env 覆盖
    max_upload_bytes: int = 50 * 1024 * 1024

    # 软删除任务后文件保留天数，超期由定时任务清理磁盘文件
    upload_retention_days: int = 7

    # SSE 进度推送：客户端无新事件时的心跳间隔（秒）
    sse_heartbeat_interval: int = 15

    log_dir: str = './logs'
    log_file: str = 'ehs_api.log'
    log_worker_file: str = 'ehs_worker.log'
    log_level: str = 'INFO'
    log_max_bytes: int = 10 * 1024 * 1024
    log_backup_count: int = 5

    # JWT（勿在生产使用默认密钥）
    jwt_secret: str = 'change-me-in-production-use-long-random-secret'  # nosec - dev placeholder, blocked by validate_production
    jwt_expire_minutes: int = 60

    # 可选：脚本/运维兼容；与 JWT 管理员二选一或同时配置
    admin_api_key: str = ''

    # 登录验证码：默认启用。测试环境可通过 monkeypatch 或环境变量关闭，避免依赖真实 Redis。
    auth_captcha_required: bool = True

    # 首次启动若库中无该用户则创建（密码仅存哈希）；留空则不自动创建
    bootstrap_admin_username: str = 'admin'
    bootstrap_admin_password: str = ''

    # CORS：逗号分隔多个源，或单星号 *（生产建议写具体域名）
    cors_origins: str = '*'

    @field_validator('dify_api_key', 'dify_base_url', mode='before')
    @classmethod
    def _strip_dify_env(cls, v: object) -> object:
        if v is None or not isinstance(v, str):
            return v
        s = v.strip()
        if len(s) >= 2 and s[0] == s[-1] and s[0] in '"\'':
            s = s[1:-1].strip()
        return s

    @property
    def cors_origin_list(self) -> list[str]:
        v = self.cors_origins.strip()
        if v == '*':
            return ['*']
        return [x.strip() for x in v.split(',') if x.strip()]

    @property
    def database_url(self) -> str:
        return (
            f'mysql+pymysql://{self.mysql_user}:{self.mysql_password}'
            f'@{self.mysql_host}:{self.mysql_port}/{self.mysql_db}?charset=utf8mb4'
        )

    @property
    def ragflow_dataset_id_list(self) -> list[str]:
        return [item.strip() for item in self.ragflow_dataset_ids.split(',') if item.strip()]

    @property
    def is_production(self) -> bool:
        """识别生产环境：APP_ENV 为 prod / production / live 时启用强校验。"""
        return self.app_env.strip().lower() in {'prod', 'production', 'live'}

    def validate_production(self) -> None:
        """
        启动时校验：生产环境禁止使用危险默认值。

        规则：
        - APP_ENV 非生产时直接返回；
        - 生产环境下逐项比对 _DANGEROUS_DEFAULTS，命中即收集错误；
        - JWT_SECRET 额外要求长度 >= 32；
        - CORS_ORIGINS 不允许保留通配符 *；
        - APP_DEBUG 不允许为 True；
        - 任一项失败即抛出 ProductionConfigError，阻止应用/Worker 启动。
        """
        if not self.is_production:
            return

        errors: list[str] = []

        for field, bad_values in _DANGEROUS_DEFAULTS.items():
            value = getattr(self, field, '')
            if isinstance(value, str) and value.strip() in bad_values:
                errors.append(
                    f'{field.upper()} 仍为开发期默认/占位值，生产环境必须改为强随机值'
                )

        if len(self.jwt_secret) < 32:
            errors.append('JWT_SECRET 长度必须 >= 32 字符')

        if '*' in self.cors_origin_list:
            errors.append('CORS_ORIGINS 不允许使用 *，请配置具体域名列表')

        if self.app_debug:
            errors.append('APP_DEBUG 必须为 false')

        if errors:
            joined = '\n  - '.join(errors)
            raise ProductionConfigError(
                '检测到生产环境不安全配置，已阻止启动：\n  - ' + joined
            )


settings = Settings()
