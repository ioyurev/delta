from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, 
                               QPushButton, QComboBox, QColorDialog, QGroupBox,
                               QMessageBox)
from core.models import TieLine, NamedComposition, VisualStyle
from typing import Optional
from ui.widgets.helpers import create_line_width_spin
from dataclasses import dataclass


@dataclass
class LineDialogResult:
    uid: str | None
    start_uid: str
    end_uid: str
    color: str
    line_style: str
    width: float

class LineDialog(QDialog):
    result_data: LineDialogResult

    def __init__(self, compositions: list[NamedComposition], current_line: Optional[TieLine] = None, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Line Settings")
        self.setFixedWidth(350)
        
        self.compositions = compositions
        
        layout = QVBoxLayout(self)
        form = QFormLayout()
        
        # 1. Выбор состав
        self.cb_start = QComboBox()
        self.cb_end = QComboBox()
        
        # Заполняем комбобоксы
        sorted_compositions = sorted(compositions, key=lambda p: p.name)
        for p in sorted_compositions:
            nm = p.name if p.name else "[Unnamed]"
            self.cb_start.addItem(nm, p.uid)
            self.cb_end.addItem(nm, p.uid)
            
        form.addRow("Start Composition:", self.cb_start)
        form.addRow("End Composition:", self.cb_end)
        
        # Если редактируем, устанавливаем значения
        self.line_uid = None
        if current_line:
            self.line_uid = current_line.uid
            idx1 = self.cb_start.findData(current_line.start_uid)
            idx2 = self.cb_end.findData(current_line.end_uid)
            if idx1 >= 0:
                self.cb_start.setCurrentIndex(idx1)
            if idx2 >= 0:
                self.cb_end.setCurrentIndex(idx2)
            
            initial_style = current_line.style
        else:
            initial_style = VisualStyle(color="#1f77b4", size=2.0, line_style="-")

        # 2. Стиль
        gb_style = QGroupBox("Appearance")
        form_style = QFormLayout()
        
        # Цвет
        self.btn_color = QPushButton()
        self.current_color = initial_style.color
        self._update_btn_color(self.current_color)
        self.btn_color.clicked.connect(self._pick_color)
        form_style.addRow("Color:", self.btn_color)
        
        # Тип линии
        self.cb_style = QComboBox()
        self.styles_map = {"Solid": "-", "Dashed": "--", "Dotted": ":", "DashDot": "-."}
        for name, code in self.styles_map.items():
            self.cb_style.addItem(name, code)
        
        # Устанавливаем текущий стиль
        cur_style_code = initial_style.line_style
        for i in range(self.cb_style.count()):
            if self.cb_style.itemData(i) == cur_style_code:
                self.cb_style.setCurrentIndex(i)
                break
        form_style.addRow("Style:", self.cb_style)
        
        # Толщина
        self.sb_width = create_line_width_spin(value=initial_style.size)
        form_style.addRow("Width:", self.sb_width)
        
        gb_style.setLayout(form_style)
        layout.addWidget(gb_style)
        layout.addLayout(form)
        
        # Кнопки
        btns = QHBoxLayout()
        btn_ok = QPushButton("OK")
        btn_ok.clicked.connect(self._on_accept)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btns.addWidget(btn_ok)
        btns.addWidget(btn_cancel)
        layout.addLayout(btns)

    def _update_btn_color(self, hex_col):
        self.btn_color.setStyleSheet(f"background-color: {hex_col}; border: 1px solid #555;")
        self.btn_color.setText(hex_col)

    def _pick_color(self):
        c = QColorDialog.getColor(self.current_color, self)
        if c.isValid():
            self.current_color = c.name()
            self._update_btn_color(self.current_color)

    def _on_accept(self):
        uid_start = self.cb_start.currentData()
        uid_end = self.cb_end.currentData()
        
        # Проверка: Start и End должны быть разными
        if uid_start == uid_end:
            QMessageBox.warning(self, "Invalid Line", "Start and End compositions must be different.")
            return

        self.result_data = LineDialogResult(
            uid=self.line_uid,
            start_uid=uid_start,
            end_uid=uid_end,
            color=self.current_color,
            line_style=self.cb_style.currentData(),
            width=self.sb_width.value()
        )
        self.accept()

    def get_data(self) -> LineDialogResult:
        return self.result_data
