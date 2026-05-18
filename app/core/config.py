from pydantic import field_validator
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
    mysql_password: str = '123456'
    mysql_db: str = 'ehs_system'

    # Dify 工作流（阻塞）；DIFY_API_KEY 为空时 Worker 将报错
    dify_api_key: str = ''
    dify_base_url: str = 'https://api.dify.ai/v1'
    # 与画布「结束」节点输出变量名一致（JSON 内含 risks / summary）
    dify_workflow_result_key: str = 'result'
    # 与画布「开始」节点中文本变量名一致
    dify_workflow_input_text_key: str = 'document_text'

    # 预置默认公司 ID（init_db 会写入），上传评价未指定公司时使用
    default_organization_id: str = '00000000-0000-4000-8000-000000000001'

    # 对外 HTTP 请求（如 Dify）使用的 User-Agent，部分网关对默认 Python-urllib 不友好
    http_user_agent: str = (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 '
        '(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    )

    redis_url: str = 'redis://127.0.0.1:6379/0'
    celery_broker_url: str = 'redis://127.0.0.1:6379/0'
    celery_result_backend: str = 'redis://127.0.0.1:6379/1'

    upload_dir: str = './uploads'

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
    jwt_secret: str = 'change-me-in-production-use-long-random-secret'
    jwt_expire_minutes: int = 60

    # 可选：脚本/运维兼容；与 JWT 管理员二选一或同时配置
    admin_api_key: str = ''

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


settings = Settings()
