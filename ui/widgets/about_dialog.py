from PySide6.QtWidgets import QDialog, QVBoxLayout, QLabel, QPushButton, QFrame
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont, QIcon
from delta.version import get_app_version
from delta.utils import resource_path

class AboutDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("O программе")
        self.setFixedWidth(400)
        
        # Убираем кнопку "?" из заголовка окна
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        
        layout = QVBoxLayout(self)
        layout.setSpacing(15)
        layout.setContentsMargins(20, 20, 20, 20)
        
        # 1. Заголовок и Версия
        lbl_title = QLabel("Delta")
        lbl_title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        f_title = QFont()
        f_title.setBold(True)
        f_title.setPointSize(16)
        lbl_title.setFont(f_title)
        
        lbl_ver = QLabel(f"Version {get_app_version()}")
        lbl_ver.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_ver.setStyleSheet("color: #666;")
        
        # Логотип в окне About
        lbl_logo = QLabel()
        # Загружаем SVG в QPixmap (растеризуем для отображения в Label)
        # Указываем размер (например, 64x64) - SVG отрендерится идеально под этот размер
        pixmap = QIcon(resource_path("icon.svg")).pixmap(128, 128)
        lbl_logo.setPixmap(pixmap)
        lbl_logo.setAlignment(Qt.AlignmentFlag.AlignCenter)
        
        layout.addWidget(lbl_logo) # Вставляем в самый верх
        layout.addWidget(lbl_title)
        layout.addWidget(lbl_ver)
        
        # Разделитель
        line = QFrame()
        line.setFrameShape(QFrame.Shape.HLine)
        line.setFrameShadow(QFrame.Shadow.Sunken)
        layout.addWidget(line)
        
        # 2. Описание и Автор
        # Используем HTML для форматирования и ссылок
        info_text = """
        <p align="center">
            Инструмент для построения и анализа<br>
            тройных диаграмм состояния (Треугольник Гиббса).
        </p>
        <p align="center">
            <b>Автор:</b> Юрьев Илья Олегович<br>
            <b>E-mail:</b> <a href="mailto:i.o.yurev@ya.ru">i.o.yurev@ya.ru</a>
        </p>
        <p align="center">
            <b>Репозиторий:</b><br>
            <a href="https://github.com/your-repo/delta">Git</a>
        </p>
        """
        
        lbl_info = QLabel(info_text)
        lbl_info.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_info.setOpenExternalLinks(True) # ВАЖНО: Делает ссылки кликабельными
        lbl_info.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextBrowserInteraction | 
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        
        layout.addWidget(lbl_info)
        
        layout.addStretch()
        
        # 3. Кнопка закрытия
        btn_close = QPushButton("Закрыть")
        btn_close.clicked.connect(self.accept)
        btn_close.setFixedWidth(100)
        
        # Центрируем кнопку
        h_btn = QVBoxLayout()
        h_btn.addWidget(btn_close, alignment=Qt.AlignmentFlag.AlignCenter)
        layout.addLayout(h_btn)
