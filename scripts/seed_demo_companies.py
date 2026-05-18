"""
向 organizations 表插入若干演示公司（主键为 UUID v7，由 ORM 自动生成）。

用法（已建库且 alembic upgrade head）：
    pip install -r requirements.txt
    python scripts/seed_demo_companies.py

同一公司名称已存在则跳过，可重复执行。预置默认公司（config.default_organization_id）不由本脚本创建。
"""

from __future__ import annotations

import sys
from pathlib import Path

_root = Path(__file__).resolve().parent.parent
if str(_root) not in sys.path:
    sys.path.insert(0, str(_root))

from sqlalchemy import select  # noqa: E402

from app.core.config import settings  # noqa: E402
from app.core.db import SessionLocal  # noqa: E402
from app.models.db_models import Organization  # noqa: E402

# 测试上传评价任务时在 organization_id 里可填这些公司的 id（从输出复制）
DEMO_COMPANY_NAMES: tuple[str, ...] = (
    '演示公司-华东',
    '演示公司-华北',
    '演示公司-西南',
    '上海浦东有限公司',
)


def main() -> None:
    with SessionLocal() as session:
        created: list[tuple[str, str]] = []
        for name in DEMO_COMPANY_NAMES:
            stmt = select(Organization).where(Organization.name == name)
            existing = session.scalars(stmt, execution_options={'include_deleted': True}).one_or_none()
            if existing is not None:
                created.append((name, existing.id))
                continue
            org = Organization(name=name)
            session.add(org)
            session.flush()
            created.append((name, org.id))
        session.commit()

    print('以下公司已就绪（organization_id 填右侧 UUID）：\n')
    for name, oid in created:
        print(f'  {name}\n    {oid}\n')
    print(f'预置默认公司 id（init_db）：\n  {settings.default_organization_id}\n')


if __name__ == '__main__':
    main()
