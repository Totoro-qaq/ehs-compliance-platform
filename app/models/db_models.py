from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from enum import Enum

from sqlalchemy import Date, DateTime, ForeignKey, Integer, Numeric, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import ModelBase


class AccountRole(str, Enum):
    ADMIN = 'ADMIN'
    ORG_ADMIN = 'ORG_ADMIN'
    USER = 'USER'


class TaskStatus(str, Enum):
    PENDING = 'PENDING'
    PARSING = 'PARSING'
    AI_ANALYZING = 'AI_ANALYZING'
    VALIDATING = 'VALIDATING'
    PERSISTING = 'PERSISTING'
    SUCCESS = 'SUCCESS'
    FAILED = 'FAILED'


# 合法的状态跳转（任何状态均可跳到 FAILED）
_VALID_TRANSITIONS: dict[TaskStatus, frozenset[TaskStatus]] = {
    TaskStatus.PENDING: frozenset({TaskStatus.PARSING, TaskStatus.FAILED}),
    TaskStatus.PARSING: frozenset({TaskStatus.AI_ANALYZING, TaskStatus.FAILED}),
    TaskStatus.AI_ANALYZING: frozenset({TaskStatus.VALIDATING, TaskStatus.FAILED}),
    TaskStatus.VALIDATING: frozenset({TaskStatus.PERSISTING, TaskStatus.FAILED}),
    TaskStatus.PERSISTING: frozenset({TaskStatus.SUCCESS, TaskStatus.FAILED}),
    TaskStatus.SUCCESS: frozenset(),
    TaskStatus.FAILED: frozenset(),
}


def check_status_transition(current: TaskStatus, target: TaskStatus) -> None:
    """校验状态跳转合法性，非法时抛 ValueError。"""
    allowed = _VALID_TRANSITIONS.get(current, frozenset())
    if target not in allowed:
        raise ValueError(f'非法状态跳转: {current.value} → {target.value}')


class Account(ModelBase):
    """B 端登录账号（密码仅存哈希）。"""

    __tablename__ = 'accounts'

    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[AccountRole] = mapped_column(
        SAEnum(AccountRole), nullable=False, default=AccountRole.USER
    )
    organization_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey('organizations.id', ondelete='RESTRICT'),
        nullable=True,
        index=True,
    )
    # 注册必填；历史/bootstrap 管理员可为空。库层唯一（MySQL 允许多条 NULL）
    email: Mapped[str | None] = mapped_column(String(255), unique=True, nullable=True, index=True)
    phone: Mapped[str | None] = mapped_column(String(20), unique=True, nullable=True, index=True)


class Organization(ModelBase):
    __tablename__ = 'organizations'

    name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    unified_social_credit_code: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    industry: Mapped[str | None] = mapped_column(String(128), nullable=True)
    address: Mapped[str | None] = mapped_column(String(500), nullable=True)
    contact_name: Mapped[str | None] = mapped_column(String(64), nullable=True)
    contact_phone: Mapped[str | None] = mapped_column(String(32), nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    tasks: Mapped[list['AssessmentTask']] = relationship(back_populates='organization')


class AssessmentTask(ModelBase):
    __tablename__ = 'assessment_tasks'

    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey('organizations.id', ondelete='RESTRICT'),
        nullable=False,
        index=True,
    )
    task_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    client_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    project_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    project_code: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    service_type: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    content_type: Mapped[str] = mapped_column(String(100), nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)

    status: Mapped[TaskStatus] = mapped_column(
        SAEnum(TaskStatus), default=TaskStatus.PENDING, nullable=False
    )
    progress: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 文本型 PDF / 后续格式解析后的正文摘录（大文本注意库表体量）
    parsed_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey('accounts.id', ondelete='SET NULL'),
        nullable=True,
        index=True,
    )

    organization: Mapped[Organization] = relationship(back_populates='tasks')
    timeline_events: Mapped[list['AssessmentTimelineEvent']] = relationship(
        back_populates='task',
        cascade='all, delete-orphan',
        order_by='AssessmentTimelineEvent.created_at',
    )


