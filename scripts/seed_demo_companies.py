"""
Seed demo tenant companies and accounts.

This script only writes demo rows to MySQL through the application models. It does not scan,
upload, parse, or import standard/source documents.

Usage:
    python scripts/seed_demo_companies.py
    python scripts/seed_demo_companies.py --reset-passwords
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import select

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from app.core.config import settings  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.core.security import hash_password  # noqa: E402
from app.models.db_models import Account, AccountRole, Organization  # noqa: E402

DEMO_PASSWORD = 'DemoPass123'


@dataclass(frozen=True, slots=True)
class DemoAccount:
    username: str
    role: AccountRole
    email: str
    phone: str
    label: str


@dataclass(frozen=True, slots=True)
class DemoTenant:
    name: str
    unified_social_credit_code: str
    industry: str
    address: str
    contact_name: str
    contact_phone: str
    notes: str
    accounts: tuple[DemoAccount, DemoAccount]


DEMO_TENANTS: tuple[DemoTenant, ...] = (
    DemoTenant(
        name='演示-华东安测检测有限公司',
        unified_social_credit_code='91310000DEMO0001X1',
        industry='第三方检测机构',
        address='上海市浦东新区演示路 100 号',
        contact_name='赵机构',
        contact_phone='13800001001',
        notes='Demo tenant: third-party occupational health and environmental testing agency.',
        accounts=(
            DemoAccount(
                username='hdtest_admin',
                role=AccountRole.ORG_ADMIN,
                email='hdtest_admin@example.local',
                phone='13800002001',
                label='公司管理员',
            ),
            DemoAccount(
                username='hdtest_user',
                role=AccountRole.USER,
                email='hdtest_user@example.local',
                phone='13800002002',
                label='公司员工',
            ),
        ),
    ),
    DemoTenant(
        name='演示-北方职业卫生检测中心',
        unified_social_credit_code='91110000DEMO0002X2',
        industry='第三方检测机构',
        address='北京市朝阳区演示街 88 号',
        contact_name='钱机构',
        contact_phone='13800001002',
        notes='Demo tenant: occupational health testing service provider.',
        accounts=(
            DemoAccount(
                username='bftest_admin',
                role=AccountRole.ORG_ADMIN,
                email='bftest_admin@example.local',
                phone='13800002003',
                label='公司管理员',
            ),
            DemoAccount(
                username='bftest_user',
                role=AccountRole.USER,
                email='bftest_user@example.local',
                phone='13800002004',
                label='公司员工',
            ),
        ),
    ),
    DemoTenant(
        name='演示-南方环境安全技术服务有限公司',
        unified_social_credit_code='91440000DEMO0003X3',
        industry='第三方检测机构',
        address='广州市天河区演示大道 66 号',
        contact_name='孙机构',
        contact_phone='13800001003',
        notes='Demo tenant: environmental and safety technical service agency.',
        accounts=(
            DemoAccount(
                username='nfsafety_admin',
                role=AccountRole.ORG_ADMIN,
                email='nfsafety_admin@example.local',
                phone='13800002005',
                label='公司管理员',
            ),
            DemoAccount(
                username='nfsafety_user',
                role=AccountRole.USER,
                email='nfsafety_user@example.local',
                phone='13800002006',
                label='公司员工',
            ),
        ),
    ),
    DemoTenant(
        name='演示-海州精密制造有限公司',
        unified_social_credit_code='91320000DEMO0004X4',
        industry='制造业企业',
        address='苏州市工业园区演示路 18 号',
        contact_name='李企业',
        contact_phone='13800001004',
        notes='Demo tenant: manufacturing enterprise client.',
        accounts=(
            DemoAccount(
                username='haizhou_admin',
                role=AccountRole.ORG_ADMIN,
                email='haizhou_admin@example.local',
                phone='13800002007',
                label='公司管理员',
            ),
            DemoAccount(
                username='haizhou_user',
                role=AccountRole.USER,
                email='haizhou_user@example.local',
                phone='13800002008',
                label='公司员工',
            ),
        ),
    ),
    DemoTenant(
        name='演示-星河化工科技有限公司',
        unified_social_credit_code='91330000DEMO0005X5',
        industry='化工企业',
        address='宁波市化工园区演示西路 9 号',
        contact_name='周企业',
        contact_phone='13800001005',
        notes='Demo tenant: chemical enterprise client.',
        accounts=(
            DemoAccount(
                username='xinghe_admin',
                role=AccountRole.ORG_ADMIN,
                email='xinghe_admin@example.local',
                phone='13800002009',
                label='公司管理员',
            ),
            DemoAccount(
                username='xinghe_user',
                role=AccountRole.USER,
                email='xinghe_user@example.local',
                phone='13800002010',
                label='公司员工',
            ),
        ),
    ),
    DemoTenant(
        name='演示-绿源电子材料有限公司',
        unified_social_credit_code='91420000DEMO0006X6',
        industry='电子材料企业',
        address='武汉市东湖高新区演示东路 36 号',
        contact_name='吴企业',
        contact_phone='13800001006',
        notes='Demo tenant: electronics material enterprise client.',
        accounts=(
            DemoAccount(
                username='lvyuan_admin',
                role=AccountRole.ORG_ADMIN,
                email='lvyuan_admin@example.local',
                phone='13800002011',
                label='公司管理员',
            ),
            DemoAccount(
                username='lvyuan_user',
                role=AccountRole.USER,
                email='lvyuan_user@example.local',
                phone='13800002012',
                label='公司员工',
            ),
        ),
    ),
)


def _upsert_organization(session, tenant: DemoTenant) -> Organization:
    existing = session.scalars(
        select(Organization).where(Organization.name == tenant.name),
        execution_options={'include_deleted': True},
    ).one_or_none()
    if existing is None:
        org = Organization(name=tenant.name)
        session.add(org)
    else:
        org = existing

    org.name = tenant.name
    org.unified_social_credit_code = tenant.unified_social_credit_code
    org.industry = tenant.industry
    org.address = tenant.address
    org.contact_name = tenant.contact_name
    org.contact_phone = tenant.contact_phone
    org.notes = tenant.notes
    org.deleted_at = None
    session.flush()
    return org


def _upsert_account(
    session,
    *,
    account: DemoAccount,
    organization_id: str,
    reset_passwords: bool,
) -> tuple[Account, bool, bool]:
    existing = session.scalars(
        select(Account).where(Account.username == account.username),
        execution_options={'include_deleted': True},
    ).one_or_none()
    created = existing is None
    password_reset = created or reset_passwords

    if existing is None:
        existing = Account(username=account.username, password_hash=hash_password(DEMO_PASSWORD))
        session.add(existing)
    elif reset_passwords:
        existing.password_hash = hash_password(DEMO_PASSWORD)

    existing.role = account.role
    existing.organization_id = organization_id
    existing.email = account.email
    existing.phone = account.phone
    existing.deleted_at = None
    session.flush()
    return existing, created, password_reset


def seed(reset_passwords: bool = False) -> None:
    rows: list[tuple[str, str, DemoAccount, bool, bool]] = []
    with SessionLocal() as session:
        for tenant in DEMO_TENANTS:
            org = _upsert_organization(session, tenant)
            for demo_account in tenant.accounts:
                _, created, password_reset = _upsert_account(
                    session,
                    account=demo_account,
                    organization_id=org.id,
                    reset_passwords=reset_passwords,
                )
                rows.append((tenant.name, org.id, demo_account, created, password_reset))
        session.commit()

    print('Seeded demo companies and accounts.')
    print('No standard documents were scanned, uploaded, parsed, or imported.')
    print(f'System admin remains role=ADMIN. Bootstrap username: {settings.bootstrap_admin_username}')
    print(f'Demo password for newly created/reset accounts: {DEMO_PASSWORD}\n')
    for company_name, org_id, account, created, password_reset in rows:
        state = 'created' if created else 'updated'
        pwd = DEMO_PASSWORD if password_reset else '(existing password kept)'
        print(
            f'{company_name}\n'
            f'  organization_id: {org_id}\n'
            f'  {account.label}: {account.username} / {pwd} / role={account.role.value} [{state}]\n'
        )


def main() -> None:
    parser = argparse.ArgumentParser(description='Seed demo tenant companies and demo accounts.')
    parser.add_argument(
        '--reset-passwords',
        action='store_true',
        help='Reset existing demo accounts to the demo password.',
    )
    args = parser.parse_args()
    seed(reset_passwords=args.reset_passwords)


if __name__ == '__main__':
    main()
