"""
Сборка геометрии hatch-регионов из сегментов границы.

SSOT: единственное место, где boundary segments → массив декартовых точек.
Используется renderer'ом и export'ом.
"""

from __future__ import annotations

import numpy as np
from typing import Optional

from delta import math_utils
from delta.models import (
    ProjectData, HatchRegion,
    StraightSegment, LineRefSegment, CurveRefSegment,
)


def build_region_path(
    region: HatchRegion,
    project: ProjectData,
    is_inverted: bool,
) -> Optional[np.ndarray]:
    """
    Собирает замкнутый контур hatch-региона в декартовых координатах.

    Returns:
        np.ndarray shape (N, 2) — точки контура, или None при ошибке.
    """
    if not region.segments:
        return None

    comp_map = {c.uid: c for c in project.compositions}
    line_map = {ln.uid: ln for ln in project.lines}
    curve_map = {cl.uid: cl for cl in project.curve_lines}

    all_points: list[np.ndarray] = []

    for seg in region.segments:
        pts = _segment_to_points(seg, comp_map, line_map, curve_map, is_inverted)
        if pts is None or len(pts) == 0:
            return None
        all_points.append(pts)

    if not all_points:
        return None

    # Склеиваем: убираем дубликат на стыке (конец предыдущего = начало следующего)
    result = [all_points[0]]
    for arr in all_points[1:]:
        # Если первая точка следующего сегмента совпадает с последней предыдущего — пропускаем
        if np.allclose(result[-1][-1], arr[0], atol=1e-9):
            result.append(arr[1:])
        else:
            result.append(arr)

    path = np.vstack(result)

    if len(path) < 3:
        return None

    return path


def _segment_to_points(
    seg: object,
    comp_map: dict,
    line_map: dict,
    curve_map: dict,
    is_inverted: bool,
) -> Optional[np.ndarray]:
    """Преобразует один сегмент границы в массив декартовых точек."""

    if isinstance(seg, StraightSegment):
        try:
            p1 = math_utils.bary_to_cart(seg.start, is_inverted)
            p2 = math_utils.bary_to_cart(seg.end, is_inverted)
            return np.array([p1, p2])
        except (ValueError, ZeroDivisionError):
            return None

    elif isinstance(seg, LineRefSegment):
        line = line_map.get(seg.line_uid)
        if line is None:
            return None

        start_comp = comp_map.get(line.start_uid)
        end_comp = comp_map.get(line.end_uid)
        if start_comp is None or end_comp is None:
            return None

        try:
            p1 = math_utils.bary_to_cart(start_comp.composition, is_inverted)
            p2 = math_utils.bary_to_cart(end_comp.composition, is_inverted)
            pts = np.array([p1, p2])
            if seg.reverse:
                pts = pts[::-1]
            return pts
        except (ValueError, ZeroDivisionError):
            return None

    elif isinstance(seg, CurveRefSegment):
        cline = curve_map.get(seg.curve_uid)
        if cline is None:
            return None

        start_comp = comp_map.get(cline.start_uid)
        end_comp = comp_map.get(cline.end_uid)
        if start_comp is None or end_comp is None:
            return None

        try:
            p_start = math_utils.bary_to_cart(start_comp.composition, is_inverted)
            p_end = math_utils.bary_to_cart(end_comp.composition, is_inverted)

            guide_pts = [
                math_utils.bary_to_cart(gp.composition, is_inverted)
                for gp in cline.guide_points
            ]

            xs, ys = math_utils.fit_curve_through_points(
                p_start, guide_pts, p_end,
                poly_degree=cline.poly_degree,
                curve_mode=cline.curve_mode,
            )

            pts = np.column_stack([xs, ys])
            if seg.reverse:
                pts = pts[::-1]
            return pts
        except (ValueError, ZeroDivisionError, np.linalg.LinAlgError):
            return None

    return None
