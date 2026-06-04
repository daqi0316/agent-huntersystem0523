"""Model 公共工具 — 集中 enum 列定义，防止 SQLAlchemy 写库用错 label。

背景
----
SQLAlchemy 的 ``SAEnum(PythonEnumClass, name=...)`` **默认** 写库时使用
Python enum 的 ``name``（大写 PENDING/EXPIRED/...），与 PostgreSQL enum
type label 必须完全一致才会被接受。

如果 DB enum label 实际上是 enum 的 ``value``（小写 pending/expired/...），
写库会抛 ``InvalidTextRepresentationError``。

本项目的事实（已核实，2026-06-03）：
- ``approval_status`` / ``recommendation_type`` / ``candidate_status``
  DB label 均为小写
- 部分 model 漏写 ``values_callable`` 导致写入大写炸 500

统一规则
----
所有"value 是小写、name 是大写"的 Python ``str, Enum`` 列必须通过本文件
的 :func:`enum_column` 工厂创建，**禁止** 直接调用 ``SAEnum(EnumClass, ...)``。

不要直接调用 `SAEnum(EnumClass, name=...)`（会写入大写 name，DB label 小写则 500）。

要这样做：
    from app.models._base import enum_column
    enum_column(ApprovalStatus, "approval_status")
"""

from __future__ import annotations

from enum import Enum
from typing import TypeVar

from sqlalchemy import Enum as SAEnum

E = TypeVar("E", bound=Enum)


def enum_column(py_enum: type[E], name: str) -> SAEnum:
    """构造 SQLAlchemy enum 列，强制写库用 enum ``value``（小写）。

    Parameters
    ----------
    py_enum:
        继承 ``str, Enum`` 的 Python 枚举类。
    name:
        PostgreSQL enum type 名称（即 ``sa.Enum(..., name=...)`` 的 name）。

    Returns
    -------
    sqlalchemy.Enum
        可直接用于 ``mapped_column(..., enum_column(MyEnum, "my_enum"))``。

    Notes
    -----
    ``values_callable=lambda x: [e.value for e in x]`` 是关键。
    它告诉 SQLAlchemy 序列化时使用 enum 的 ``value``，而不是 ``name``。
    """
    if not (
        isinstance(py_enum, type)
        and issubclass(py_enum, Enum)
    ):
        raise TypeError(
            f"enum_column() 需要 Enum 子类，得到 {py_enum!r}"
        )
    return SAEnum(
        py_enum,
        name=name,
        values_callable=lambda members: [e.value for e in members],
    )
