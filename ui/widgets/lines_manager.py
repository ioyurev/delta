from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, 
                               QPushButton, QListWidget, QListWidgetItem)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QKeyEvent
from core.models import ProjectData

class LinesManager(QWidget):
    request_add_line = Signal()
    request_edit_line = Signal(str)
    request_delete_line = Signal(str)
    
    # Новый сигнал для открытия диалога
    request_calc_dialog = Signal()

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        
        # 1. Список линий
        gb_man = QGroupBox("Lines List")
        l_man = QVBoxLayout()
        
        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self._on_edit_click)
        
        # Устанавливаем фокус-политику для списка
        self.list_widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
        l_man.addWidget(self.list_widget)
        
        # Добавляем tooltip для списка линий
        self.list_widget.setToolTip("Double-click to edit line. Select and press Delete to remove.")
        
        btns = QHBoxLayout()
        btn_add = QPushButton("➕ Create")
        btn_add.clicked.connect(self.request_add_line.emit)
        btn_edit = QPushButton("✏️ Edit")
        btn_edit.clicked.connect(self._on_edit_click)
        btn_del = QPushButton("🗑️ Delete")
        btn_del.clicked.connect(self._on_delete_click)
        
        # Добавляем tooltips для кнопок
        btn_add.setToolTip("Create a new tie-line between two compositions")
        btn_edit.setToolTip("Edit selected line properties")
        btn_del.setToolTip("Delete selected line")
        
        btns.addWidget(btn_add)
        btns.addWidget(btn_edit)
        btns.addWidget(btn_del)
        l_man.addLayout(btns)
        gb_man.setLayout(l_man)
        
        layout.addWidget(gb_man, stretch=1)

        # 2. Большая кнопка Калькулятора (ВМЕСТО старого виджета)
        btn_calc = QPushButton("📐 Intersection Calculator")
        btn_calc.setStyleSheet("""
            QPushButton {
                font-size: 13px;
                padding: 10px;
                font-weight: bold;
            }
        """)
        btn_calc.clicked.connect(self.request_calc_dialog.emit)
        
        # Добавляем tooltip для кнопки калькулятора
        btn_calc.setToolTip("Calculate intersection point of two lines")
        
        layout.addWidget(btn_calc)
        
        self._current_lines = []

    def update_view(self, project_data: ProjectData) -> None:
        self.list_widget.clear()
        self._current_lines = project_data.lines
        name_map = {p.uid: (p.name if p.name else "???") for p in project_data.compositions}  # ← Используем project_data.compositions
        
        for line in project_data.lines:  # ← Используем project_data.lines
            n1 = name_map.get(line.start_uid, "Unknown")
            n2 = name_map.get(line.end_uid, "Unknown")
            item = QListWidgetItem(f"{n1} — {n2}")
            item.setData(Qt.ItemDataRole.UserRole, line.uid)  # Сохраняем UID в элементе
            self.list_widget.addItem(item)

    def _on_edit_click(self):
        item = self.list_widget.currentItem()
        if item:
            uid = item.data(Qt.ItemDataRole.UserRole)  # Берем UID из элемента
            self.request_edit_line.emit(uid)

    def _on_delete_click(self):
        item = self.list_widget.currentItem()
        if item:
            uid = item.data(Qt.ItemDataRole.UserRole)  # Берем UID из элемента
            self.request_delete_line.emit(uid)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Обработка нажатий клавиш"""
        if event.key() == Qt.Key.Key_Delete:
            item = self.list_widget.currentItem()
            if item:
                uid = item.data(Qt.ItemDataRole.UserRole)
                if uid:
                    self.request_delete_line.emit(uid)
                    return
        
        if event.key() == Qt.Key.Key_Return or event.key() == Qt.Key.Key_Enter:
            item = self.list_widget.currentItem()
            if item:
                uid = item.data(Qt.ItemDataRole.UserRole)
                if uid:
                    self.request_edit_line.emit(uid)
                    return
        
        super().keyPressEvent(event)
