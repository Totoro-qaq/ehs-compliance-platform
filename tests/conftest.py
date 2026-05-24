"""pytest 配置与共享 fixtures：内存 SQLite + FastAPI TestClient。"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, event
from sqlalchemy.orm import Session, sessionmaker, with_loader_criteria
from sqlalchemy.pool import StaticPool

from app.core.config import settings
from app.core.db import get_db
from app.models.base import Base, ModelBase

_TEST_ENGINE = create_engine(
    'sqlite://',
    connect_args={'check_same_thread': False},
    poolclass=StaticPool,
)


# 复制生产环境的软删除过滤器到测试 session
@event.listens_for(Session, 'do_orm_execute', propagate=True)
def _test_soft_delete_filter(orm_execute_state):
    if not orm_execute_state.is_select:
        return
    if orm_execute_state.execution_options.get('include_deleted', False):
        return
    orm_execute_state.statement = orm_execute_state.statement.options(
        with_loader_criteria(
            ModelBase,
            lambda cls: cls.deleted_at.is_(None),
            propagate_to_loaders=True,
            track_closure_variables=False,
        )
    )


TestSessionLocal = sessionmaker(
    bind=_TEST_ENGINE, autoflush=False, autocommit=False, expire_on_commit=False
)


# 在模块加载阶段就把生产 SessionLocal 替换为内存 sqlite 版本：
# 部分测试（如 worker 任务测试）绕开 FastAPI dependency_overrides，直接调用
# app.core.db.SessionLocal，CI 中没有 MySQL 服务会失败。
# 这里在 conftest 加载完成（早于任何测试模块 import）时就覆盖，
# 比 autouse fixture 更可靠（避免 fixture 执行顺序问题）。
import app.core.db as _core_db_module  # noqa: E402
import app.tasks.worker as _worker_module  # noqa: E402

_core_db_module.SessionLocal = TestSessionLocal
_worker_module.SessionLocal = TestSessionLocal


@pytest.fixture(scope='session', autouse=True)
def _create_tables():
    Base.metadata.create_all(bind=_TEST_ENGINE)
    yield
    Base.metadata.drop_all(bind=_TEST_ENGINE)


@pytest.fixture(autouse=True)
def _disable_captcha_for_unit_tests(monkeypatch):
    """单测默认不依赖 Redis 验证码；需要覆盖验证码行为的测试可重新设为 True。"""
    monkeypatch.setattr(settings, 'auth_captcha_required', False)


@pytest.fixture()
def db():
    """每个测试用例独立事务，结束后回滚。"""
    connection = _TEST_ENGINE.connect()
    transaction = connection.begin()
    session = TestSessionLocal(bind=connection)
    yield session
    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture()
def client(db: Session):
    """FastAPI TestClient，注入测试数据库 session。"""
    from main import app

    def _override_get_db():
        yield db

    app.dependency_overrides[get_db] = _override_get_db
    with TestClient(app, raise_server_exceptions=False) as c:
        yield c
    app.dependency_overrides.clear()


@pytest.fixture()
def admin_token(db: Session) -> str:
    """创建测试管理员并返回 JWT token。"""
    from app.core.security import hash_password
    from app.models.db_models import Account, AccountRole, Organization

    # 确保默认公司存在（assessment 接口依赖）
    org = db.get(Organization, settings.default_organization_id)
    if org is None:
        org = Organization(id=settings.default_organization_id, name='默认测试公司')
        db.add(org)
        db.flush()

    admin = Account(
        username='testadmin',
        password_hash=hash_password('Admin123x'),
        role=AccountRole.ADMIN,
        organization_id=org.id,
        email='admin@test.com',
        phone='13800000001',
    )
    db.add(admin)
    db.flush()

    from app.services.auth_service import create_access_token

    token = create_access_token(
        username=admin.username,
        role=admin.role.value,
        account_id=admin.id,
        organization_id=admin.organization_id,
    )
    return token.access_token


@pytest.fixture()
def user_token(db: Session) -> str:
    """创建测试普通用户并返回 JWT token。"""
    from app.core.security import hash_password
    from app.models.db_models import Account, AccountRole, Organization

    org = db.get(Organization, settings.default_organization_id)
    if org is None:
        org = Organization(id=settings.default_organization_id, name='默认测试公司')
        db.add(org)
        db.flush()

    user = Account(
        username='testuser',
        password_hash=hash_password('User1234x'),
        role=AccountRole.USER,
        organization_id=org.id,
        email='user@test.com',
        phone='13800000002',
    )
    db.add(user)
    db.flush()

    from app.services.auth_service import create_access_token

    token = create_access_token(
        username=user.username,
        role=user.role.value,
        account_id=user.id,
        organization_id=user.organization_id,
    )
    return token.access_token


@pytest.fixture()
def org_admin_token(db: Session) -> str:
    """创建测试公司管理员并返回 JWT token。"""
    from app.core.security import hash_password
    from app.models.db_models import Account, AccountRole, Organization

    org = db.get(Organization, settings.default_organization_id)
    if org is None:
        org = Organization(id=settings.default_organization_id, name='默认测试公司')
        db.add(org)
        db.flush()

    org_admin = Account(
        username='testorgadmin',
        password_hash=hash_password('OrgAdmin123x'),
        role=AccountRole.ORG_ADMIN,
        organization_id=org.id,
        email='orgadmin@test.com',
        phone='13800000003',
    )
    db.add(org_admin)
    db.flush()

    from app.services.auth_service import create_access_token

    token = create_access_token(
        username=org_admin.username,
        role=org_admin.role.value,
        account_id=org_admin.id,
        organization_id=org_admin.organization_id,
    )
    return token.access_token
