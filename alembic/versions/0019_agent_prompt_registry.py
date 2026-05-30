"""add agent prompt registry

Revision ID: 0019_agent_prompt_registry
Revises: 0018_agent_audit_security
Create Date: 2026-05-30 00:00:00.000000
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime

import sqlalchemy as sa

from alembic import op

revision: str = '0019_agent_prompt_registry'
down_revision: str | None = '0018_agent_audit_security'
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None
__all__ = ['revision', 'down_revision', 'branch_labels', 'depends_on', 'upgrade', 'downgrade']

agent_prompt_scenario = sa.Enum('agent_chat', name='agent_prompt_scenario')


def _audit_columns() -> list[sa.Column]:
    return [
        sa.Column('id', sa.String(length=36), nullable=False),
        sa.Column('created_at', sa.DateTime(), nullable=False),
        sa.Column('updated_at', sa.DateTime(), nullable=False),
        sa.Column('deleted_at', sa.DateTime(), nullable=True),
    ]


def upgrade() -> None:
    op.create_table(
        'agent_prompts',
        *_audit_columns(),
        sa.Column('name', sa.String(length=128), nullable=False),
        sa.Column('version', sa.String(length=64), nullable=False),
        sa.Column('scenario', agent_prompt_scenario, nullable=False),
        sa.Column('system_prompt', sa.Text(), nullable=False),
        sa.Column('developer_prompt', sa.Text(), nullable=True),
        sa.Column('output_contract_json', sa.Text(), nullable=True),
        sa.Column('risk_notes', sa.Text(), nullable=True),
        sa.Column('is_active', sa.Integer(), nullable=False),
        sa.Column('approved_by_id', sa.String(length=36), nullable=True),
        sa.Column('approved_at', sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(['approved_by_id'], ['accounts.id'], ondelete='SET NULL'),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('scenario', 'version', name='uq_agent_prompts_scenario_version'),
    )
    op.create_index(op.f('ix_agent_prompts_approved_by_id'), 'agent_prompts', ['approved_by_id'])
    op.create_index(op.f('ix_agent_prompts_deleted_at'), 'agent_prompts', ['deleted_at'])
    op.create_index(op.f('ix_agent_prompts_is_active'), 'agent_prompts', ['is_active'])
    op.create_index(op.f('ix_agent_prompts_scenario'), 'agent_prompts', ['scenario'])

    prompts = sa.table(
        'agent_prompts',
        sa.column('id', sa.String),
        sa.column('created_at', sa.DateTime),
        sa.column('updated_at', sa.DateTime),
        sa.column('deleted_at', sa.DateTime),
        sa.column('name', sa.String),
        sa.column('version', sa.String),
        sa.column('scenario', sa.String),
        sa.column('system_prompt', sa.Text),
        sa.column('developer_prompt', sa.Text),
        sa.column('output_contract_json', sa.Text),
        sa.column('risk_notes', sa.Text),
        sa.column('is_active', sa.Integer),
        sa.column('approved_by_id', sa.String),
        sa.column('approved_at', sa.DateTime),
    )
    now = datetime.utcnow()
    op.bulk_insert(
        prompts,
        [
            {
                'id': 'agent-chat-default-v1',
                'created_at': now,
                'updated_at': now,
                'deleted_at': None,
                'name': 'Agent Chat Default Prompt',
                'version': 'v1',
                'scenario': 'agent_chat',
                'system_prompt': (
                    '你是 EHS 合规管理平台助手，服务对象包括企业和第三方检测机构。\n'
                    '你只能基于后端工具提供的数据回答，不允许编造任务、报告、标准或法规条款。\n'
                    '当前阶段你只能做只读分析，不能声称已经创建、删除、修改或重跑任何业务数据。\n'
                    '如果数据不足，请说明需要用户进入对应页面复核。\n'
                    '回答使用中文，结构清晰，优先给出可执行的下一步建议。'
                ),
                'developer_prompt': None,
                'output_contract_json': (
                    '{"language":"zh-CN","must_use_tool_results_only":true,'
                    '"must_not_create_formal_compliance_conclusion":true,'
                    '"must_request_human_review_when_evidence_missing":true}'
                ),
                'risk_notes': '默认只读 Agent 提示词，禁止编造标准和正式合规结论。',
                'is_active': 1,
                'approved_by_id': None,
                'approved_at': now,
            }
        ],
    )


def downgrade() -> None:
    op.drop_index(op.f('ix_agent_prompts_scenario'), table_name='agent_prompts')
    op.drop_index(op.f('ix_agent_prompts_is_active'), table_name='agent_prompts')
    op.drop_index(op.f('ix_agent_prompts_deleted_at'), table_name='agent_prompts')
    op.drop_index(op.f('ix_agent_prompts_approved_by_id'), table_name='agent_prompts')
    op.drop_table('agent_prompts')
    agent_prompt_scenario.drop(op.get_bind(), checkfirst=True)
