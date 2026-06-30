"""
P2-3: 批量插入/更新工具

提供 pg_insert 风格的批量 upsert，兼容 SQLite（测试）和 PostgreSQL（生产）。
"""
import logging
from typing import Any, Iterable, List, Sequence

from sqlalchemy import Table
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)


async def batch_upsert(
    session: AsyncSession,
    table: Table,
    rows: Sequence[dict],
    conflict_keys: List[str],
    update_keys: List[str] = None,
) -> int:
    """
    批量 upsert（插入或更新）

    - PostgreSQL: pg_insert + on_conflict_do_update
    - SQLite: sqlite_insert + on_conflict_do_update（开发/测试）

    Args:
        session: AsyncSession
        table: SQLAlchemy Table 对象
        rows: 待插入的字典列表
        conflict_keys: 唯一索引列（用于判断冲突）
        update_keys: 冲突时要更新的列（默认全部非冲突列）

    Returns:
        影响的行数
    """
    if not rows:
        return 0

    if update_keys is None:
        # 默认更新所有非冲突列
        update_keys = [c.name for c in table.columns if c.name not in conflict_keys]

    # 检测 dialect
    bind = session.bind
    dialect_name = ""
    if bind is not None:
        dialect_name = bind.dialect.name

    if dialect_name == "postgresql":
        stmt = pg_insert(table).values(list(rows))
        stmt = stmt.on_conflict_do_update(
            index_elements=conflict_keys,
            set_={k: stmt.excluded[k] for k in update_keys},
        )
    else:
        # SQLite / 其他 → 用 sqlite_insert
        stmt = sqlite_insert(table).values(list(rows))
        stmt = stmt.on_conflict_do_update(
            index_elements=conflict_keys,
            set_={k: stmt.excluded[k] for k in update_keys},
        )

    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount or len(rows)


async def batch_insert(
    session: AsyncSession,
    table: Table,
    rows: Sequence[dict],
) -> int:
    """
    批量插入（无冲突处理）

    Returns:
        插入的行数
    """
    if not rows:
        return 0

    bind = session.bind
    dialect_name = ""
    if bind is not None:
        dialect_name = bind.dialect.name

    if dialect_name == "postgresql":
        stmt = pg_insert(table).values(list(rows))
    else:
        stmt = sqlite_insert(table).values(list(rows))

    result = await session.execute(stmt)
    await session.commit()
    return result.rowcount or len(rows)
