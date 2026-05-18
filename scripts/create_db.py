"""创建 MySQL 库 ehs_system（不建表；表由 alembic 负责）。"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import pymysql

from app.core.config import settings

SQL = (
    'CREATE DATABASE IF NOT EXISTS '
    f'`{settings.mysql_db}` '
    'DEFAULT CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci'
)


def main() -> None:
    conn = pymysql.connect(
        host=settings.mysql_host,
        port=settings.mysql_port,
        user=settings.mysql_user,
        password=settings.mysql_password,
    )
    try:
        with conn.cursor() as cur:
            cur.execute(SQL)
        conn.commit()
    finally:
        conn.close()
    print('数据库已就绪:', settings.mysql_db)


if __name__ == '__main__':
    main()