class AssessmentTimelineEvent(ModelBase):
    __tablename__ = 'assessment_timeline_events'

    task_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey('assessment_tasks.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    status: Mapped[TaskStatus] = mapped_column(SAEnum(TaskStatus), nullable=False, index=True)
    progress: Mapped[int] = mapped_column(Integer, nullable=False)
    message: Mapped[str | None] = mapped_column(String(255), nullable=True)
    elapsed_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    task: Mapped[AssessmentTask] = relationship(back_populates='timeline_events')


# ----------------------------------------------------------------------------
# 检测报告合规模块（结构化 MVP）
#
# 所有数值字段使用 Numeric / Decimal，避免浮点比较带来的超标判定边界误差；
# 单位、限值类型等强制走枚举，保留原始值与归一化值两套字段，方便审计。
# ----------------------------------------------------------------------------


class ReportType(str, Enum):
    """检测报告业务类型，决定 sample.medium 与限值匹配口径。"""

    OCCUPATIONAL_HEALTH = 'OCCUPATIONAL_HEALTH'  # 职业卫生
    WASTEWATER = 'WASTEWATER'  # 废水
    EXHAUST_GAS = 'EXHAUST_GAS'  # 废气
    NOISE = 'NOISE'  # 噪声
    HIGH_TEMPERATURE = 'HIGH_TEMPERATURE'  # 高温 / WBGT


class ReportStatus(str, Enum):
    """检测报告生命周期。CALCULATED 表示已生成 compliance_results。"""

    UPLOADED = 'UPLOADED'
    PARSED = 'PARSED'
    VALIDATED = 'VALIDATED'
    CALCULATED = 'CALCULATED'
    FAILED = 'FAILED'


class SampleMedium(str, Enum):
    """采样介质，限值匹配的硬约束之一。"""

    WORKPLACE_AIR = 'WORKPLACE_AIR'
    WASTEWATER = 'WASTEWATER'
    EXHAUST_GAS = 'EXHAUST_GAS'
    NOISE = 'NOISE'
    HIGH_TEMPERATURE = 'HIGH_TEMPERATURE'
    PHYSICAL_FACTOR = 'PHYSICAL_FACTOR'


class LimitType(str, Enum):
    """法规限值类型；RANGE 用于 pH 等需要上下限的指标。"""

    MAC = 'MAC'  # 最高容许浓度
    PC_TWA = 'PC_TWA'  # 时间加权平均容许浓度
    PC_STEL = 'PC_STEL'  # 短时间接触容许浓度
    DAILY_AVG = 'DAILY_AVG'  # 日均值
    INSTANT = 'INSTANT'  # 瞬时值 / 最大允许值
    RANGE = 'RANGE'  # 上下限范围（pH 等）


class ComplianceStatus(str, Enum):
    """最终合规判定结果。"""

    COMPLIANT = 'COMPLIANT'
    EXCEEDED = 'EXCEEDED'
    BORDERLINE = 'BORDERLINE'
    INSUFFICIENT_DATA = 'INSUFFICIENT_DATA'
    NEEDS_REVIEW = 'NEEDS_REVIEW'


class AgentSessionStatus(str, Enum):
    OPEN = 'OPEN'
    ARCHIVED = 'ARCHIVED'


class AgentMessageRole(str, Enum):
    USER = 'USER'
    ASSISTANT = 'ASSISTANT'
    SYSTEM = 'SYSTEM'
    TOOL = 'TOOL'


class AgentRunStatus(str, Enum):
    RUNNING = 'RUNNING'
    SUCCEEDED = 'SUCCEEDED'
    FAILED = 'FAILED'


class DetectionReport(ModelBase):
    """检测报告主表：一份上传文件 + 报告类型 + 状态机。"""

    __tablename__ = 'detection_reports'

    organization_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey('organizations.id', ondelete='RESTRICT'),
        nullable=False,
        index=True,
    )
    report_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    client_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    project_name: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    project_code: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    service_type: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    filename: Mapped[str] = mapped_column(String(255), nullable=False)
    file_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    report_type: Mapped[ReportType] = mapped_column(SAEnum(ReportType), nullable=False, index=True)
    status: Mapped[ReportStatus] = mapped_column(
        SAEnum(ReportStatus), nullable=False, default=ReportStatus.UPLOADED
    )
    report_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    issuer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_by_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey('accounts.id', ondelete='SET NULL'),
        nullable=True,
        index=True,
    )

    samples: Mapped[list['DetectionSample']] = relationship(
        back_populates='report', cascade='all, delete-orphan'
    )
    compliance_results: Mapped[list['ComplianceResult']] = relationship(
        back_populates='report', cascade='all, delete-orphan'
    )


