"""
Интерактивность для matplotlib-окна (plt.show) без Qt.

Подключает к Axes:
- координатный overlay при движении мыши
- перетаскивание текстовых меток (drag & drop)

Не зависит от PySide6. Используется в Diagram.show() и Diagram.draw(..., interactive=True).
"""

from __future__ import annotations

from typing import Optional

from matplotlib.axes import Axes
from matplotlib.backend_bases import MouseEvent
from matplotlib.text import Text
from matplotlib.backend_tools import Cursors

from delta import math_utils
from delta.models import ProjectData
from delta.project_manager import ProjectManager


class MapInteractor:
    """
    Лёгкий интерактор для matplotlib Axes (без Qt).

    Обеспечивает:
    - Координатный overlay (барицентрические координаты под курсором)
    - Drag & Drop текстовых меток
    """

    def __init__(
        self,
        ax: Axes,
        project_data: ProjectData,
        manager: Optional[ProjectManager] = None,
    ) -> None:
        self._ax = ax
        self._project = project_data
        self._manager = manager
        self._fig = ax.get_figure()

        # Overlay — текстовый элемент в углу осей
        self._coord_text: Optional[Text] = None

        # Drag state
        self._dragging = False
        self._dragged_artist: Optional[Text] = None
        self._dragged_gid: Optional[str] = None
        self._drag_offset = (0.0, 0.0)
        self._background = None

        self._connect()

    def _connect(self) -> None:
        """Подключает matplotlib event callbacks."""
        if self._fig is None:
            return
        self._fig.canvas.mpl_connect("motion_notify_event", self._on_move)  # type: ignore[arg-type]
        self._fig.canvas.mpl_connect("button_press_event", self._on_press)  # type: ignore[arg-type]
        self._fig.canvas.mpl_connect("button_release_event", self._on_release)  # type: ignore[arg-type]
        self._cursor_over_draggable = False

    # =====================================================================
    # КООРДИНАТНЫЙ OVERLAY
    # =====================================================================

    def _ensure_coord_text(self) -> Text:
        """Создаёт или возвращает текстовый элемент для overlay."""
        if self._coord_text is None:
            self._coord_text = self._ax.text(
                0.02, 0.98, "",
                transform=self._ax.transAxes,
                fontsize=9,
                fontfamily="monospace",
                verticalalignment="top",
                bbox=dict(
                    boxstyle="round,pad=0.4",
                    facecolor="white",
                    edgecolor="#cccccc",
                    alpha=0.9,
                ),
                zorder=1000,
            )
        return self._coord_text

    def _update_overlay(self, event: MouseEvent) -> None:
        """Обновляет текст координат под курсором."""
        if event.xdata is None or event.ydata is None:
            self._hide_overlay()
            return

        is_inv = self._project.is_inverted
        comp = math_utils.cart_to_bary(event.xdata, event.ydata, is_inv)

        # Скрываем, если курсор вне треугольника
        if comp.a < -0.02 or comp.b < -0.02 or comp.c < -0.02:
            self._hide_overlay()
            return

        try:
            a, b, c = comp.normalized
        except (ValueError, ZeroDivisionError):
            self._hide_overlay()
            return

        names = self._project.components
        txt = self._ensure_coord_text()
        txt.set_text(
            f"{names[0]}: {a:.4f}\n"
            f"{names[1]}: {b:.4f}\n"
            f"{names[2]}: {c:.4f}"
        )
        txt.set_visible(True)

    def _hide_overlay(self) -> None:
        if self._coord_text is not None:
            self._coord_text.set_visible(False)

    # =====================================================================
    # DRAG & DROP МЕТОК
    # =====================================================================

    def _find_draggable(self, event: MouseEvent) -> Optional[Text]:
        """Ищет Text-артист под курсором, у которого есть gid.
        
        Работает даже если курсор за пределами осей (для меток,
        вынесенных за display region).
        """
        if event.x is None or event.y is None:
            return None
        for artist in self._ax.texts:
            if artist is self._coord_text:
                continue
            if not artist.get_gid():
                continue
            contains, _ = artist.contains(event)
            if contains:
                return artist
        return None

    def _on_press(self, event: MouseEvent) -> None:
        if event.button != 1:
            return

        artist = self._find_draggable(event)
        if artist is None:
            return

        # Получаем координаты в системе данных (могут быть None если за пределами осей)
        # В этом случае используем transform для конвертации display -> data
        xdata, ydata = self._event_to_data(event)
        if xdata is None or ydata is None:
            return

        self._dragged_artist = artist
        self._dragged_gid = artist.get_gid()
        self._dragging = True

        x0, y0 = artist.get_position()
        self._drag_offset = (x0 - xdata, y0 - ydata)

        artist.set_animated(True)
        canvas = self._fig.canvas  # type: ignore[union-attr]
        canvas.set_cursor(Cursors.MOVE)
        canvas.draw()
        self._background = canvas.copy_from_bbox(self._ax.bbox)  # type: ignore[attr-defined, union-attr]
        self._ax.draw_artist(artist)
        canvas.blit(self._ax.bbox)

    def _on_release(self, event: MouseEvent) -> None:
        if not self._dragging or self._dragged_artist is None:
            return

        artist = self._dragged_artist
        gid = self._dragged_gid

        artist.set_animated(False)
        self._dragging = False
        self._dragged_artist = None
        self._dragged_gid = None
        self._background = None
        self._cursor_over_draggable = False

        canvas = self._fig.canvas  # type: ignore[union-attr]
        canvas.set_cursor(Cursors.POINTER)
        canvas.draw_idle()

        # Сохраняем новую позицию в модель
        if self._manager is not None and gid is not None:
            try:
                x, y = artist.get_position()
                self._persist_label_position(gid, x, y)
            except Exception:
                pass  # Не ломаем интерактивность при ошибке сохранения

    def _persist_label_position(self, gid: str, x: float, y: float) -> None:
        """Записывает новую позицию перетащенной метки в ProjectManager."""
        if self._manager is None:
            return

        is_inv = self._project.is_inverted

        if gid.startswith("vertex_"):
            # Метка вершины: vertex_0, vertex_1, vertex_2
            try:
                idx = int(gid.split("_")[1])
                self._manager.set_vertex_label_pos(idx, x, y)
            except (ValueError, IndexError):
                pass

        elif gid.startswith("annotation_"):
            # Текстовая аннотация: annotation_{uid}
            ann_uid = gid[len("annotation_"):]
            new_pos = math_utils.cart_to_bary(x, y, is_inv)
            self._manager.update_annotation(ann_uid, position=new_pos)

        else:
            # Composition label: gid = composition uid
            self._manager.set_composition_label_pos(gid, x, y)

    # =====================================================================
    # MOTION
    # =====================================================================

    def _on_move(self, event: MouseEvent) -> None:
        canvas = self._fig.canvas  # type: ignore[union-attr]

        # Drag — работает даже за пределами осей
        if self._dragging and self._dragged_artist is not None:
            xdata, ydata = self._event_to_data(event)
            if xdata is not None and ydata is not None:
                new_x = xdata + self._drag_offset[0]
                new_y = ydata + self._drag_offset[1]
                self._dragged_artist.set_position((new_x, new_y))

                if self._background is not None:
                    canvas.restore_region(self._background)
                self._ax.draw_artist(self._dragged_artist)
                canvas.blit(self._ax.bbox)
            return

        # Курсор: рука если над перетаскиваемым элементом
        hit = self._find_draggable(event)
        if hit is not None:
            if not self._cursor_over_draggable:
                canvas.set_cursor(Cursors.HAND)
                self._cursor_over_draggable = True
        else:
            if self._cursor_over_draggable:
                canvas.set_cursor(Cursors.POINTER)
                self._cursor_over_draggable = False

        # Overlay — только когда курсор внутри осей
        if not event.inaxes:
            self._hide_overlay()
            canvas.draw_idle()
            return

        self._update_overlay(event)
        canvas.draw_idle()

    def _event_to_data(self, event: MouseEvent) -> tuple[Optional[float], Optional[float]]:
        """
        Конвертирует координаты события в систему данных осей.
        
        Работает даже если курсор за пределами осей (event.xdata is None).
        Это нужно для перетаскивания меток, вынесенных за display region.
        """
        if event.xdata is not None and event.ydata is not None:
            return event.xdata, event.ydata
        
        # Курсор за пределами осей — конвертируем вручную
        if event.x is None or event.y is None:
            return None, None
        
        try:
            # display coords -> data coords
            inv_transform = self._ax.transData.inverted()
            xdata, ydata = inv_transform.transform((event.x, event.y))
            return float(xdata), float(ydata)
        except Exception:
            return None, None
