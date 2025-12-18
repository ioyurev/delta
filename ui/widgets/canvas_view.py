from PySide6.QtWidgets import QWidget
from PySide6.QtGui import QResizeEvent
from ui.widgets.canvas import PlotCanvas

class CanvasView(QWidget):
    def __init__(self, canvas: PlotCanvas):
        super().__init__()
        self.canvas = canvas
        self.canvas.setParent(self)
        
        # Задаем желаемое соотношение сторон (1154 / 1000 = 1.154)
        self.target_ratio = 1154.0 / 1000.0
        
        # Темно-серый фон для "стола"
        self.setStyleSheet("background-color: #505050;")

    def resizeEvent(self, event: QResizeEvent):
        """Ручной расчет размеров для сохранения пропорций (Letterboxing)"""
        w = self.width()
        h = self.height()
        
        if w == 0 or h == 0:
            return

        # Считаем размеры, вписывая прямоугольник в текущее окно
        if w / h > self.target_ratio:
            # Окно слишком широкое - ограничиваем по высоте
            new_h = h
            new_w = int(new_h * self.target_ratio)
        else:
            # Окно слишком узкое/высокое - ограничиваем по ширине
            new_w = w
            new_h = int(new_w / self.target_ratio)
            
        # Центрируем
        x = (w - new_w) // 2
        y = (h - new_h) // 2
        
        # Применяем размеры
        self.canvas.setGeometry(x, y, new_w, new_h)
        
        super().resizeEvent(event)

    # Заглушки для совместимости
    def set_target_size(self, w: int, h: int): pass
    def get_target_size(self) -> tuple[int, int]: return (1154, 1000)
