from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QResizeEvent
from ui.canvas import PlotCanvas


class CanvasView(QWidget):
    def __init__(self, canvas: PlotCanvas):
        super().__init__()
        self.canvas = canvas
        self.canvas.setParent(self)
        
        self.target_ratio = 1154.0 / 1000.0
        self._lock_aspect = True                                # ◄ НОВОЕ
        
        self.setStyleSheet("background-color: #505050;")

    def set_aspect_locked(self, locked: bool) -> None:          # ◄ НОВОЕ
        """Переключает режим пропорций"""
        self._lock_aspect = locked
        self._update_canvas_geometry()

    def resizeEvent(self, event: QResizeEvent):
        self._update_canvas_geometry()
        super().resizeEvent(event)

    def _update_canvas_geometry(self) -> None:                  # ◄ РЕФАКТОРИНГ
        """Пересчитывает геометрию canvas"""
        w = self.width()
        h = self.height()
        
        if w == 0 or h == 0:
            return

        if self._lock_aspect:
            # Letterboxing — вписываем с сохранением пропорций
            if w / h > self.target_ratio:
                new_h = h
                new_w = int(new_h * self.target_ratio)
            else:
                new_w = w
                new_h = int(new_w / self.target_ratio)
            x = (w - new_w) // 2
            y = (h - new_h) // 2
        else:
            # Свободное растяжение — заполняем всё пространство
            x, y = 0, 0
            new_w, new_h = w, h
        
        self.canvas.setGeometry(x, y, new_w, new_h)

    # Заглушки для совместимости
    def set_target_size(self, w: int, h: int) -> None:
        pass
    
    def get_target_size(self) -> tuple[int, int]:
        return (1154, 1000)