class DetectionSample(ModelBase):
    """检测点 / 样品 / 采样记录。一份报告下挂多个样品。"""

    __tablename__ = 'detection_samples'

    report_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey('detection_reports.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    sample_point: Mapped[str] = mapped_column(String(255), nullable=False)
    workplace: Mapped[str | None] = mapped_column(String(255), nullable=True)
    post_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    medium: Mapped[SampleMedium] = mapped_column(SAEnum(SampleMedium), nullable=False, index=True)
    sample_time_start: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sample_time_end: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # 单次采样持续时长（分钟），TWA 计算所需
    duration_minutes: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    # 岗位/班次工时（小时），PC-TWA 标准时长 8h
    shift_hours: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    raw_payload_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    report: Mapped[DetectionReport] = relationship(back_populates='samples')
    measurements: Mapped[list['DetectionMeasurement']] = relationship(
        back_populates='sample', cascade='all, delete-orphan'
    )


class DetectionMeasurement(ModelBase):
    """检测因子结果。raw_* 与 normalized_* 双份字段，方便审计与回滚。"""

    __tablename__ = 'detection_measurements'

    sample_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey('detection_samples.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    indicator_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    indicator_alias: Mapped[str | None] = mapped_column(String(255), nullable=True)
    cas_no: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    raw_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    raw_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    normalized_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    normalized_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    # 检测限 / 方法定量限（< 检出限的样品参与判定时按检测限处理）
    detect_limit: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    # 报告表格内给出的限值；法规限值库未命中时作为可追溯的兜底判定依据。
    source_limit_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    source_limit_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    source_limit_type: Mapped[LimitType | None] = mapped_column(SAEnum(LimitType), nullable=True)
    method_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    raw_text: Mapped[str | None] = mapped_column(String(255), nullable=True)

    sample: Mapped[DetectionSample] = relationship(back_populates='measurements')


class RegulatoryLimit(ModelBase):
    """法规限值表。limit_value / limit_min / limit_max 互补：标量限值用前者，范围限值用后两者。"""

    __tablename__ = 'regulatory_limits'

    indicator_name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    cas_no: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    aliases_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    medium: Mapped[SampleMedium] = mapped_column(SAEnum(SampleMedium), nullable=False, index=True)
    limit_type: Mapped[LimitType] = mapped_column(SAEnum(LimitType), nullable=False, index=True)
    limit_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    limit_min: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    limit_max: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    unit: Mapped[str] = mapped_column(String(32), nullable=False)
    standard_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    standard_name: Mapped[str] = mapped_column(String(255), nullable=False)
    clause: Mapped[str | None] = mapped_column(String(128), nullable=True)
    basis_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    applicability_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 多条限值同时命中时，priority 越小越优先（行业 > 综合，地方严于国家时人工置顶）
    priority: Mapped[int] = mapped_column(Integer, nullable=False, default=100)


class StandardDocument(ModelBase):
    """标准原文元数据：原文件仍在外部资料目录，库内只保存可追溯索引。"""

    __tablename__ = 'standard_documents'

    standard_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    standard_name: Mapped[str] = mapped_column(String(255), nullable=False)
    domain: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    service_type: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    storage_backend: Mapped[str] = mapped_column(String(32), nullable=False, default='minio', index=True)
    bucket: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    object_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    object_version: Mapped[str | None] = mapped_column(String(128), nullable=True)
    source_path: Mapped[str] = mapped_column(String(1024), nullable=False)
    source_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    source_format: Mapped[str | None] = mapped_column(String(32), nullable=True)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True, index=True)
    file_size_bytes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    version: Mapped[str | None] = mapped_column(String(64), nullable=True)
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default='ACTIVE', index=True)
    is_sensitive: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    chunks: Mapped[list['StandardChunk']] = relationship(
        back_populates='document',
        cascade='all, delete-orphan',
        order_by='StandardChunk.chunk_index',
    )


