import numpy as np
import matplotlib.patheffects as path_effects
from matplotlib.axes import Axes
from matplotlib.lines import Line2D
from matplotlib.patches import PathPatch
from matplotlib.path import Path
from typing import List, Literal
from delta import math_utils
from delta.models import ProjectData, RenderOverlay, Composition, ArrowSettings
from delta.constants import (
    COLOR_BACKGROUND, COLOR_TERNARY_TRIANGLE, COLOR_PROJECTION,
    COLOR_INTERSECTION, ZORDER_GRID, ZORDER_LINES, ZORDER_COMPS,
    ZORDER_MASK, ZORDER_OVERLAY, ZORDER_PROJECTION, ZORDER_INTERSECTION,
    VERTEX_LABEL_OFFSET, COMP_LABEL_OFFSET, TRIANGLE_HEIGHT
)

# Константы отрисовки
FONT_SIZE = 10
BORDER_WIDTH = 2
GRID_LINE_WIDTH = 1

def get_highlight_effect():
    return [
        path_effects.Stroke(linewidth=5, foreground="orange"),
        path_effects.Normal(),
    ]

class ProjectRenderer:
    """Отвечает за отрисовку статики и динамики на Axes"""
    
    def __init__(self, ax: Axes):
        self.ax = ax
        self._line_artists: dict[str, Line2D] = {}
        self._cached_overlay_uids: set[str] = set()
        self._aspect_mode: Literal['equal', 'auto'] = 'equal'

    def set_aspect_mode(self, mode: Literal['equal', 'auto']) -> None:
        """Устанавливает режим пропорций: 'equal' или 'auto'"""
        self._aspect_mode = mode

    def clear(self):
        self.ax.clear()
        self.ax.set_aspect(self._aspect_mode)               # ◄ ИЗМЕНЕНО
        self.ax.set_facecolor(COLOR_BACKGROUND)
        self._line_artists.clear()

    def draw_static_project(self, project: ProjectData, highlight_uids: list[str] | None = None):
        """Полная перерисовка проекта"""
        self.clear()
        is_inv = project.is_inverted
        
        # 1. Треугольник
        v_a, v_b, v_c = math_utils.get_vertices(is_inv)
        self.ax.plot([v_a[0], v_b[0]], [v_a[1], v_b[1]], 'k-', lw=BORDER_WIDTH)
        self.ax.plot([v_a[0], v_c[0]], [v_a[1], v_c[1]], 'k-', lw=BORDER_WIDTH)
        self.ax.plot([v_b[0], v_c[0]], [v_b[1], v_c[1]], 'k-', lw=BORDER_WIDTH)

        # 2. Сетка
        if project.grid.visible:
            self._draw_grid(project.grid.step, is_inv)

        # 3. Прямые линии (TieLine)
        comp_map = {p.uid: p for p in project.compositions}
        for line in project.lines:
            start = comp_map.get(line.start_uid)
            end = comp_map.get(line.end_uid)
            if start and end:
                p1 = math_utils.bary_to_cart(start.composition, is_inv)
                p2 = math_utils.bary_to_cart(end.composition, is_inv)
                xs = np.linspace(p1[0], p2[0], 300)
                ys = np.linspace(p1[1], p2[1], 300)

                mpl_line, = self.ax.plot(
                    xs, ys,
                    color=line.style.color,
                    linestyle=line.style.line_style,
                    lw=line.style.size,
                    picker=True,
                    pickradius=5,
                    zorder=ZORDER_LINES
                )
                self._line_artists[line.uid] = mpl_line

                if line.arrow.enabled:
                    self._draw_arrows_on_path(
                        xs, ys, line.arrow,
                        line.style.color, line.style.size
                    )

        # 3b. Кривые линии (CurveLine)
        for cline in project.curve_lines:
            start = comp_map.get(cline.start_uid)
            end = comp_map.get(cline.end_uid)
            if not start or not end:
                continue

            p_start = math_utils.bary_to_cart(start.composition, is_inv)
            p_end = math_utils.bary_to_cart(end.composition, is_inv)
            guide_pts = [
                math_utils.bary_to_cart(gp.composition, is_inv)
                for gp in cline.guide_points
            ]

            try:
                xs, ys = math_utils.fit_curve_through_points(
                    p_start, guide_pts, p_end,
                    poly_degree=cline.poly_degree,
                )
            except Exception:
                # Fallback: прямая линия
                xs = np.linspace(p_start[0], p_end[0], 300)
                ys = np.linspace(p_start[1], p_end[1], 300)

            mpl_line, = self.ax.plot(
                xs, ys,
                color=cline.style.color,
                linestyle=cline.style.line_style,
                lw=cline.style.size,
                picker=True,
                pickradius=5,
                zorder=ZORDER_LINES
            )
            self._line_artists[cline.uid] = mpl_line

            if cline.arrow.enabled:
                self._draw_arrows_on_path(
                    xs, ys, cline.arrow,
                    cline.style.color, cline.style.size
                )

            if cline.show_guide_markers:
                ms = cline.guide_marker_style
                for gp in cline.guide_points:
                    try:
                        gpt = math_utils.bary_to_cart(gp.composition, is_inv)
                    except Exception:
                        continue
                    self.ax.plot(
                        gpt[0], gpt[1],
                        marker=ms.marker_symbol,
                        color=ms.color,
                        markersize=ms.size,
                        zorder=ZORDER_COMPS,
                        linestyle='None',
                    )

        # 4. Составы (Точки и метки)
        for comp in project.compositions:
            try:
                pt = math_utils.bary_to_cart(comp.composition, is_inv)
            except Exception:
                continue
            
            # Маркер
            if comp.style.show_marker:
                self.ax.plot(
                    pt[0], pt[1],
                    marker=comp.style.marker_symbol,
                    color=comp.style.color,
                    markersize=comp.style.size,
                    zorder=ZORDER_COMPS,
                    linestyle='None'
                )
            
            # Метка
            if comp.name and comp.style.show_label:
                if comp.label_offset:
                    off_x, off_y = comp.label_offset
                    txt_x, txt_y = pt[0] + off_x, pt[1] + off_y
                else:
                    off = COMP_LABEL_OFFSET if is_inv else -COMP_LABEL_OFFSET
                    txt_x, txt_y = pt[0], pt[1] + off
                
                self.ax.text(
                    txt_x, txt_y, comp.name,
                    ha='center', fontweight='bold',
                    fontsize=FONT_SIZE,
                    gid=comp.uid, picker=True,
                    clip_on=False
                )

        # 5. Вершины
        self._draw_vertices(project)
        
        # 6. Подсказка при пустом проекте
        user_compositions = [c for c in project.compositions if c.style.show_marker or c.style.show_label]
        if not user_compositions and not project.lines:
            self._draw_empty_state_hint()
        
        # 7. Подсветка
        if highlight_uids:
            self.apply_highlights(highlight_uids)

        # 8. Маска области отображения (если задана)
        region_cart = self._valid_region_cart(project.display_region, is_inv)
        if region_cart:
            self._draw_region_mask(region_cart)
            rx = [pt[0] for pt in region_cart]
            ry = [pt[1] for pt in region_cart]
            pad = 0.05
            self.ax.set_xlim(min(rx) - pad, max(rx) + pad)
            self.ax.set_ylim(min(ry) - pad, max(ry) + pad)
        else:
            padding = 0.1
            h = math_utils.H
            self.ax.set_xlim(-padding, 1.0 + padding)
            self.ax.set_ylim(-padding, h + padding)

        self.ax.axis('off')

    def draw_dynamic_overlay(self, overlay: RenderOverlay, is_inverted: bool) -> list:
        """
        Рисует временные элементы.
        Возвращает список artists для отрисовки.
        """
        temp_artists = []
        
        # Треугольник
        if overlay.triangle_overlay and len(overlay.triangle_overlay) == 3:
            pts = overlay.triangle_overlay
            t1 = math_utils.bary_to_cart(pts[0], is_inverted)
            t2 = math_utils.bary_to_cart(pts[1], is_inverted)
            t3 = math_utils.bary_to_cart(pts[2], is_inverted)
            
            poly, = self.ax.fill(
                [t1[0], t2[0], t3[0]], [t1[1], t2[1], t3[1]],
                color=COLOR_TERNARY_TRIANGLE, alpha=0.1, zorder=ZORDER_OVERLAY, animated=False
            )
            line, = self.ax.plot(
                [t1[0], t2[0], t3[0], t1[0]], [t1[1], t2[1], t3[1], t1[1]],
                '--', color=COLOR_TERNARY_TRIANGLE, lw=1.5, alpha=0.8, 
                zorder=ZORDER_OVERLAY, animated=False
            )
            temp_artists.extend([poly, line])

        # Линии экстраполяции
        for item in overlay.extrap_lines:
            p1 = math_utils.bary_to_cart(item.start, is_inverted)
            p2 = math_utils.bary_to_cart(item.end, is_inverted)
            
            line, = self.ax.plot(
                [p1[0], p2[0]], [p1[1], p2[1]],
                color=item.color, linestyle=item.style,
                lw=1.5, alpha=0.9, zorder=ZORDER_OVERLAY, animated=False
            )
            if item.highlight:
                line.set_path_effects(get_highlight_effect())
            temp_artists.append(line)
        
        # Точки
        if overlay.projection_point:
            pt = math_utils.bary_to_cart(overlay.projection_point, is_inverted)
            point, = self.ax.plot(
                pt[0], pt[1], marker='o', color=COLOR_PROJECTION,
                markersize=6, zorder=ZORDER_PROJECTION, animated=False
            )
            temp_artists.append(point)
            
        if overlay.intersect_point:
            pt = math_utils.bary_to_cart(overlay.intersect_point, is_inverted)
            point, = self.ax.plot(
                pt[0], pt[1], marker='X', color=COLOR_INTERSECTION,
                markersize=10, zorder=ZORDER_INTERSECTION, markeredgecolor='white', markeredgewidth=1, animated=False
            )
            temp_artists.append(point)

        return temp_artists

    def apply_highlights(self, uids: list[str]):
        """Обновляет эффекты подсветки для существующих линий"""
        target_uids = set(uids)
        for line_uid, artist in self._line_artists.items():
            if line_uid in target_uids:
                artist.set_path_effects(get_highlight_effect())
                artist.set_zorder(ZORDER_OVERLAY)
            else:
                artist.set_path_effects([path_effects.Normal()])
                artist.set_zorder(ZORDER_LINES)

    def _draw_arrows_on_path(
        self,
        xs: np.ndarray,
        ys: np.ndarray,
        arrow: ArrowSettings,
        color: str,
        lw: float,
    ) -> None:
        """
        Рисует стрелки вдоль пути, заданного массивами xs/ys.

        Направление каждой стрелки определяется двумя реальными точками пути
        (не касательной), поэтому стрелка точно совпадает с нарисованной линией.
        """
        n = len(xs)
        if n < 4:
            return

        # Шаг для определения направления (≈2% длины пути)
        delta = max(2, n // 50)

        # Равномерное распределение стрелок по длине дуги
        step = 1.0 / (arrow.count + 1)
        positions = [step * (i + 1) for i in range(arrow.count)]

        for pos in positions:
            i = int(pos * (n - 1))
            i = max(delta, min(n - 1 - delta, i))

            if arrow.direction == "to_end":
                x0, y0 = xs[i - delta], ys[i - delta]
                x1, y1 = xs[i + delta], ys[i + delta]
            else:
                x0, y0 = xs[i + delta], ys[i + delta]
                x1, y1 = xs[i - delta], ys[i - delta]

            self.ax.annotate(
                "",
                xy=(x1, y1),
                xytext=(x0, y0),
                arrowprops=dict(
                    arrowstyle="-|>",
                    color=color,
                    lw=lw,
                    mutation_scale=10 + lw * 2,
                ),
                zorder=ZORDER_LINES + 1,
            )

    def _draw_grid(self, step: float, is_inv: bool):
        if step < 0.01: 
            step = 0.1
        if step >= 1.0: 
            return
        
        num_steps = int(round(1.0 / step))
        vals = [i * step for i in range(1, num_steps)]
        
        for v in vals:
            val = float(v)
            inv_val = 1.0 - val
            
            p1 = math_utils.bary_to_cart(Composition(a=val, b=0.0, c=inv_val), is_inv)
            p2 = math_utils.bary_to_cart(Composition(a=val, b=inv_val, c=0.0), is_inv)
            self.ax.plot([p1[0], p2[0]], [p1[1], p2[1]], 
                         color='gray', alpha=0.3, linestyle='-', lw=GRID_LINE_WIDTH, zorder=ZORDER_GRID)
            
            p3 = math_utils.bary_to_cart(Composition(a=0.0, b=val, c=inv_val), is_inv)
            p4 = math_utils.bary_to_cart(Composition(a=inv_val, b=val, c=0.0), is_inv)
            self.ax.plot([p3[0], p4[0]], [p3[1], p4[1]], 
                         color='gray', alpha=0.3, linestyle='-', lw=GRID_LINE_WIDTH, zorder=ZORDER_GRID)
            
            p5 = math_utils.bary_to_cart(Composition(a=0.0, b=inv_val, c=val), is_inv)
            p6 = math_utils.bary_to_cart(Composition(a=inv_val, b=0.0, c=val), is_inv)
            self.ax.plot([p5[0], p6[0]], [p5[1], p6[1]], 
                         color='gray', alpha=0.3, linestyle='-', lw=GRID_LINE_WIDTH, zorder=ZORDER_GRID)

    def _draw_empty_state_hint(self) -> None:
        """Рисует подсказку при пустом проекте"""
        self.ax.text(
            0.5, TRIANGLE_HEIGHT / 2,
            "Add compositions in the right panel\n"
            "or press Ctrl+O to open project\n\n"
            "Tip: Coordinates are molar fractions (auto-normalized)",
            ha='center', va='center',
            fontsize=11, color='#888888',
            style='italic',
            bbox=dict(boxstyle='round,pad=0.5', facecolor='#f5f5f5', edgecolor='#cccccc')
        )

    def _valid_region_cart(
        self, region: List[Composition], is_inv: bool
    ) -> List[tuple]:
        """Converts display_region compositions to Cartesian; returns list if ≥ 3 valid."""
        pts = []
        for comp in region:
            try:
                if not comp.is_valid:
                    continue
                pt = math_utils.bary_to_cart(comp, is_inv)
                pts.append((float(pt[0]), float(pt[1])))
            except Exception:
                continue
        return pts if len(pts) >= 3 else []

    def _draw_region_mask(self, region_cart: List[tuple]) -> None:
        """Draws a white mask covering everything outside the display region polygon."""
        big = 10.0
        outer = [(-big, -big), (big, -big), (big, big), (-big, big)]
        outer_verts = outer + [outer[0]]
        outer_codes = (
            [Path.MOVETO] + [Path.LINETO] * (len(outer) - 1) + [Path.CLOSEPOLY]
        )

        # Inner polygon with reversed winding to create a hole
        inner = list(reversed(region_cart))
        inner_verts = inner + [inner[0]]
        inner_codes = (
            [Path.MOVETO] + [Path.LINETO] * (len(inner) - 1) + [Path.CLOSEPOLY]
        )

        path = Path(outer_verts + inner_verts, outer_codes + inner_codes)
        patch = PathPatch(
            path, facecolor=COLOR_BACKGROUND, edgecolor='none', zorder=ZORDER_MASK
        )
        self.ax.add_patch(patch)

    def _draw_vertices(self, project: ProjectData):
        is_inv = project.is_inverted
        vertices = math_utils.get_vertices(is_inv)
        names = project.components
        off = VERTEX_LABEL_OFFSET
        
        configs = [
            (0, 'right', 'center', -off, 0),
            (1, 'left', 'center', off, 0),
            (2, 'center', 'top' if is_inv else 'bottom', 0, -off if is_inv else off),
        ]
        
        for idx, ha, va, dx, dy in configs:
            vertex = vertices[idx]
            key = str(idx)
            
            if key in project.vertex_labels_pos:
                x, y = project.vertex_labels_pos[key]
                current_ha, current_va = 'center', 'center'
            else:
                x = vertex[0] + dx
                y = vertex[1] + dy
                current_ha, current_va = ha, va

            self.ax.text(
                x, y, names[idx],
                ha=current_ha, va=current_va,
                fontweight='bold', fontsize=FONT_SIZE,
                gid=f"vertex_{idx}", picker=True
            )
