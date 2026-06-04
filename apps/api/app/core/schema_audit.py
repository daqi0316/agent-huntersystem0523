"""启动时 schema 审计 — 防止 model 声明与 DB 实际不一致。

**触发场景**：2026-06-03 生产事故。``approval_status`` / ``recommendation_type``
等 PostgreSQL enum 的 DB label 实际是小写（``pending/expired/...``），但
SQLAlchemy ``SAEnum(MyEnum, name=...)`` 写库默认用 enum ``name``（``PENDING/...``），
不一致 → ``InvalidTextRepresentationError`` 500。

**防护**：app 启动时遍历所有 ``Base.metadata`` 的 enum 列，调用
``Enum._db_value_for_elem(member)`` 拿到"SQLAlchemy 实际写入 DB 的字符串"，
对比 ``pg_enum`` 实际 label。**不一致 → 抛 RuntimeError 阻止启动**。

防再发：
- 模型层用 ``enum_column()`` 工厂（强制 ``values_callable``，写 value）
- 静态扫描 ``scripts/check_model_patterns.py``（pre-commit hook）
- **本模块是 L2 启动期护栏**（L1 编译期失效时的兜底）
"""

from __future__ import annotations

import logging
from typing import Iterable

from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.core.database import Base, engine
from app.models import *  # noqa: F401,F403  # 触发 model 注册到 Base.metadata

logger = logging.getLogger(__name__)


def _iter_enum_columns() -> Iterable[tuple[str, str, str, type, list[str]]]:
    """遍历 Base.metadata 所有 enum 列。

    Yields
    ------
    (table_name, column_name, db_type_name, enum_class, declared_values)
        declared_values: SQLAlchemy 实际写入 DB 的字符串列表（按定义顺序）
    """
    for table in Base.metadata.sorted_tables:
        for col in table.columns:
            col_type = col.type
            # 仅 SAEnum (sa.Enum) 类
            if not hasattr(col_type, "enum_class") or col_type.enum_class is None:
                continue
            enum_cls = col_type.enum_class
            # SAEnum.name 是 PostgreSQL enum type 名称（字符串），直接用
            db_type_name = getattr(col_type, "name", None) or col.name
            # 拿 SQLAlchemy 实际写入 DB 的字符串（用 _db_value_for_elem 抽象出 name/value 之别）
            try:
                values = [col_type._db_value_for_elem(m) for m in enum_cls]
            except Exception as e:  # pragma: no cover - SA 内部 API 变化
                logger.warning(
                    "schema_audit: skip %s.%s — _db_value_for_elem failed: %s",
                    table.name, col.name, e,
                )
                continue
            yield table.name, col.name, db_type_name, enum_cls, values


async def audit_db_consistency(
    *,
    fail_on_mismatch: bool = True,
    engine_arg=None,
) -> list[str]:
    """对比 model 声明的 enum 写入值与 DB pg_enum label。

    Returns
    -------
    list[str]
        错误描述列表。空列表 = 一致。

    Raises
    ------
    RuntimeError
        当 ``fail_on_mismatch=True`` 且发现不一致。
        阻止应用启动，防止生产 500 静默爆发。
    """
    issues: list[str] = []

    declared_map: dict[str, tuple[str, str, list[str]]] = {}
    for table_name, col_name, db_type_name, enum_cls, values in _iter_enum_columns():
        declared_map[db_type_name] = (table_name, col_name, values)

    if not declared_map:
        logger.info("schema_audit: no enum columns found in metadata, skipping")
        return []

    try:
        eng = engine_arg or engine
        async with eng.connect() as conn:
            for db_type_name, (table_name, col_name, declared) in declared_map.items():
                # 用 SAVEPOINT 隔离每个 enum 查询，单个失败不污染 connection 事务状态
                savepoint = await conn.begin_nested()
                try:
                    rows = await conn.execute(
                        text(
                            "SELECT enumlabel FROM pg_enum "
                            "WHERE enumtypid = CAST(:name AS regtype) ORDER BY enumsortorder"
                        ),
                        {"name": db_type_name},
                    )
                    db_labels = [r[0] for r in rows.fetchall()]
                    await savepoint.commit()
                except SQLAlchemyError as e:
                    await savepoint.rollback()
                    # 单个 enum 不存在（表未建）→ 仅跳过这一个，继续下一个
                    logger.warning(
                        "schema_audit: skip %s (%s.%s) — DB type missing: %s",
                        db_type_name, table_name, col_name, e,
                    )
                    continue

                declared_set = set(declared)
                db_set = set(db_labels)

                if declared_set == db_set:
                    logger.info(
                        "schema_audit: %s OK (%s.%s) %d values",
                        db_type_name, table_name, col_name, len(declared),
                    )
                    continue

                # 报告具体差异
                only_in_model = declared_set - db_set
                only_in_db = db_set - declared_set
                msg = (
                    f"enum drift: {db_type_name} ({table_name}.{col_name}) — "
                    f"only in model: {sorted(only_in_model)}; "
                    f"only in db: {sorted(only_in_db)}"
                )
                issues.append(msg)
                logger.error("schema_audit: " + msg)
    except SQLAlchemyError as e:
        logger.warning("schema_audit: DB unreachable, skipping consistency check: %s", e)
        return []

    if issues and fail_on_mismatch:
        joined = "\n".join(issues)
        raise RuntimeError(
            "Schema drift detected on startup — DB enum labels do not match model:\n"
            + joined
            + "\n\nFix: change DB label (ALTER TYPE ... RENAME VALUE) or update model enum "
            "class values to match. See .omo/plans/decision-records/2026-06-03-enum-and-uuid-pattern.md"
        )

    return issues


