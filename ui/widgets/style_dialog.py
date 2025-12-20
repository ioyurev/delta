from PySide6.QtWidgets import QFormLayout, QComboBox, QCheckBox, QGroupBox, QVBoxLayout
from ui.widgets.helpers import create_marker_size_spin, ColorPickerButton
from ui.widgets.base_dialog import BaseFormDialog
from core.models import NamedComposition
from dataclasses import dataclass


@dataclass
class CompositionStyleSettings:
    color: str
    size: float
    symbol: str
    show_label: bool
    show_marker: bool


class CompositionStyleDialog(BaseFormDialog[CompositionStyleSettings]):
    def __init__(self, comp: NamedComposition, parent=None):
        self._comp = comp
        super().__init__("Composition Marker Settings", width=320, parent=parent)
    
    def _init_form(self) -> None:
        form = QFormLayout()
        
        # --- Цвет (теперь одна строка!) ---
        self.btn_color = ColorPickerButton(self._comp.style.color)
        form.addRow("Color:", self.btn_color)
        
        # --- Размер ---
        self.sp_size = create_marker_size_spin(value=self._comp.style.size)
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
            
        idx = self.cb_symbol.findData(self._comp.style.marker_symbol)
        if idx >= 0:
            self.cb_symbol.setCurrentIndex(idx)
        form.addRow("Shape:", self.cb_symbol)
        
        # Добавляем tooltips для элементов формы
        self.btn_color.setToolTip("Marker color")
        self.sp_size.setToolTip("Marker size in points")
        self.cb_symbol.setToolTip("Marker shape")
        
        self._layout.addLayout(form)

        # --- Видимость ---
        gb_vis = QGroupBox("Visibility")
        v_vis = QVBoxLayout()
        
        self.chk_marker = QCheckBox("Show Marker (Symbol)")
        self.chk_marker.setChecked(self._comp.style.show_marker)
        
        self.chk_label = QCheckBox("Show Text Label")
        self.chk_label.setChecked(self._comp.style.show_label)
        
        # Добавляем tooltips для переключателей видимости
        self.chk_marker.setToolTip("Show/hide the marker symbol on diagram")
        self.chk_label.setToolTip("Show/hide the text label on diagram")
        
        v_vis.addWidget(self.chk_marker)
        v_vis.addWidget(self.chk_label)
        gb_vis.setLayout(v_vis)
        self._layout.addWidget(gb_vis)

    def get_data(self) -> CompositionStyleSettings:
        return CompositionStyleSettings(
            color=self.btn_color.color(),  # ← Используем метод виджета
            size=self.sp_size.value(),
            symbol=self.cb_symbol.currentData(),
            show_marker=self.chk_marker.isChecked(),
            show_label=self.chk_label.isChecked()
        )
