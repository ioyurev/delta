from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, 
                               QPushButton, QComboBox, QColorDialog, 
                               QCheckBox, QGroupBox)
from ui.widgets.helpers import create_marker_size_spin
from core.models import NamedComposition
from dataclasses import dataclass


@dataclass
class CompositionStyleSettings:
    color: str
    size: float
    symbol: str
    show_label: bool
    show_marker: bool

class CompositionStyleDialog(QDialog):
    def __init__(self, comp: NamedComposition, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Composition Marker Settings")
        self.setFixedWidth(320)
        
        # Сохраняем текущий цвет отдельно, так как его неудобно доставать из кнопки
        self._current_color: str = comp.style.color
        
        layout = QVBoxLayout(self)
        form = QFormLayout()
        
        # --- Цвет ---
        self.btn_color = QPushButton()
        self._update_btn_color(self._current_color)
        self.btn_color.clicked.connect(self._pick_color)
        form.addRow("Color:", self.btn_color)
        
        # --- Размер ---
        # Здесь мы берем значение прямо из переданного объекта comp
        self.sp_size = create_marker_size_spin(value=comp.style.size)
        form.addRow("Size:", self.sp_size)
        
        # --- Форма ---
        self.cb_symbol = QComboBox()
        self.markers = {
            "Circle (●)": "o", "Square (■)": "s", "Triangle Up (▲)": "^",
            "Triangle Down (▼)": "v", "Diamond (◆)": "D", "Star (★)": "*",
            "Cross (x)": "x", "Plus (+)": "P"
        }
        for name, code in self.markers.items():
            self.cb_symbol.addItem(name, code)
            
        idx = self.cb_symbol.findData(comp.style.marker_symbol)
        if idx >= 0:
            self.cb_symbol.setCurrentIndex(idx)
        form.addRow("Shape:", self.cb_symbol)
        
        layout.addLayout(form)

        # --- Видимость ---
        gb_vis = QGroupBox("Visibility")
        v_vis = QVBoxLayout()
        
        self.chk_marker = QCheckBox("Show Marker (Symbol)")
        self.chk_marker.setChecked(comp.style.show_marker)
        
        self.chk_label = QCheckBox("Show Text Label")
        self.chk_label.setChecked(comp.style.show_label)
        
        v_vis.addWidget(self.chk_marker)
        v_vis.addWidget(self.chk_label)
        gb_vis.setLayout(v_vis)
        layout.addWidget(gb_vis)
        
        # --- Кнопки ---
        btns = QHBoxLayout()
        btn_ok = QPushButton("OK")
        btn_ok.clicked.connect(self.accept)
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btns.addWidget(btn_ok)
        btns.addWidget(btn_cancel)
        layout.addLayout(btns)

    def _update_btn_color(self, hex_col: str) -> None:
        self.btn_color.setStyleSheet(f"background-color: {hex_col}; border: 1px solid #555;")
        self.btn_color.setText(hex_col)

    def _pick_color(self) -> None:
        c = QColorDialog.getColor(self._current_color, self)
        if c.isValid():
            self._current_color = c.name()
            self._update_btn_color(self._current_color)

    # Возвращаем типизированный объект, собирая данные из виджетов
    def get_data(self) -> CompositionStyleSettings:
        return CompositionStyleSettings(
            color=self._current_color,
            size=self.sp_size.value(),     # Возвращает float -> ошибки mypy не будет
            symbol=self.cb_symbol.currentData(),
            show_marker=self.chk_marker.isChecked(), # Возвращает bool
            show_label=self.chk_label.isChecked()    # Возвращает bool
        )
