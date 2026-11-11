"""pgvector column type (``vector(n)``) without an extra dependency.

Values travel as pgvector's text form (``[0.1,0.2,...]``) and are cast on the server, so the
driver never needs to know the type.
"""

from __future__ import annotations

from typing import Any
from typing import cast as typing_cast

from sqlalchemy import Float, cast
from sqlalchemy.sql.elements import ColumnElement
from sqlalchemy.types import UserDefinedType

# Fixed by migration 0007; changing it needs a migration and a full re-index (ADR-042).
EMBEDDING_DIMENSIONS = 1024


def to_literal(values: list[float]) -> str:
    return "[" + ",".join(repr(float(v)) for v in values) + "]"


def from_literal(value: str) -> list[float]:
    inner = value.strip()[1:-1]
    return [float(v) for v in inner.split(",")] if inner else []


class Vector(UserDefinedType[list[float]]):
    cache_ok = True

    def __init__(self, dimensions: int) -> None:
        self.dimensions = dimensions

    def get_col_spec(self, **_: Any) -> str:
        return f"vector({self.dimensions})"

    def bind_processor(self, dialect: Any) -> Any:
        def process(value: list[float] | None) -> str | None:
            return None if value is None else to_literal(value)

        return process

    def bind_expression(self, bindvalue: Any) -> Any:
        return cast(bindvalue, self)

    def result_processor(self, dialect: Any, coltype: Any) -> Any:
        def process(value: Any) -> list[float] | None:
            if value is None or isinstance(value, list):
                return value
            return from_literal(str(value))

        return process

    class comparator_factory(UserDefinedType.Comparator[list[float]]):
        def cosine_distance(self, other: Any) -> ColumnElement[float]:
            return typing_cast(ColumnElement[float], self.op("<=>", return_type=Float)(other))
