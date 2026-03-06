from __future__ import annotations

from typing import Iterable, Tuple, Optional

from tp_ingestion.models import Plot


def _parse_public_plot_id(plot_id: str) -> Tuple[str, str]:
    """
    Parse the public plot id used by the frontend into (tp_scheme, fp_number).

    Convention: "{tp_scheme}-{fp_number}", e.g. "TP14-152".
    """
    parts = plot_id.strip().split("-", 1)
    if len(parts) != 2:
        raise ValueError(f"Invalid plot id format: {plot_id!r}")
    tp_scheme, fp = parts[0].strip(), parts[1].strip()
    if not tp_scheme or not fp:
        raise ValueError(f"Invalid plot id format: {plot_id!r}")
    return tp_scheme, fp


def get_plot_by_public_id(plot_id: str) -> Plot:
    """
    Resolve a Plot instance given the public id used by the frontend.
    """
    tp_scheme, fp = _parse_public_plot_id(plot_id)
    return Plot.objects.get(tp_scheme=tp_scheme, fp_number=fp)


def list_plots(
    *,
    search: Optional[str] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
) -> Tuple[Iterable[Plot], int]:
    """
    Return a slice of Plot rows plus total count.

    - search: case-insensitive substring match on tp_scheme or fp_number.
    - limit/offset: optional manual pagination.
    """
    qs = Plot.objects.all().order_by("-area_geometry", "tp_scheme", "fp_number")

    if search:
        qs = qs.filter(fp_number__icontains=search) | qs.filter(
            tp_scheme__icontains=search
        )

    total = qs.count()

    if offset is not None and offset > 0:
        qs = qs[offset:]
    if limit is not None and limit >= 0:
        qs = qs[:limit]

    return qs, total


__all__ = [
    "get_plot_by_public_id",
    "list_plots",
]