class StandardChunk(ModelBase):
    """标准条文切片元数据：向量可在 Milvus，文本与来源链路保留在 MySQL。"""

    __tablename__ = 'standard_chunks'

    document_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey('standard_documents.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    chunk_id: Mapped[str] = mapped_column(String(128), nullable=False, unique=True, index=True)
    chunk_index: Mapped[int] = mapped_column(Integer, nullable=False)
    standard_code: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    standard_name: Mapped[str] = mapped_column(String(255), nullable=False)
    clause: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    domain: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    service_type: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    effective_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    effective_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    text_chunk: Mapped[str] = mapped_column(Text, nullable=False)
    text_hash: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    page_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    page_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_sensitive: Mapped[int] = mapped_column(Integer, nullable=False, default=0, index=True)
    milvus_collection: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    milvus_id: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    embedding_model: Mapped[str | None] = mapped_column(String(128), nullable=True)
    indexed_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    document: Mapped[StandardDocument] = relationship(back_populates='chunks')


class ComplianceResult(ModelBase):
    """合规判定结果：每条 measurement 对应一条结果，附违反依据。"""

    __tablename__ = 'compliance_results'

    report_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey('detection_reports.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    sample_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey('detection_samples.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    measurement_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey('detection_measurements.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    limit_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey('regulatory_limits.id', ondelete='SET NULL'),
        nullable=True,
        index=True,
    )
    calculated_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    calculated_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    limit_value: Mapped[Decimal | None] = mapped_column(Numeric(18, 6), nullable=True)
    limit_unit: Mapped[str | None] = mapped_column(String(32), nullable=True)
    limit_type: Mapped[LimitType | None] = mapped_column(SAEnum(LimitType), nullable=True)
    status: Mapped[ComplianceStatus] = mapped_column(
        SAEnum(ComplianceStatus), nullable=False, index=True
    )
    # 超标倍数 = (calculated - limit) / limit；范围限值场景为 NULL
    exceedance_multiple: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    standard_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    standard_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    clause: Mapped[str | None] = mapped_column(String(128), nullable=True)
    message: Mapped[str | None] = mapped_column(Text, nullable=True)

    report: Mapped[DetectionReport] = relationship(back_populates='compliance_results')


class AgentSession(ModelBase):
    """Agent 会话：绑定调用账号和可见公司范围。"""

    __tablename__ = 'agent_sessions'

    account_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey('accounts.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey('organizations.id', ondelete='SET NULL'),
        nullable=True,
        index=True,
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    status: Mapped[AgentSessionStatus] = mapped_column(
        SAEnum(AgentSessionStatus), nullable=False, default=AgentSessionStatus.OPEN, index=True
    )
    last_message_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)

    messages: Mapped[list['AgentMessage']] = relationship(
        back_populates='session',
        cascade='all, delete-orphan',
        order_by='AgentMessage.created_at',
    )
    runs: Mapped[list['AgentRun']] = relationship(
        back_populates='session',
        cascade='all, delete-orphan',
    )


class AgentMessage(ModelBase):
    """Agent 会话消息。"""

    __tablename__ = 'agent_messages'

    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey('agent_sessions.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    role: Mapped[AgentMessageRole] = mapped_column(
        SAEnum(AgentMessageRole), nullable=False, index=True
    )
    content: Mapped[str] = mapped_column(Text, nullable=False)
    metadata_json: Mapped[str | None] = mapped_column(Text, nullable=True)

    session: Mapped[AgentSession] = relationship(back_populates='messages')


class AgentRun(ModelBase):
    """一次 Agent 编排运行，记录模型、状态和耗时。"""

    __tablename__ = 'agent_runs'

    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey('agent_sessions.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    account_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey('accounts.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    organization_id: Mapped[str | None] = mapped_column(String(36), nullable=True, index=True)
    user_message_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey('agent_messages.id', ondelete='SET NULL'),
        nullable=True,
        index=True,
    )
    assistant_message_id: Mapped[str | None] = mapped_column(
        String(36),
        ForeignKey('agent_messages.id', ondelete='SET NULL'),
        nullable=True,
        index=True,
    )
    provider: Mapped[str] = mapped_column(String(32), nullable=False)
    model_name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[AgentRunStatus] = mapped_column(
        SAEnum(AgentRunStatus), nullable=False, default=AgentRunStatus.RUNNING, index=True
    )
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    session: Mapped[AgentSession] = relationship(back_populates='runs')
    tool_calls: Mapped[list['AgentToolCall']] = relationship(
        back_populates='run',
        cascade='all, delete-orphan',
        order_by='AgentToolCall.created_at',
    )


class AgentToolCall(ModelBase):
    """Agent 工具调用审计记录。"""

    __tablename__ = 'agent_tool_calls'

    run_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey('agent_runs.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    session_id: Mapped[str] = mapped_column(
        String(36),
        ForeignKey('agent_sessions.id', ondelete='CASCADE'),
        nullable=False,
        index=True,
    )
    tool_name: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    arguments_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    result_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    success: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    elapsed_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)

    run: Mapped[AgentRun] = relationship(back_populates='tool_calls')
