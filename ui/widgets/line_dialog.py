from PySide6.QtWidgets import (
    QFormLayout, QComboBox, QPushButton, QGroupBox, QMessageBox,
    QCheckBox, QHBoxLayout, QSpinBox,
)
from ui.widgets.base_dialog import BaseFormDialog
from ui.widgets.helpers import create_line_width_spin, ColorPickerButton
from delta.models import TieLine, NamedComposition, VisualStyle, ArrowSettings
from delta.constants import LINE_WIDTH_DEFAULT, ARROW_COUNT_MIN, ARROW_COUNT_MAX
from typing import Optional
from dataclasses import dataclass, field


@dataclass
class LineDialogResult:
    uid: str | None
    start_uid: str
    end_uid: str
    color: str
    line_style: str
    width: float
    arrow: ArrowSettings = field(default_factory=ArrowSettings)


class LineDialog(BaseFormDialog[LineDialogResult]):
    def __init__(self, compositions: list[NamedComposition],
                 current_line: Optional[TieLine] = None, parent=None):
        self._compositions = compositions
        self._current_line = current_line
        self._line_uid = current_line.uid if current_line else None
        self._initial_style = (
            current_line.style if current_line
            else VisualStyle(size=LINE_WIDTH_DEFAULT)
        )
        self._initial_arrow = current_line.arrow if current_line else ArrowSettings()
        super().__init__("Line Settings", width=350, parent=parent)

    def _init_form(self) -> None:
        # --- Стиль ---
        gb_style = QGroupBox("Appearance")
        form_style = QFormLayout()

        self.btn_color = ColorPickerButton(self._initial_style.color)
        self.btn_color.setToolTip("Line color")
        form_style.addRow("Color:", self.btn_color)

        self.cb_style = QComboBox()
        self._styles_map = {"Solid": "-", "Dashed": "--", "Dotted": ":", "DashDot": "-."}
        for name, code in self._styles_map.items():
            self.cb_style.addItem(name, code)
        cur_style_code = self._initial_style.line_style
        for i in range(self.cb_style.count()):
            if self.cb_style.itemData(i) == cur_style_code:
                self.cb_style.setCurrentIndex(i)
                break
        self.cb_style.setToolTip("Line style (solid, dashed, etc.)")
        form_style.addRow("Style:", self.cb_style)

        self.sb_width = create_line_width_spin(value=self._initial_style.size)
        self.sb_width.setToolTip("Line thickness in points")
        form_style.addRow("Width:", self.sb_width)

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

        self.cb_start.setToolTip("Starting composition of the line")
        self.cb_end.setToolTip("Ending composition of the line")
        form.addRow("Start:", self.cb_start)
        form.addRow("End:", self.cb_end)

        if self._current_line:
            idx1 = self.cb_start.findData(self._current_line.start_uid)
            idx2 = self.cb_end.findData(self._current_line.end_uid)
            if idx1 >= 0:
                self.cb_start.setCurrentIndex(idx1)
            if idx2 >= 0:
                self.cb_end.setCurrentIndex(idx2)

        self._layout.addLayout(form)

        # --- Стрелки ---
        self._init_arrow_section()

    def _init_arrow_section(self) -> None:
        gb_arrow = QGroupBox("Arrows")
        form = QFormLayout()

        self.chk_arrows = QCheckBox("Show arrows")
        self.chk_arrows.setChecked(self._initial_arrow.enabled)
        self.chk_arrows.setToolTip("Draw directional arrows along the line")
        form.addRow(self.chk_arrows)

        self.cb_arrow_dir = QComboBox()
        self.cb_arrow_dir.addItem("→ to End", "to_end")
        self.cb_arrow_dir.addItem("← to Start", "to_start")
        idx = self.cb_arrow_dir.findData(self._initial_arrow.direction)
        if idx >= 0:
            self.cb_arrow_dir.setCurrentIndex(idx)
        self.cb_arrow_dir.setToolTip("Direction arrows point along the line")
        form.addRow("Direction:", self.cb_arrow_dir)

        self.sb_arrow_count = QSpinBox()
        self.sb_arrow_count.setRange(ARROW_COUNT_MIN, ARROW_COUNT_MAX)
        self.sb_arrow_count.setValue(self._initial_arrow.count)
        self.sb_arrow_count.setToolTip("Number of arrows along the line")
        form.addRow("Count:", self.sb_arrow_count)

        # Disable direction/count when arrows are off
        self._update_arrow_controls(self.chk_arrows.isChecked())
        self.chk_arrows.toggled.connect(self._update_arrow_controls)

        gb_arrow.setLayout(form)
        self._layout.addWidget(gb_arrow)

    def _update_arrow_controls(self, enabled: bool) -> None:
        self.cb_arrow_dir.setEnabled(enabled)
        self.sb_arrow_count.setEnabled(enabled)

    def _add_buttons(self) -> None:
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
            color=self.btn_color.color(),
            line_style=self.cb_style.currentData(),
            width=self.sb_width.value(),
            arrow=ArrowSettings(
                enabled=self.chk_arrows.isChecked(),
                direction=self.cb_arrow_dir.currentData(),
                count=self.sb_arrow_count.value(),
            ),
        )
