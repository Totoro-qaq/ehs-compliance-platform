import json
from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.models.db_models import TaskStatus


class AssessmentCreateResponse(BaseModel):
    """创建评价任务后的简要结果。"""

    task_id: str = Field(description='新建任务的唯一 ID')
    task_name: str | None = Field(default=None, description='面向用户展示的评价任务名称')
    status: TaskStatus = Field(description='任务当前状态（创建后多为 PENDING）')


class AssessmentTimelineEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    status: TaskStatus
    progress: int
    message: str | None = None
    elapsed_ms: int | None = None
    created_at: datetime


class AssessmentWaterfallSegment(BaseModel):
    status: TaskStatus
    label: str
    start_ms: int
    duration_ms: int
    progress: int


class AssessmentStatusResponse(BaseModel):
    """评价任务详情（供列表与单条查询）。"""

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)

    task_id: str = Field(alias='id', serialization_alias='task_id', description='任务 ID')
    organization_id: str = Field(description='所属公司 ID')
    task_name: str | None = Field(default=None, description='面向用户展示的评价任务名称')
    filename: str = Field(description='上传时的展示文件名')
    status: TaskStatus = Field(description='处理状态')
    progress: int = Field(description='进度 0–100')
    result_json: str | None = Field(default=None, exclude=True)
    result: 'EHSAssessmentResult | None' = Field(default=None, description='结构化分析结果')
    error_message: str | None = Field(default=None, description='失败时的错误说明')
    parsed_text: str | None = Field(default=None, description='解析得到的正文摘录（若有）')
    created_by_id: str | None = Field(default=None, description='创建人账号 ID')
    created_at: datetime = Field(description='创建时间')
    updated_at: datetime = Field(description='最后更新时间')
    timeline: list[AssessmentTimelineEventResponse] = Field(default_factory=list)
    waterfall: list[AssessmentWaterfallSegment] = Field(default_factory=list)

    @model_validator(mode='after')
    def _parse_result_json(self) -> 'AssessmentStatusResponse':
        """将 result_json 字符串解析为结构化的 EHSAssessmentResult。"""
        if self.result is not None:
            return self
        raw = self.result_json
        if not raw:
            return self
        try:
            data = json.loads(raw)
            self.result = EHSAssessmentResult.model_validate(data)
        except (json.JSONDecodeError, ValueError):
            pass
        return self


class EHSRiskItem(BaseModel):
    """单条风险项，兼容新旧两种 Dify 输出格式。"""

    # 新格式字段（知识库 RAG 版提示词输出）
    id: int | None = None
    description: str | None = None
    violated_standard: str | None = None
    severity: str | None = None
    recommendation: str | None = None
    deadline_suggestion: str | None = None

    # 旧格式字段（保持向后兼容）
    risk_level: str | None = None
    violation_clause: str | None = None
    rectification_advice: str | None = None
    evidence: str | None = None

    @model_validator(mode='after')
    def _normalize_fields(self) -> 'EHSRiskItem':
        """新旧字段互相填充，确保下游消费方拿到统一数据。"""
        # 旧 → 新
        if not self.severity and self.risk_level:
            self.severity = self.risk_level
        if not self.violated_standard and self.violation_clause:
            self.violated_standard = self.violation_clause
        if not self.recommendation and self.rectification_advice:
            self.recommendation = self.rectification_advice
        # 新 → 旧
        if not self.risk_level and self.severity:
            self.risk_level = self.severity
        if not self.violation_clause and self.violated_standard:
            self.violation_clause = self.violated_standard
        if not self.rectification_advice and self.recommendation:
            self.rectification_advice = self.recommendation
        return self


class EHSAssessmentResult(BaseModel):
    risks: list[EHSRiskItem]
    summary: str
    metadata: dict[str, Any] = Field(default_factory=dict)
