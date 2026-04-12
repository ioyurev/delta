from PySide6.QtWidgets import QCheckBox, QGroupBox, QVBoxLayout
from ui.widgets.helpers import MarkerStyleWidget
from ui.widgets.base_dialog import BaseFormDialog
from delta.models import NamedComposition
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
        self._marker_widget = MarkerStyleWidget(
            color=self._comp.style.color,
            symbol=self._comp.style.marker_symbol,
            size=self._comp.style.size,
        )
        self._layout.addWidget(self._marker_widget)

        # --- Видимость ---
        gb_vis = QGroupBox("Visibility")
        v_vis = QVBoxLayout()

        self.chk_marker = QCheckBox("Show Marker (Symbol)")
        self.chk_marker.setChecked(self._comp.style.show_marker)
        self.chk_marker.setToolTip("Show/hide the marker symbol on diagram")

        self.chk_label = QCheckBox("Show Text Label")
        self.chk_label.setChecked(self._comp.style.show_label)
        self.chk_label.setToolTip("Show/hide the text label on diagram")

        v_vis.addWidget(self.chk_marker)
        v_vis.addWidget(self.chk_label)
        gb_vis.setLayout(v_vis)
        self._layout.addWidget(gb_vis)

    def get_data(self) -> CompositionStyleSettings:
        ms = self._marker_widget.get_data()
        return CompositionStyleSettings(
            color=ms.color,
            size=ms.size,
            symbol=ms.symbol,
            show_marker=self.chk_marker.isChecked(),
            show_label=self.chk_label.isChecked(),
        )
