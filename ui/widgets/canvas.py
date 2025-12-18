from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
import matplotlib.patheffects as path_effects
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QSizePolicy
from core import math_utils
from core.models import Composition, RenderOverlay, ProjectData
import numpy as np
from typing import Optional

# Стандартные настройки размеров (фиксированные)
FONT_SIZE = 10
MARKER_SIZE = 6
LINE_WIDTH = 2
GRID_WIDTH = 1

def get_highlight_effect():
    return [
        path_effects.Stroke(linewidth=5, foreground="orange"),
        path_effects.Normal(),
    ]

class PlotCanvas(FigureCanvasQTAgg):
    mouse_moved = Signal(Composition)
    annotation_dropped = Signal(str, float, float)
    vertex_label_dropped = Signal(int, float, float)

    def __init__(self, parent=None):
        # Создаем фигуру без жестких размеров и DPI.
        # Matplotlib сам подберет DPI в зависимости от системных настроек.
        self.fig = Figure()
        self.ax = self.fig.add_subplot(111)
        
        # Используем стандартный режим 'box' для совместимости с жесткими xlim/ylim
        self.ax.set_aspect('equal')
        
        # Убираем поля графика
        self.fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
        
        super().__init__(self.fig)
        self.setParent(parent)
        
        # Используем Policy.Ignored, чтобы CanvasView мог жестко задавать setGeometry
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        
        self.current_project = None
        self._is_dragging = False
        self.dragged_item_uid = None
        self.dragged_artist = None
        self.drag_offset = (0, 0)
        
        # Blitting
        self.background = None
        self._static_background = None
        
        self._overlay_artists = []
        self._needs_full_redraw = True
        self._line_artists = {} 
        self.highlighted_line_uid = None
        self._cached_overlay_uids = set()
        
        # Подключаем события (resize больше не нужен для пересчета масштаба)
        self.mpl_connect('motion_notify_event', self.on_mouse_move)
        self.mpl_connect('button_press_event', self.on_press)
        self.mpl_connect('button_release_event', self.on_release)

    def resizeEvent(self, event):
        """
        Обрабатываем изменение размера окна.
        Сбрасываем кэш фона, чтобы картинка перерисовалась под новый размер.
        """
        # 1. Стандартная обработка matplotlib (обновление размеров фигуры)
        super().resizeEvent(event)
        
        # 2. Инвалидируем (сбрасываем) кэш
        self._static_background = None
        self._needs_full_redraw = True
        
        # 3. Если проект загружен, форсируем перерисовку прямо сейчас,
        # чтобы пользователь сразу увидел результат, а не ждал движения мыши.
        if self.current_project:
            # Можно передать None вместо overlay_data, если не хотим его сохранять,
            # или просто вызвать полную перерисовку.
            self.draw_project(self.current_project, force_full_redraw=True)

    def set_highlight_line(self, uid: Optional[str]) -> None:
        self.highlighted_line_uid = uid
        self._apply_overlay_highlights(list(self._cached_overlay_uids)) 
        self.draw_idle()

    def _apply_overlay_highlights(self, overlay_uids: list[str]):
        target_uids = set(overlay_uids) if overlay_uids else set()
        if self.highlighted_line_uid:
            target_uids.add(self.highlighted_line_uid)
            
        for line_uid, artist in self._line_artists.items():
            if line_uid in target_uids:
                artist.set_path_effects(get_highlight_effect())
                artist.set_zorder(10) 
            else:
                artist.set_path_effects([path_effects.Normal()])
                artist.set_zorder(2) 

    def draw_project(self, project_data: ProjectData, overlay_data: Optional[RenderOverlay] = None, force_full_redraw: bool = False):
        if self._is_dragging:
            return
        
        self.current_project = project_data 
        
        new_highlights = overlay_data.highlight_lines_uids if overlay_data else []
        highlights_changed = (set(new_highlights) != self._cached_overlay_uids)
        
        need_static_update = (
            force_full_redraw 
            or self._needs_full_redraw 
            or self._static_background is None
            or highlights_changed
        )

        if need_static_update:
            self._full_redraw(project_data, highlight_uids=new_highlights or [])
            self._needs_full_redraw = False
            self._draw_overlay_fast(overlay_data)
        else:
            self._draw_overlay_fast(overlay_data)

    def _full_redraw(self, project_data: ProjectData, highlight_uids: list[str] | None = None):
        self.ax.clear()
        # Повторно ставим aspect, так как clear() его сбрасывает
        self.ax.set_aspect('equal')
        
        self._overlay_artists.clear()
        self._line_artists.clear()
        
        self.ax.set_facecolor("#FFFFFF")
        
        is_inv = project_data.is_inverted
        v_a, v_b, v_c = math_utils.get_vertices(is_inv)
        
        # 1. Границы треугольника
        self.ax.plot([v_a[0], v_b[0]], [v_a[1], v_b[1]], 'k-', lw=2)
        self.ax.plot([v_a[0], v_c[0]], [v_a[1], v_c[1]], 'k-', lw=1)
        self.ax.plot([v_b[0], v_c[0]], [v_b[1], v_c[1]], 'k-', lw=1)
        
        # 2. Сетка
        if project_data.grid.visible:
            self._draw_grid(project_data.grid.step, is_inv)
        
        # 3. Линии
        comp_map = {p.uid: p for p in project_data.compositions}
        for line in project_data.lines:
            start = comp_map.get(line.start_uid)
            end = comp_map.get(line.end_uid)
            if start and end:
                p1 = math_utils.bary_to_cart(start.composition, is_inv)
                p2 = math_utils.bary_to_cart(end.composition, is_inv)
                
                mpl_line, = self.ax.plot(
                    [p1[0], p2[0]], [p1[1], p2[1]],
                    color=line.style.color,
                    linestyle=line.style.line_style,
                    lw=line.style.size, # Используем реальный размер из модели
                    picker=True,
                    pickradius=5,
                    zorder=2
                )
                self._line_artists[line.uid] = mpl_line

        # 4. Подсветка
        if highlight_uids is not None:
             self._cached_overlay_uids = set(highlight_uids)
        else:
            self._cached_overlay_uids = set()
        
        current_highlights = set(self._cached_overlay_uids)
        if self.highlighted_line_uid:
            current_highlights.add(self.highlighted_line_uid)
        self._apply_overlay_highlights(list(current_highlights))

        # 5. Составы
        for comp in project_data.compositions:
            try:
                pt = math_utils.bary_to_cart(comp.composition, is_inv)
            except Exception:
                continue
            
            if comp.style.show_marker:
                self.ax.plot(
                    pt[0], pt[1],
                    marker=comp.style.marker_symbol,
                    color=comp.style.color,
                    markersize=comp.style.size, # Реальный размер
                    zorder=5,
                    linestyle='None'
                )
            
            if comp.name and comp.style.show_label:
                if comp.label_offset:
                    # Если есть пользовательское смещение, прибавляем его к точке
                    off_x, off_y = comp.label_offset
                    txt_x = pt[0] + off_x
                    txt_y = pt[1] + off_y
                else:
                    # Дефолтное поведение (если смещение не задано)
                    off = 0.03 if is_inv else -0.03
                    txt_x, txt_y = pt[0], pt[1] + off
                
                self.ax.text(
                    txt_x, txt_y, comp.name,
                    ha='center', fontweight='bold',
                    fontsize=FONT_SIZE,
                    gid=comp.uid, picker=True,
                    clip_on=False
                )
        
        # 6. Вершины
        self._draw_vertices(project_data)
        
        # 7. Границы (Zoom/Pan) - Статичные границы данных
        # Треугольник вписан в (0,0) - (1, H), где H=sqrt(3)/2 ~ 0.866
        # Добавляем небольшие отступы (padding)
        padding = 0.1
        self.ax.set_xlim(-padding, 1.0 + padding)
        
        h = math_utils.H
        if is_inv:
            # Перевернутый: от 0 до H
            self.ax.set_ylim(-padding, h + padding)
        else:
            # Обычный: тоже вписывается в подобные границы, 
            # но для надежности берем чуть шире
            self.ax.set_ylim(-padding, h + padding)
            
        self.ax.axis('off')
        
        self.draw()
        
        # ЗАЩИТА ОТ КРАША
        bbox = self.ax.bbox
        if bbox.width > 1 and bbox.height > 1:
            self._static_background = self.copy_from_bbox(bbox)
        else:
            self._static_background = None

    def _draw_overlay_fast(self, overlay_data: Optional[RenderOverlay]):
        # ЗАЩИТА И САМОВОССТАНОВЛЕНИЕ
        if self._static_background is None:
            # Если фона нет (сброшен при resize или не создан), 
            # но есть проект - генерируем фон немедленно.
            if self.current_project:
                self._full_redraw(self.current_project)
            else:
                # Если проекта нет, рисовать нечего
                return

        # Теперь фон точно есть (или мы попытались его создать)
        if self._static_background:
            self.restore_region(self._static_background)
        
        if not overlay_data:
            self.blit(self.ax.bbox)
            return

        is_inv = self.current_project.is_inverted if self.current_project else True
        temp_artists = []
        
        # Треугольник
        if overlay_data.triangle_overlay and len(overlay_data.triangle_overlay) == 3:
            pts = overlay_data.triangle_overlay
            t1 = math_utils.bary_to_cart(pts[0], is_inv)
            t2 = math_utils.bary_to_cart(pts[1], is_inv)
            t3 = math_utils.bary_to_cart(pts[2], is_inv)
            
            poly, = self.ax.fill(
                [t1[0], t2[0], t3[0]], [t1[1], t2[1], t3[1]],
                color='green', alpha=0.1, zorder=3, animated=False
            )
            line, = self.ax.plot(
                [t1[0], t2[0], t3[0], t1[0]], [t1[1], t2[1], t3[1], t1[1]],
                'g--', lw=1.5, alpha=0.8, zorder=3, animated=False
            )
            temp_artists.extend([poly, line])

        # Линии экстраполяции
        for item in overlay_data.extrap_lines:
            p1 = math_utils.bary_to_cart(item.start, is_inv)
            p2 = math_utils.bary_to_cart(item.end, is_inv)
            
            line, = self.ax.plot(
                [p1[0], p2[0]], [p1[1], p2[1]],
                color=item.color, linestyle=item.style,
                lw=1.5, alpha=0.9, zorder=4, animated=False
            )
            if item.highlight:
                line.set_path_effects(get_highlight_effect())
            temp_artists.append(line)
        
        # Точки
        if overlay_data.projection_point:
            pt = math_utils.bary_to_cart(overlay_data.projection_point, is_inv)
            point, = self.ax.plot(
                pt[0], pt[1], marker='o', color='blue',
                markersize=6, zorder=101, animated=False
            )
            temp_artists.append(point)
            
        if overlay_data.intersect_point:
            pt = math_utils.bary_to_cart(overlay_data.intersect_point, is_inv)
            point, = self.ax.plot(
                pt[0], pt[1], marker='X', color='red',
                markersize=10, zorder=100, markeredgecolor='white', markeredgewidth=1, animated=False
            )
            temp_artists.append(point)
            
        for artist in temp_artists:
            self.ax.draw_artist(artist)
            artist.remove()

        self.blit(self.ax.bbox)

    def _draw_vertices(self, project_data: ProjectData):
        is_inv = project_data.is_inverted
        vertices = math_utils.get_vertices(is_inv)
        names = project_data.components
        
        off_x = 0.04
        off_y = 0.04 
        
        if is_inv:
            configs = [
                (0, 'right', 'center', -off_x, 0),
                (1, 'left', 'center', off_x, 0),
                (2, 'center', 'top', 0, -off_y),
            ]
        else:
            configs = [
                (0, 'right', 'center', -off_x, 0),
                (1, 'left', 'center', off_x, 0),
                (2, 'center', 'bottom', 0, off_y),
            ]
        
        for idx, ha, va, dx, dy in configs:
            vertex = vertices[idx]
            key = str(idx)
            
            if key in project_data.vertex_labels_pos:
                x, y = project_data.vertex_labels_pos[key]
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

    def force_full_redraw(self):
        self._needs_full_redraw = True

    def _draw_grid(self, step: float, is_inv: bool):
        if step < 0.01:
            step = 0.1
        if step >= 1.0:
            return
        epsilon = 1e-9
        vals = np.arange(step, 1.0 - epsilon, step)
        style = {'color': 'gray', 'alpha': 0.3, 'linestyle': '-', 'lw': GRID_WIDTH, 'zorder': 0.5}
        
        for v in vals:
            val = float(v)
            inv_val = 1.0 - val
            p1 = math_utils.bary_to_cart(Composition(val, 0.0, inv_val), is_inv)
            p2 = math_utils.bary_to_cart(Composition(val, inv_val, 0.0), is_inv)
            self.ax.plot([p1[0], p2[0]], [p1[1], p2[1]], **style)
            
            p3 = math_utils.bary_to_cart(Composition(0.0, val, inv_val), is_inv)
            p4 = math_utils.bary_to_cart(Composition(inv_val, val, 0.0), is_inv)
            self.ax.plot([p3[0], p4[0]], [p3[1], p4[1]], **style)
            
            p5 = math_utils.bary_to_cart(Composition(0.0, inv_val, val), is_inv)
            p6 = math_utils.bary_to_cart(Composition(inv_val, 0.0, val), is_inv)
            self.ax.plot([p5[0], p6[0]], [p5[1], p6[1]], **style)

    def on_press(self, event):
        if event.button != 1 or not event.inaxes:
            return
        for artist in self.ax.texts:
            contains, _ = artist.contains(event)
            if contains and artist.get_gid():
                self.dragged_artist = artist
                self.dragged_item_uid = artist.get_gid()
                x0, y0 = artist.get_position()
                self.drag_offset = (x0 - event.xdata, y0 - event.ydata)
                
                self._is_dragging = True
                self.dragged_artist.set_animated(True)
                self.draw() 
                self.background = self.copy_from_bbox(self.ax.bbox)
                self.ax.draw_artist(self.dragged_artist)
                self.blit(self.ax.bbox)
                return

    def on_mouse_move(self, event):
        if event.inaxes:
            comp = math_utils.cart_to_bary(event.xdata, event.ydata, self.current_project.is_inverted if self.current_project else True)
            self.mouse_moved.emit(comp)
            
            if self.dragged_artist:
                self.restore_region(self.background)
                new_x = event.xdata + self.drag_offset[0]
                new_y = event.ydata + self.drag_offset[1]
                self.dragged_artist.set_position((new_x, new_y))
                self.ax.draw_artist(self.dragged_artist)
                self.blit(self.ax.bbox)

    def on_release(self, event):
        if not self._is_dragging:
            return
        if self.dragged_artist:
            self.dragged_artist.set_animated(False)
        self.background = None

        artist = self.dragged_artist
        uid = self.dragged_item_uid
        
        self._is_dragging = False
        self.dragged_artist = None
        self.dragged_item_uid = None
        
        if not artist or not uid:
            return
        try:
            x, y = artist.get_position()
        except (RuntimeError, AttributeError):
            return
        
        if uid.startswith("vertex_"):
            idx = int(uid.split("_")[1])
            self.vertex_label_dropped.emit(idx, x, y)
        else:
            self.annotation_dropped.emit(uid, x, y)

    def export_image(self, filename: str):
        # Обычное сохранение matplotlib
        if self.current_project:
            self._full_redraw(self.current_project)
            self.fig.savefig(filename, bbox_inches='tight')
