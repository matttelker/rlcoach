"""Sorting a list endpoint by a field the caller names."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException


def sort_by(query: Any, sort: str, columns: dict[str, Any]) -> Any:
    """Order by one of `columns`, named as "field" or "-field" for descending."""
    name = sort.removeprefix("-")
    if name not in columns:
        raise HTTPException(
            status_code=400, detail=f"Invalid sort field. Allowed: {sorted(columns)}"
        )
    column = columns[name]
    return query.order_by(column.desc() if sort.startswith("-") else column)
