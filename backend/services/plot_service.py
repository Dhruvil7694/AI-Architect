from __future__ import annotations

import re
from typing import Iterable, Tuple, Optional

from django.db.models import Q

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


def _tp_scheme_candidates(tp_scheme: str) -> set[str]:
    value = tp_scheme.strip()
    if not value:
        return set()

    digits = "".join(ch for ch in value if ch.isdigit())
    collapsed = re.sub(r"[\s_-]+", "", value)

    candidates = {
        value,
        value.upper(),
        value.lower(),
        collapsed,
        collapsed.upper(),
        collapsed.lower(),
    }

    if digits:
        candidates.update(
            {
                digits,
                f"TP{digits}",
                f"tp{digits}",
                f"TP-{digits}",
                f"tp-{digits}",
                f"TP {digits}",
                f"tp {digits}",
            }
        )

    return {candidate for candidate in candidates if candidate}


def build_tp_scheme_query(tp_scheme: str, field_name: str = "tp_scheme") -> Q:
    cleaned = tp_scheme.strip()
    if not cleaned:
        return Q()

    query = Q(**{f"{field_name}__iexact": cleaned})
    candidates = _tp_scheme_candidates(cleaned)
    if candidates:
        query |= Q(**{f"{field_name}__in": sorted(candidates)})
    return query


def get_plot_by_public_id(plot_id: str) -> Plot:
    """
    Resolve a Plot instance given the public id used by the frontend.
    """
    tp_scheme, fp = _parse_public_plot_id(plot_id)
    try:
        return Plot.objects.get(tp_scheme=tp_scheme, fp_number=fp)
    except Plot.DoesNotExist:
        return Plot.objects.get(build_tp_scheme_query(tp_scheme), fp_number=fp)


def list_plots(
    *,
    tp_scheme: Optional[str] = None,
    city: Optional[str] = None,
    search: Optional[str] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
) -> Tuple[Iterable[Plot], int]:
    """
    Return a slice of Plot rows plus total count.

    - tp_scheme/city: optional filters (tp is normalized/case-insensitive, city is case-insensitive).
    - search: case-insensitive substring match on tp_scheme or fp_number.
    - limit/offset: optional manual pagination.
    """
    qs = Plot.objects.all()

    if tp_scheme:
        qs = qs.filter(build_tp_scheme_query(tp_scheme))
    if city:
        qs = qs.filter(city__iexact=city.strip())

    if search:
        qs = qs.filter(
            Q(fp_number__icontains=search) | Q(tp_scheme__icontains=search)
        )

    qs = qs.order_by("-area_geometry", "tp_scheme", "fp_number")

    total = qs.count()

    if offset is not None and offset > 0:
        qs = qs[offset:]
    if limit is not None and limit >= 0:
        qs = qs[:limit]

    return qs, total


__all__ = [
    "build_tp_scheme_query",
    "get_plot_by_public_id",
    "list_plots",
]