async def audit_required_tables(
    fail_on_mismatch: bool = False,
    *,
    engine_arg=None,
) -> list[str]:
    """启动时检查所有 ``Base.metadata`` 表是否在 DB 存在。

    **触发场景**：2026-06-03 后端僵死事故。``OperationStatsHourly`` model
    已定义但 alembic 缺 migration，DB 无表。``aggregation_loop`` 和
    ``/dashboard/operations/{summary,trend}`` 每次读表抛
    ``UndefinedTableError``，asyncpg 连接累积泄漏到 pool 耗尽（30 个连接），
    所有 endpoint 卡死。

    **本审计**：用 ``pg_class`` 系统表查询（不触发 ORM session），
    表缺失只 log warn，**不阻止启动**（dev 早期允许），但聚合后台任务
    会拿不到表 → 需跑 ``alembic upgrade head``。

    L4 防再发：
    - 模型层用 alembic migration 同步（手动 SQL 补建会被此审计发现）
    - ``aggregation_loop`` 启动时再检查一次（纵深防御）
    - 单端点 try/except 优雅降级（dashboard.py L1.1/L1.2）

    Parameters
    ----------
    fail_on_mismatch:
        True → 表缺失时抛 RuntimeError 阻止启动（生产严格模式）
        False（默认）→ 仅 log warn，dev 早期允许（dashboard 端点有 L1 兜底）

        对照 ``audit_db_consistency`` 默认 ``True``（enum drift 必爆故 fail），
        本函数默认 ``False``（表缺失有 L1 优雅降级兜底故 warn）。
        两 audit 默认值不同是**有意设计**。
    """
    expected = [t.name for t in Base.metadata.sorted_tables]
    if not expected:
        return []

    try:
        eng = engine_arg or engine
        async with eng.connect() as conn:
            rows = await conn.execute(
                text(
                    "SELECT relname FROM pg_class "
                    "WHERE relkind IN ('r', 'p') AND relname = ANY(:names)"
                ),
                {"names": expected},
            )
            existing = {r[0] for r in rows.fetchall()}
    except SQLAlchemyError as e:
        logger.warning("schema_audit: required-tables check skipped (DB unreachable): %s", e)
        return []

    missing = sorted(set(expected) - existing)
    if missing:
        for name in missing:
            logger.warning(
                "schema_audit: 表 %s 在 model 声明但 DB 不存在。"
                "运行 `alembic upgrade head` 建表，或临时 dashboard 端点会返 mock。",
                name,
            )
        if fail_on_mismatch:
            raise RuntimeError(
                f"Required tables missing in DB: {missing}. "
                f"Run `alembic upgrade head` to apply migrations."
            )
    else:
        logger.info("schema_audit: all %d expected tables exist in DB", len(expected))
    return missing
