import matplotlib.patheffects as path_effects
from matplotlib.axes import Axes
from matplotlib.lines import Line2D
from core import math_utils
from core.models import ProjectData, RenderOverlay, Composition
from core.constants import (
    COLOR_BACKGROUND, COLOR_TERNARY_TRIANGLE, COLOR_PROJECTION, 
    COLOR_INTERSECTION, ZORDER_GRID, ZORDER_LINES, ZORDER_COMPS,
    ZORDER_OVERLAY, ZORDER_PROJECTION, ZORDER_INTERSECTION,
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

    def clear(self):
        self.ax.clear()
        self.ax.set_aspect('equal')
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

        # 3. Линии
        comp_map = {p.uid: p for p in project.compositions}
        for line in project.lines:
            start = comp_map.get(line.start_uid)
            end = comp_map.get(line.end_uid)
            if start and end:
                p1 = math_utils.bary_to_cart(start.composition, is_inv)
                p2 = math_utils.bary_to_cart(end.composition, is_inv)
                
                mpl_line, = self.ax.plot(
                    [p1[0], p2[0]], [p1[1], p2[1]],
                    color=line.style.color,
                    linestyle=line.style.line_style,
                    lw=line.style.size,
                    picker=True,
                    pickradius=5,
                    zorder=ZORDER_LINES
                )
                self._line_artists[line.uid] = mpl_line

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
            
        # 8. Границы отображения
        padding = 0.1
        h = math_utils.H
        self.ax.set_xlim(-padding, 1.0 + padding)
        self.ax.set_ylim(-padding, h + padding)
        self.ax.axis('off')

    def draw_dynamic_overlay(self, overlay: RenderOverlay, is_inverted: bool) -> list:
        """
        Рисует временные элементы.
        Возвращает список artists для отрисовки (чтобы потом их удалить, если нужно, но при blit это не обязательно).
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

    def _draw_grid(self, step: float, is_inv: bool):
        if step < 0.01: 
            step = 0.1
        if step >= 1.0: 
            return
        
        # Используем генератор вместо np.arange для избежания ошибок округления
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
