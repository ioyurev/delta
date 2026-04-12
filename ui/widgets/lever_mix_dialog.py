"""
Диалог создания состава по правилу рычага (Lever Mix).

Позволяет задать два конечных члена из списка составов проекта
и молярную долю второго, получить результирующий состав в координатах
вершин треугольника и добавить его в проект с предпросмотром маркера.
"""

from __future__ import annotations

from typing import Optional, List

from PySide6.QtCore import Signal, Qt
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QGroupBox, QComboBox, QLabel, QPushButton,
    QDoubleSpinBox,
)

from delta.models import Composition, NamedComposition
from delta import math_utils
from delta.constants import DISPLAY_DECIMALS_ANALYSIS
from ui.widgets.helpers import MarkerStyleWidget, mathtext_to_plain


class LeverMixDialog(QDialog):
    """
    Немодальный диалог «Lever Mix».

    Сигналы:
        preview_changed(tuple | None)
            tuple = (result: Composition, end_a: Composition, end_b: Composition,
                     style: MarkerStyleData)
            None  = состав вырожден / ошибка / диалог закрыт

        composition_accepted(tuple)
            tuple = (result: Composition, style: MarkerStyleData)
    """

    preview_changed = Signal(object)        # tuple | None
    composition_accepted = Signal(object)   # tuple (Composition, MarkerStyleData)

    def __init__(
        self,
        compositions: List[NamedComposition],
        components: List[str],
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Lever Mix — Create Composition")
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )
        self.setMinimumWidth(340)

        self._compositions = compositions
        self._components = components if components else ["A", "B", "C"]
        self._result: Optional[Composition] = None

        layout = QVBoxLayout(self)

        # ── End-members ────────────────────────────────────────────
        gb = QGroupBox("End-members")
        form = QFormLayout(gb)
        form.setSpacing(6)

        self._cb_a = QComboBox()
        self._cb_b = QComboBox()
        self._populate_combos()
        form.addRow("End-member A:", self._cb_a)
        form.addRow("End-member B:", self._cb_b)

        self._spin = QDoubleSpinBox()
        self._spin.setRange(0.0, 100.0)
        self._spin.setValue(50.0)
        self._spin.setSuffix(" mol%")
        self._spin.setDecimals(2)
        self._spin.setSingleStep(1.0)
        self._spin.setToolTip("Mole percent of end-member B;\nend-member A = 100 − this value")
        form.addRow("Mol% of B:", self._spin)

        layout.addWidget(gb)

        # ── Marker style ────────────────────────────────────────────
        gb_style = QGroupBox("Marker Style")
        style_layout = QVBoxLayout(gb_style)
        style_layout.setContentsMargins(6, 6, 6, 6)
        self._style_widget = MarkerStyleWidget(
            color="#e67e00", symbol="*", size=14.0
        )
        self._style_widget.style_changed.connect(self._recalculate)
        style_layout.addWidget(self._style_widget)
        layout.addWidget(gb_style)

        # ── Result ─────────────────────────────────────────────────
        self._lbl_result = QLabel("—")
        self._lbl_result.setWordWrap(True)
        self._lbl_result.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._lbl_result.setTextInteractionFlags(
            Qt.TextInteractionFlag.TextSelectableByMouse
        )
        self._lbl_result.setStyleSheet(
            "padding: 6px; border: 1px solid palette(mid); border-radius: 4px;"
        )
        layout.addWidget(self._lbl_result)

        # ── Buttons ────────────────────────────────────────────────
        btn_row = QHBoxLayout()
        self._btn_add = QPushButton("Add to Project")
        self._btn_add.setEnabled(False)
        self._btn_add.clicked.connect(self._on_add_clicked)
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.close)
        btn_row.addWidget(self._btn_add)
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

        # ── Signals ────────────────────────────────────────────────
        self._cb_a.currentIndexChanged.connect(self._recalculate)
        self._cb_b.currentIndexChanged.connect(self._recalculate)
        self._spin.valueChanged.connect(self._recalculate)

        self._recalculate()

    # =========================================================================
    # Public API
    # =========================================================================

    def refresh_compositions(self, compositions: List[NamedComposition]) -> None:
        """Обновляет список составов (вызывается из main_window при изменении проекта)."""
        prev_a = self._cb_a.currentData()
        prev_b = self._cb_b.currentData()
        self._compositions = compositions
        self._populate_combos()
        self._restore_selection(self._cb_a, prev_a)
        self._restore_selection(self._cb_b, prev_b)
        self._recalculate()

    # =========================================================================
    # Private
    # =========================================================================

    def _populate_combos(self) -> None:
        for cb in (self._cb_a, self._cb_b):
            cb.blockSignals(True)
            cb.clear()
            for nc in sorted(self._compositions, key=lambda p: p.name):
                cb.addItem(mathtext_to_plain(nc.name) if nc.name else "[Unnamed]", userData=nc.uid)
            cb.blockSignals(False)

    def _restore_selection(self, cb: QComboBox, uid: Optional[str]) -> None:
        if uid is None:
            return
        for i in range(cb.count()):
            if cb.itemData(i) == uid:
                cb.setCurrentIndex(i)
                return

    def _recalculate(self, *_: object) -> None:
        uid_a = self._cb_a.currentData()
        uid_b = self._cb_b.currentData()

        nc_a = next((c for c in self._compositions if c.uid == uid_a), None)
        nc_b = next((c for c in self._compositions if c.uid == uid_b), None)

        if nc_a is None or nc_b is None:
            self._set_error("Select two compositions.")
            return

        if uid_a == uid_b:
            self._set_error("End-members must be different.")
            return

        mol_frac_b = self._spin.value() / 100.0
        mol_frac_a = 1.0 - mol_frac_b
        try:
            result = math_utils.mix_compositions_by_mol_frac(
                nc_a.composition, mol_frac_a, nc_b.composition
            )
        except ValueError as exc:
            self._set_error(str(exc))
            return

        self._result = result
        self._btn_add.setEnabled(True)

        d = DISPLAY_DECIMALS_ANALYSIS
        lbl = self._components
        la = lbl[0] if len(lbl) > 0 else "A"
        lb = lbl[1] if len(lbl) > 1 else "B"
        lc = lbl[2] if len(lbl) > 2 else "C"
        mol_a = 100.0 - self._spin.value()
        na = mathtext_to_plain(nc_a.name) if nc_a.name else "[Unnamed]"
        nb = mathtext_to_plain(nc_b.name) if nc_b.name else "[Unnamed]"
        self._lbl_result.setText(
            f"<b>{na}</b> {mol_a:.2f} mol% + "
            f"<b>{nb}</b> {self._spin.value():.2f} mol%<br>"
            f"{la}: <b>{result.a:.{d}f}</b> &nbsp; "
            f"{lb}: <b>{result.b:.{d}f}</b> &nbsp; "
            f"{lc}: <b>{result.c:.{d}f}</b>"
        )
        self._lbl_result.setStyleSheet(
            "padding: 6px; border: 1px solid palette(mid); border-radius: 4px;"
        )
        style = self._style_widget.get_data()
        self.preview_changed.emit((result, nc_a.composition, nc_b.composition, style))

    def _set_error(self, message: str) -> None:
        self._result = None
        self._btn_add.setEnabled(False)
        self._lbl_result.setText(message)
        self._lbl_result.setStyleSheet(
            "color: #c0392b; padding: 6px; "
            "border: 1px solid #c0392b; border-radius: 4px;"
        )
        self.preview_changed.emit(None)

    def _on_add_clicked(self) -> None:
        if self._result is not None:
            style = self._style_widget.get_data()
            self.composition_accepted.emit((self._result, style))

    def closeEvent(self, event) -> None:  # type: ignore[override]
        self.preview_changed.emit(None)
        super().closeEvent(event)
