from PySide6.QtCore import QObject, Signal, Qt
from PySide6.QtGui import QCursor
from matplotlib.backend_bases import MouseEvent
from delta import math_utils
from delta.models import Composition
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .widget import PlotCanvas


class CanvasInteractor(QObject):
    """
    Отвечает за обработку событий мыши:
    - Испускание mouse_moved
    - Drag & Drop текстовых меток
    - Режим выбора guide-точки для CurveLine (GUIDE_PICK)
    """
    mouse_moved = Signal(Composition)
    annotation_dropped = Signal(str, float, float)
    vertex_label_dropped = Signal(int, float, float)
    text_annotation_dropped = Signal(str, float, float)
    # Испускается в режиме GUIDE_PICK при клике по холсту
    guide_point_picked = Signal(Composition)
    ctrl_click_add = Signal(Composition)  # Ctrl+Click → добавить точку

    MODE_NORMAL = "normal"
    MODE_GUIDE_PICK = "guide_pick"

    def __init__(self, canvas_widget: 'PlotCanvas'):
        super().__init__()
        self._canvas = canvas_widget
        self._mode: str = self.MODE_NORMAL
        self._is_dragging = False
        self._cursor_over_draggable = False
        self.dragged_item_uid: str | None = None
        self.dragged_artist = None  # matplotlib Text artist
        self.drag_offset: tuple[float, float] = (0.0, 0.0)

    @property
    def is_dragging(self) -> bool:
        """True во время перетаскивания текстовой метки."""
        return self._is_dragging

    def set_mode(self, mode: str) -> None:
        """Переключает режим интерактора. mode: MODE_NORMAL | MODE_GUIDE_PICK"""
        self._mode = mode

    def on_press(self, event: MouseEvent) -> None:
        if event.button != 1:
            return

        # Режим выбора guide-точки
        if self._mode == self.MODE_GUIDE_PICK:
            if event.inaxes and event.xdata is not None and event.ydata is not None:
                is_inv = (
                    self._canvas.current_project.is_inverted
                    if self._canvas.current_project else False
                )
                comp = math_utils.cart_to_bary(event.xdata, event.ydata, is_inv)
                self.guide_point_picked.emit(comp)
            return

        # Ctrl+Click — добавить точку
        if (event.inaxes and event.key == 'control'
                and event.xdata is not None and event.ydata is not None):
            is_inv = (
                self._canvas.current_project.is_inverted
                if self._canvas.current_project else False
            )
            comp = math_utils.cart_to_bary(event.xdata, event.ydata, is_inv)
            if comp.a >= -0.01 and comp.b >= -0.01 and comp.c >= -0.01:
                self.ctrl_click_add.emit(comp)
            return

        # Ищем по чему кликнули — работает и за пределами осей
        for artist in self._canvas.ax.texts:
            if not artist.get_gid():
                continue
            contains, _ = artist.contains(event)
            if contains:
                self._start_drag(artist, event)
                return

    def _start_drag(self, artist, event: MouseEvent) -> None:
        xdata, ydata = self._event_to_data(event)
        if xdata is None or ydata is None:
            return

        self.dragged_artist = artist
        self.dragged_item_uid = artist.get_gid()
        x0, y0 = artist.get_position()
        self.drag_offset = (x0 - xdata, y0 - ydata)

        self._is_dragging = True
        artist.set_animated(True)
        self._canvas.setCursor(QCursor(Qt.CursorShape.ClosedHandCursor))

        self._canvas.prepare_blitting_background()
        self._canvas.draw_artist_dynamic(self.dragged_artist)

    def on_move(self, event: MouseEvent) -> None:
        # Drag — работает и за пределами осей
        if self._is_dragging and self.dragged_artist is not None:
            self._update_drag(event)
            return

        # Курсор: рука над перетаскиваемыми элементами
        hit = self._find_draggable_at(event)
        if hit is not None:
            if not self._cursor_over_draggable:
                self._canvas.setCursor(QCursor(Qt.CursorShape.OpenHandCursor))
                self._cursor_over_draggable = True
        else:
            if self._cursor_over_draggable:
                self._canvas.unsetCursor()
                self._cursor_over_draggable = False

        # Координаты — только внутри осей
        if not event.inaxes or event.xdata is None or event.ydata is None:
            return

        is_inv = self._canvas.current_project.is_inverted if self._canvas.current_project else True
        comp = math_utils.cart_to_bary(event.xdata, event.ydata, is_inv)
        self.mouse_moved.emit(comp)

    def _update_drag(self, event: MouseEvent) -> None:
        if self.dragged_artist is None:
            return

        xdata, ydata = self._event_to_data(event)
        if xdata is None or ydata is None:
            return

        self._canvas.restore_blitting_background()

        new_x = xdata + self.drag_offset[0]
        new_y = ydata + self.drag_offset[1]

        self.dragged_artist.set_position((new_x, new_y))
        self._canvas.draw_artist_dynamic(self.dragged_artist)

    def on_release(self, event: MouseEvent) -> None:
        if not self._is_dragging:
            return

        if self.dragged_artist is not None:
            self.dragged_artist.set_animated(False)

        self._canvas.unsetCursor()
        self._cursor_over_draggable = False
        self._canvas.clear_blitting_background()
        
        uid = self.dragged_item_uid
        artist = self.dragged_artist
        
        self._is_dragging = False
        self.dragged_artist = None
        self.dragged_item_uid = None
        
        if artist is None or uid is None:
            return
            
        try:
            x, y = artist.get_position()
        except (RuntimeError, AttributeError):
            return
        
        if uid.startswith("vertex_"):
            idx = int(uid.split("_")[1])
            self.vertex_label_dropped.emit(idx, x, y)
        elif uid.startswith("annotation_"):
            ann_uid = uid[len("annotation_"):]
            self.text_annotation_dropped.emit(ann_uid, x, y)
        else:
            self.annotation_dropped.emit(uid, x, y)

    def _event_to_data(self, event: MouseEvent) -> tuple[float | None, float | None]:
        """Конвертирует координаты события в систему данных, даже за пределами осей."""
        if event.xdata is not None and event.ydata is not None:
            return event.xdata, event.ydata

        if event.x is None or event.y is None:
            return None, None

        try:
            inv_transform = self._canvas.ax.transData.inverted()
            xdata, ydata = inv_transform.transform((event.x, event.y))
            return float(xdata), float(ydata)
        except Exception:
            return None, None

    def _find_draggable_at(self, event: MouseEvent) -> object:
        """Ищет перетаскиваемый Text-артист под курсором."""
        if event.x is None or event.y is None:
            return None
        for artist in self._canvas.ax.texts:
            if not artist.get_gid():
                continue
            contains, _ = artist.contains(event)
            if contains:
                return artist
        return None
