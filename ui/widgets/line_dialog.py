from PySide6.QtWidgets import QFormLayout, QComboBox, QPushButton, QGroupBox, QMessageBox
from ui.widgets.base_dialog import BaseFormDialog
from ui.widgets.helpers import create_line_width_spin, ColorPickerButton
from core.models import TieLine, NamedComposition, VisualStyle
from typing import Optional
from dataclasses import dataclass


@dataclass
class LineDialogResult:
    uid: str | None
    start_uid: str
    end_uid: str
    color: str
    line_style: str
    width: float


class LineDialog(BaseFormDialog[LineDialogResult]):
    def __init__(self, compositions: list[NamedComposition], 
                 current_line: Optional[TieLine] = None, parent=None):
        self._compositions = compositions
        self._current_line = current_line
        self._line_uid = current_line.uid if current_line else None
        self._initial_style = (
            current_line.style if current_line 
            else VisualStyle()
        )
        super().__init__("Line Settings", width=350, parent=parent)
    
    def _init_form(self) -> None:
        # --- Стиль (сверху) ---
        gb_style = QGroupBox("Appearance")
        form_style = QFormLayout()
        
        # Цвет (теперь одна строка!)
        self.btn_color = ColorPickerButton(self._initial_style.color)
        form_style.addRow("Color:", self.btn_color)
        
        # Тип линии
        self.cb_style = QComboBox()
        self._styles_map = {"Solid": "-", "Dashed": "--", "Dotted": ":", "DashDot": "-."}
        for name, code in self._styles_map.items():
            self.cb_style.addItem(name, code)
        
        cur_style_code = self._initial_style.line_style
        for i in range(self.cb_style.count()):
            if self.cb_style.itemData(i) == cur_style_code:
                self.cb_style.setCurrentIndex(i)
                break
        form_style.addRow("Style:", self.cb_style)
        
        # Толщина
        self.sb_width = create_line_width_spin(value=self._initial_style.size)
        form_style.addRow("Width:", self.sb_width)
        
        # Добавляем tooltips для элементов стиля
        self.btn_color.setToolTip("Line color")
        self.cb_style.setToolTip("Line style (solid, dashed, etc.)")
        self.sb_width.setToolTip("Line thickness in points")
        
        gb_style.setLayout(form_style)
        self._layout.addWidget(gb_style)

        # --- Выбор составов ---
        form = QFormLayout()
        
        self.cb_start = QComboBox()
        self.cb_end = QComboBox()
        
        sorted_compositions = sorted(self._compositions, key=lambda p: p.name)
        for p in sorted_compositions:
            nm = p.name if p.name else "[Unnamed]"
            self.cb_start.addItem(nm, p.uid)
            self.cb_end.addItem(nm, p.uid)
            
        form.addRow("Start Composition:", self.cb_start)
        form.addRow("End Composition:", self.cb_end)
        
        # Добавляем tooltips для выбора составов
        self.cb_start.setToolTip("Starting composition of the line")
        self.cb_end.setToolTip("Ending composition of the line")
        
        # Если редактируем существующую линию
        if self._current_line:
            idx1 = self.cb_start.findData(self._current_line.start_uid)
            idx2 = self.cb_end.findData(self._current_line.end_uid)
            if idx1 >= 0:
                self.cb_start.setCurrentIndex(idx1)
            if idx2 >= 0:
                self.cb_end.setCurrentIndex(idx2)
        
        self._layout.addLayout(form)

    def _add_buttons(self) -> None:
        """Переопределяем для валидации перед accept"""
        from PySide6.QtWidgets import QHBoxLayout
        
        btns = QHBoxLayout()
        
        btn_ok = QPushButton("OK")
        btn_ok.clicked.connect(self._on_accept)
        
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        
        btns.addWidget(btn_ok)
        btns.addWidget(btn_cancel)
        self._layout.addLayout(btns)

    def _on_accept(self):
        uid_start = self.cb_start.currentData()
        uid_end = self.cb_end.currentData()
        
        if uid_start == uid_end:
            QMessageBox.warning(self, "Invalid Line", 
                                "Start and End compositions must be different.")
            return

        self.accept()

    def get_data(self) -> LineDialogResult:
        return LineDialogResult(
            uid=self._line_uid,
            start_uid=self.cb_start.currentData(),
            end_uid=self.cb_end.currentData(),
            color=self.btn_color.color(),  # ← Используем метод виджета
            line_style=self.cb_style.currentData(),
            width=self.sb_width.value()
        )
