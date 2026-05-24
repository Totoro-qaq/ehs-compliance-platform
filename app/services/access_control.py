"""
水平越权（IDOR）防护：在 Service 层按「公司范围 + 创建者」做强校验。

IDOR（Insecure Direct Object Reference）：攻击者篡改 URL / body 中的 id，
访问本不属于自己租户或不是自己创建的数据。仅靠「猜不到 UUID」不算防御。

防御要点：
1. 不信任客户端传来的 organization_id：普通用户强制用令牌中的租户。
2. 读/写任意资源前，用数据库主键加载资源后校验 resource.organization_id 与用户一致。
3. 敏感写操作可叠加 created_by_id == 当前账号（同租户内的二次隔离）。
"""

from __future__ import annotations

from app.core.exceptions import EHSException
from app.models.db_models import AccountRole, AssessmentTask
from app.schemas.auth_context import CurrentUser


def is_system_admin(actor: CurrentUser) -> bool:
    return actor.role == AccountRole.ADMIN


def is_org_admin(actor: CurrentUser) -> bool:
    return actor.role == AccountRole.ORG_ADMIN


def ensure_admin(actor: CurrentUser) -> None:
    """Require the system-level administrator role."""
    if not is_system_admin(actor):
        raise EHSException(
            '需要管理员权限',
            code='FORBIDDEN',
            status_code=403,
            details={'reason': 'ADMIN_ROLE_REQUIRED'},
        )


def ensure_org_admin_or_system_admin(actor: CurrentUser, organization_id: str) -> None:
    if is_system_admin(actor):
        return
    if is_org_admin(actor):
        ensure_organization_scope(actor, organization_id)
        return
    raise EHSException(
        '需要公司管理员权限',
        code='FORBIDDEN',
        status_code=403,
        details={'reason': 'ORG_ADMIN_ROLE_REQUIRED'},
    )


def ensure_user_has_organization(actor: CurrentUser) -> str:
    """普通业务用户须绑定 organization_id；管理员在公司隔离函数中提前 return，不会调用本函数。"""
    if not actor.organization_id:
        raise EHSException(
            '账号未绑定公司，请联系管理员',
            code='ACCOUNT_NO_ORG',
            status_code=403,
            details={'reason': 'USER_ORG_REQUIRED'},
        )
    return actor.organization_id


def ensure_organization_scope(actor: CurrentUser, resource_organization_id: str) -> None:
    """
    公司级水平隔离：非管理员仅能访问本公司数据。
    违反时 403，与统一 Envelope + EHSException 一致。
    """
    if is_system_admin(actor):
        return
    uid_org = ensure_user_has_organization(actor)
    if resource_organization_id != uid_org:
        raise EHSException(
            '禁止访问该资源（公司范围不匹配，疑似水平越权）',
            code='IDOR_ORG_MISMATCH',
            status_code=403,
            details={
                'hint': '请求的资源不属于当前登录账号所属公司',
            },
        )


def ensure_client_org_id_allowed(
    actor: CurrentUser,
    *,
    requested_organization_id: str,
) -> None:
    """
    防止客户端伪造 organization_id：普通用户仅允许操作本人所属公司。
    """
    if is_system_admin(actor):
        return
    uid_org = ensure_user_has_organization(actor)
    if requested_organization_id != uid_org:
        raise EHSException(
            '禁止为该公司创建或查询资源（公司不匹配）',
            code='IDOR_ORG_FORGE',
            status_code=403,
            details={'hint': '普通用户不能使用不属于本公司的 organization_id'},
        )


def ensure_task_author_for_mutation(actor: CurrentUser, task: AssessmentTask) -> None:
    """
    在同公司内，普通用户仅能删除/变更自己创建的评价任务；管理员不受限。
    """
    ensure_organization_scope(actor, task.organization_id)
    if is_system_admin(actor) or is_org_admin(actor):
        return
    if task.created_by_id is None:
        raise EHSException(
            '该任务缺少创建者信息，无法校验权限',
            code='TASK_NO_AUTHOR',
            status_code=403,
            details={'task_id': task.id},
        )
    if task.created_by_id != actor.account_id:
        raise EHSException(
            '禁止操作该评价任务（非任务创建者）',
            code='IDOR_AUTHOR_MISMATCH',
            status_code=403,
            details={'hint': '同公司内仅创建者可执行此操作', 'task_id': task.id},
        )
