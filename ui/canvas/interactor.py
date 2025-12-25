from PySide6.QtCore import QObject, Signal
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
    """
    mouse_moved = Signal(Composition)
    annotation_dropped = Signal(str, float, float)
    vertex_label_dropped = Signal(int, float, float)

    def __init__(self, canvas_widget: 'PlotCanvas'):
        super().__init__()
        self._canvas = canvas_widget
        self._is_dragging = False
        self.dragged_item_uid: str | None = None
        self.dragged_artist = None  # matplotlib Text artist
        self.drag_offset: tuple[float, float] = (0.0, 0.0)

    def on_press(self, event: MouseEvent) -> None:
        if event.button != 1 or not event.inaxes:
            return
        
        # Ищем, по чему кликнули (текстовые метки)
        for artist in self._canvas.ax.texts:
            contains, _ = artist.contains(event)
            if contains and artist.get_gid():
                self._start_drag(artist, event)
                return

    def _start_drag(self, artist, event: MouseEvent) -> None:
        if event.xdata is None or event.ydata is None:
            return
            
        self.dragged_artist = artist
        self.dragged_item_uid = artist.get_gid()
        x0, y0 = artist.get_position()
        self.drag_offset = (x0 - event.xdata, y0 - event.ydata)
        
        self._is_dragging = True
        artist.set_animated(True)
        
        # Сообщаем канвасу, что нужно подготовить фон для blitting
        self._canvas.prepare_blitting_background()
        
        # Рисуем артиста поверх сохраненного фона
        self._canvas.draw_artist_dynamic(self.dragged_artist)

    def on_move(self, event: MouseEvent) -> None:
        # Проверяем валидность координат
        if not event.inaxes or event.xdata is None or event.ydata is None:
            return
            
        # 1. Испускаем координаты
        is_inv = self._canvas.current_project.is_inverted if self._canvas.current_project else True
        comp = math_utils.cart_to_bary(event.xdata, event.ydata, is_inv)
        self.mouse_moved.emit(comp)
        
        # 2. Обрабатываем Drag
        if self._is_dragging and self.dragged_artist is not None:
            self._update_drag(event)

    def _update_drag(self, event: MouseEvent) -> None:
        # Проверяем валидность координат
        if event.xdata is None or event.ydata is None:
            return
        if self.dragged_artist is None:
            return
            
        # Восстанавливаем фон
        self._canvas.restore_blitting_background()
        
        # Считаем новую позицию
        new_x = event.xdata + self.drag_offset[0]
        new_y = event.ydata + self.drag_offset[1]
        
        # Обновляем и рисуем артиста
        self.dragged_artist.set_position((new_x, new_y))
        self._canvas.draw_artist_dynamic(self.dragged_artist)

    def on_release(self, event: MouseEvent) -> None:
        if not self._is_dragging:
            return
        
        # Завершение драга
        if self.dragged_artist is not None:
            self.dragged_artist.set_animated(False)
        
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
        else:
            self.annotation_dropped.emit(uid, x, y)
