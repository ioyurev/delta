from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QGroupBox,
    QPushButton, QListWidget, QListWidgetItem, QMenu,
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QKeyEvent, QAction, QColor, QBrush
from delta.models import ProjectData
from ui.widgets.helpers import mathtext_to_plain

# Маркер типа линии в UserRole+1
_ROLE_TYPE = Qt.ItemDataRole.UserRole + 1
_TYPE_TIE = "tie"
_TYPE_CURVE = "curve"


class LinesManager(QWidget):
    request_add_line = Signal()
    request_add_curve_line = Signal()
    request_edit_line = Signal(str)          # uid TieLine
    request_edit_curve_line = Signal(str)    # uid CurveLine
    request_delete_line = Signal(str)
    request_delete_curve_line = Signal(str)
    request_calc_dialog = Signal()

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)

        # --- Список линий ---
        gb_man = QGroupBox("Lines List")
        l_man = QVBoxLayout()

        self.list_widget = QListWidget()
        self.list_widget.itemDoubleClicked.connect(self._on_edit_click)
        self.list_widget.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.list_widget.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.list_widget.customContextMenuRequested.connect(self._on_context_menu)
        self.list_widget.setToolTip(
            "Double-click to edit. Select and press Delete to remove. Right-click for more options."
        )
        l_man.addWidget(self.list_widget)

        # Кнопки
        btns = QHBoxLayout()

        # Выпадающая кнопка "Add"
        self.btn_add_straight = QPushButton("➕ Add Straight")
        self.btn_add_straight.setToolTip("Create a straight tie-line between two compositions")
        self.btn_add_straight.clicked.connect(self.request_add_line.emit)

        self.btn_add_curve = QPushButton("〜 Add Curve")
        self.btn_add_curve.setToolTip("Create a curved line with optional guide points")
        self.btn_add_curve.clicked.connect(self.request_add_curve_line.emit)

        btn_edit = QPushButton("✏️ Edit")
        btn_edit.setToolTip("Edit selected line properties")
        btn_edit.clicked.connect(self._on_edit_click)

        btn_del = QPushButton("🗑️ Delete")
        btn_del.setToolTip("Delete selected line")
        btn_del.clicked.connect(self._on_delete_click)

        btns.addWidget(self.btn_add_straight)
        btns.addWidget(self.btn_add_curve)
        btns.addWidget(btn_edit)
        btns.addWidget(btn_del)
        l_man.addLayout(btns)

        gb_man.setLayout(l_man)
        layout.addWidget(gb_man, stretch=1)

        # --- Калькулятор ---
        self.btn_calc = QPushButton("📐 Intersection Calculator")
        self.btn_calc.setStyleSheet("""
            QPushButton {
                font-size: 13px;
                padding: 10px;
                font-weight: bold;
            }
        """)
        self.btn_calc.setToolTip("Calculate intersection point of two straight lines")
        self.btn_calc.clicked.connect(self.request_calc_dialog.emit)
        layout.addWidget(self.btn_calc)

        self._current_lines = []

    def update_view(self, project_data: ProjectData) -> None:
        self.list_widget.clear()
        name_map = {p.uid: (p.name or "???") for p in project_data.compositions}

        for line in project_data.lines:
            n1 = mathtext_to_plain(name_map.get(line.start_uid, "Unknown"))
            n2 = mathtext_to_plain(name_map.get(line.end_uid, "Unknown"))
            arrow_mark = " ▶" if line.arrow.enabled else ""
            item = QListWidgetItem(f"─── {n1} — {n2}{arrow_mark}")
            item.setData(Qt.ItemDataRole.UserRole, line.uid)
            item.setData(_ROLE_TYPE, _TYPE_TIE)
            self.list_widget.addItem(item)

        for cline in project_data.curve_lines:
            n1 = mathtext_to_plain(name_map.get(cline.start_uid, "Unknown"))
            n2 = mathtext_to_plain(name_map.get(cline.end_uid, "Unknown"))
            guide_count = len(cline.guide_points)
            guide_mark = f" ({guide_count}pt)" if guide_count else ""
            arrow_mark = " ▶" if cline.arrow.enabled else ""
            item = QListWidgetItem(f"∿── {n1} — {n2}{guide_mark}{arrow_mark}")
            item.setData(Qt.ItemDataRole.UserRole, cline.uid)
            item.setData(_ROLE_TYPE, _TYPE_CURVE)
            # Лёгкое окрашивание строк с кривыми для визуального разделения
            item.setForeground(QBrush(QColor("#1a5276")))
            self.list_widget.addItem(item)

        self.btn_calc.setEnabled(len(project_data.lines) >= 2)

    # =========================================================================
    # ВНУТРЕННИЕ ОБРАБОТЧИКИ
    # =========================================================================

    def _on_edit_click(self):
        item = self.list_widget.currentItem()
        if not item:
            return
        uid = item.data(Qt.ItemDataRole.UserRole)
        line_type = item.data(_ROLE_TYPE)
        if line_type == _TYPE_CURVE:
            self.request_edit_curve_line.emit(uid)
        else:
            self.request_edit_line.emit(uid)

    def _on_delete_click(self):
        item = self.list_widget.currentItem()
        if not item:
            return
        uid = item.data(Qt.ItemDataRole.UserRole)
        line_type = item.data(_ROLE_TYPE)
        if line_type == _TYPE_CURVE:
            self.request_delete_curve_line.emit(uid)
        else:
            self.request_delete_line.emit(uid)

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Delete:
            item = self.list_widget.currentItem()
            if item:
                uid = item.data(Qt.ItemDataRole.UserRole)
                line_type = item.data(_ROLE_TYPE)
                if uid:
                    if line_type == _TYPE_CURVE:
                        self.request_delete_curve_line.emit(uid)
                    else:
                        self.request_delete_line.emit(uid)
                    return

        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._on_edit_click()
            return

        super().keyPressEvent(event)

    def _on_context_menu(self, pos):
        item = self.list_widget.itemAt(pos)
        if not item:
            return
        uid = item.data(Qt.ItemDataRole.UserRole)
        line_type = item.data(_ROLE_TYPE)

        menu = QMenu()

        action_edit = QAction("✏️ Edit…", self)
        if line_type == _TYPE_CURVE:
            action_edit.triggered.connect(lambda: self.request_edit_curve_line.emit(uid))
        else:
            action_edit.triggered.connect(lambda: self.request_edit_line.emit(uid))
        menu.addAction(action_edit)

        menu.addSeparator()

        action_del = QAction("🗑️ Delete", self)
        if line_type == _TYPE_CURVE:
            action_del.triggered.connect(lambda: self.request_delete_curve_line.emit(uid))
        else:
            action_del.triggered.connect(lambda: self.request_delete_line.emit(uid))
        menu.addAction(action_del)

        menu.exec(self.list_widget.mapToGlobal(pos))
