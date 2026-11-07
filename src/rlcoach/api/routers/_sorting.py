"""Shared query sorting for API list endpoints."""

from typing import Any

from fastapi import HTTPException


def apply_sort(
    query: Any,
    model: Any,
    sort: str,
    allowed_fields: set[str],
    computed: dict[str, Any] | None = None,
) -> Any:
    """Apply validated ascending or descending sorting.

    A field sorts by the model column of that name, unless `computed` gives it
    an expression, such as a count from another table.
    """
    descending = sort.startswith("-")
    sort_field = sort[1:] if descending else sort
    if sort_field not in allowed_fields:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid sort field. Allowed: {sorted(allowed_fields)}",
        )

    order_col = (computed or {}).get(sort_field)
    if order_col is None:
        order_col = getattr(model, sort_field)
    return query.order_by(order_col.desc() if descending else order_col)
