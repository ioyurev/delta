"""
Калькулятор масс навесок.

Три режима ввода:
- Manual: молярные доли компонентов вершин
- From composition: выбор существующего состава
- Compound ratio: соотношение молей двух или трёх соединений
"""

from __future__ import annotations

import math
from typing import Optional, TYPE_CHECKING

from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QGroupBox, QComboBox, QLabel, QPushButton,
    QDoubleSpinBox, QPlainTextEdit, QRadioButton,
    QButtonGroup, QWidget,
)
from PySide6.QtCore import Qt
from PySide6.QtGui import QFont

from delta.models import Composition, NamedComposition
from delta import math_utils
from delta.constants import EPSILON_ZERO
from ui.widgets.helpers import mathtext_to_plain, populate_combo

if TYPE_CHECKING:
    from delta.project_controller import ProjectController


class NaveskiDialog(QDialog):
    """Диалог расчёта навесок для произвольного состава."""

    def __init__(self, controller: 'ProjectController', parent=None):
        super().__init__(parent)
        self._controller = controller
        self.setWindowTitle("Sample Mass Calculator (Naveski)")
        self.setMinimumWidth(460)
        self.setWindowFlags(
            self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint
        )

        self._comp_names = controller.get_components()
        self._molar_masses = controller.get_component_molar_masses()
        self._all_masses_set = all(m is not None for m in self._molar_masses)

        layout = QVBoxLayout(self)

        # ── Молярные массы (read-only) ───────────────────────────
        gb_masses = QGroupBox("Component Molar Masses (from project)")
        mass_form = QFormLayout(gb_masses)
        for name, m in zip(self._comp_names, self._molar_masses):
            val_text = f"{m:.2f} g/mol" if m is not None else "\u2014 (not set)"
            mass_form.addRow(f"{name}:", QLabel(val_text))
        layout.addWidget(gb_masses)

        if not self._all_masses_set:
            warn = QLabel(
                "\u26a0 Set molar masses for all components in\n"
                "Compositions \u2192 System Settings to enable calculation."
            )
            warn.setStyleSheet("color: #c0392b; font-weight: bold; padding: 4px;")
            layout.addWidget(warn)

        # ── Режим ввода ──────────────────────────────────────────
        gb_source = QGroupBox("Input Mode")
        source_layout = QVBoxLayout(gb_source)

        src_row = QHBoxLayout()
        self._rb_manual = QRadioButton("Mol. fractions")
        self._rb_existing = QRadioButton("Composition")
        self._rb_ratio = QRadioButton("Compound ratio")
        self._rb_ratio.setChecked(True)
        bg = QButtonGroup(self)
        bg.addButton(self._rb_manual)
        bg.addButton(self._rb_existing)
        bg.addButton(self._rb_ratio)
        bg.buttonClicked.connect(self._on_source_changed)
        src_row.addWidget(self._rb_manual)
        src_row.addWidget(self._rb_existing)
        src_row.addWidget(self._rb_ratio)
        source_layout.addLayout(src_row)

        # --- Page: Manual ---
        self._manual_widget = QWidget()
        manual_form = QFormLayout(self._manual_widget)
        manual_form.setContentsMargins(0, 4, 0, 0)
        self._spins: list[QDoubleSpinBox] = []
        for name in self._comp_names:
            spin = QDoubleSpinBox()
            spin.setRange(0.0, 1000.0)
            spin.setDecimals(6)
            spin.setSingleStep(0.01)
            spin.setValue(33.33)
            spin.valueChanged.connect(self._recalculate)
            self._spins.append(spin)
            manual_form.addRow(f"{name}:", spin)
        source_layout.addWidget(self._manual_widget)
        self._manual_widget.hide()

        # --- Page: From existing ---
        self._existing_widget = QWidget()
        exist_form = QFormLayout(self._existing_widget)
        exist_form.setContentsMargins(0, 4, 0, 0)
        self._cb_comp = QComboBox()
        self._cb_comp.currentIndexChanged.connect(self._recalculate)
        exist_form.addRow("Composition:", self._cb_comp)
        source_layout.addWidget(self._existing_widget)
        self._existing_widget.hide()

        # --- Page: Compound ratio ---
        self._ratio_widget = QWidget()
        ratio_layout = QVBoxLayout(self._ratio_widget)
        ratio_layout.setContentsMargins(0, 4, 0, 0)

        self._ratio_rows: list[dict] = []
        self._ratio_form = QVBoxLayout()
        ratio_layout.addLayout(self._ratio_form)

        self._add_ratio_row()
        self._add_ratio_row()

        ratio_btns = QHBoxLayout()
        self._btn_add_compound = QPushButton("+ Add compound")
        self._btn_add_compound.setToolTip("Add a third compound to the ratio")
        self._btn_add_compound.clicked.connect(self._on_add_compound)
        self._btn_remove_compound = QPushButton("\u2212 Remove last")
        self._btn_remove_compound.clicked.connect(self._on_remove_compound)
        ratio_btns.addWidget(self._btn_add_compound)
        ratio_btns.addWidget(self._btn_remove_compound)
        ratio_layout.addLayout(ratio_btns)

        source_layout.addWidget(self._ratio_widget)

        self._populate_all_combos()
        layout.addWidget(gb_source)

        # ── Общая масса ──────────────────────────────────────────
        mass_row = QHBoxLayout()
        mass_row.addWidget(QLabel("Total sample mass:"))
        self._spin_total = QDoubleSpinBox()
        self._spin_total.setRange(0.0001, 9999.9999)
        self._spin_total.setDecimals(4)
        self._spin_total.setSuffix(" g")
        self._spin_total.setValue(0.5)
        self._spin_total.setSingleStep(0.1)
        self._spin_total.valueChanged.connect(self._recalculate)
        mass_row.addWidget(self._spin_total)
        layout.addLayout(mass_row)

        # ── Результат ────────────────────────────────────────────
        self._result_edit = QPlainTextEdit()
        self._result_edit.setReadOnly(True)
        mono = QFont("Courier New")
        mono.setStyleHint(QFont.StyleHint.Monospace)
        mono.setPointSize(10)
        self._result_edit.setFont(mono)
        self._result_edit.setMinimumHeight(200)
        layout.addWidget(self._result_edit)

        # ── Кнопки ───────────────────────────────────────────────
        btn_row = QHBoxLayout()
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        btn_row.addStretch()
        btn_row.addWidget(btn_close)
        layout.addLayout(btn_row)

        self._on_source_changed()
        self._recalculate()

    # =========================================================================
    # RATIO ROWS
    # =========================================================================

    def _add_ratio_row(self) -> None:
        row_widget = QWidget()
        row_layout = QHBoxLayout(row_widget)
        row_layout.setContentsMargins(0, 2, 0, 2)

        cb = QComboBox()
        cb.setMinimumWidth(150)
        cb.currentIndexChanged.connect(self._recalculate)

        spin = QDoubleSpinBox()
        spin.setRange(0.0001, 9999.0)
        spin.setDecimals(4)
        spin.setSingleStep(0.1)
        spin.setValue(1.0)
        spin.setPrefix("n = ")
        spin.setToolTip("Molar amount of this compound")
        spin.valueChanged.connect(self._recalculate)

        row_layout.addWidget(cb)
        row_layout.addWidget(spin)

        self._ratio_rows.append({"widget": row_widget, "combo": cb, "spin": spin})
        self._ratio_form.addWidget(row_widget)

    def _on_add_compound(self) -> None:
        if len(self._ratio_rows) >= 3:
            return
        self._add_ratio_row()
        self._populate_ratio_combos()
        self._btn_add_compound.setEnabled(len(self._ratio_rows) < 3)
        self._btn_remove_compound.setEnabled(len(self._ratio_rows) > 2)
        self._recalculate()

    def _on_remove_compound(self) -> None:
        if len(self._ratio_rows) <= 2:
            return
        row = self._ratio_rows.pop()
        row["widget"].setParent(None)
        row["widget"].deleteLater()
        self._btn_add_compound.setEnabled(len(self._ratio_rows) < 3)
        self._btn_remove_compound.setEnabled(len(self._ratio_rows) > 2)
        self._recalculate()

    # =========================================================================
    # COMBO POPULATION
    # =========================================================================

    def _populate_all_combos(self) -> None:
        comps = sorted(self._controller.get_all_compositions(), key=lambda c: c.name)
        populate_combo(
            self._cb_comp, comps,
            get_text=lambda c: mathtext_to_plain(c.name) if c.name else "[Unnamed]",
            get_data=lambda c: c.uid,
            preserve_selection=False,
        )
        self._populate_ratio_combos()

    def _populate_ratio_combos(self) -> None:
        comps = sorted(self._controller.get_all_compositions(), key=lambda c: c.name)
        for row in self._ratio_rows:
            populate_combo(
                row["combo"], comps,
                get_text=lambda c: mathtext_to_plain(c.name) if c.name else "[Unnamed]",
                get_data=lambda c: c.uid,
                preserve_selection=True,
            )

    # =========================================================================
    # SOURCE SWITCHING
    # =========================================================================

    def _on_source_changed(self) -> None:
        self._manual_widget.setVisible(self._rb_manual.isChecked())
        self._existing_widget.setVisible(self._rb_existing.isChecked())
        self._ratio_widget.setVisible(self._rb_ratio.isChecked())
        self._recalculate()

    # =========================================================================
    # CALCULATION
    # =========================================================================

    def _recalculate(self) -> None:
        if not self._all_masses_set:
            self._result_edit.setPlainText(
                "\u26a0 Cannot calculate: molar masses not set for all components.\n"
                "Set them in Compositions \u2192 System Settings."
            )
            return

        if self._rb_ratio.isChecked():
            self._calculate_ratio_mode()
        elif self._rb_existing.isChecked():
            self._calculate_vertex_mode(self._get_comp_from_existing())
        else:
            self._calculate_vertex_mode(self._get_comp_from_manual())

    def _get_comp_from_manual(self) -> Optional[Composition]:
        a = self._spins[0].value()
        b = self._spins[1].value()
        c = self._spins[2].value()
        comp = Composition(a=a, b=b, c=c)
        return comp if comp.total > EPSILON_ZERO else None

    def _get_comp_from_existing(self) -> Optional[Composition]:
        uid = self._cb_comp.currentData()
        if not uid:
            return None
        nc = self._controller.find_composition(uid)
        return nc.composition if nc else None

    def _calculate_vertex_mode(self, comp: Optional[Composition]) -> None:
        if comp is None:
            self._result_edit.setPlainText("\u26a0 Invalid composition (sum \u2248 0)")
            return

        try:
            a, b, c = comp.normalized
        except (ValueError, ZeroDivisionError):
            self._result_edit.setPlainText("\u26a0 Cannot normalize composition")
            return

        mol_fracs = [a, b, c]
        M_vals = [float(m) for m in self._molar_masses]  # type: ignore[arg-type]
        total_mass = self._spin_total.value()
        names = self._comp_names

        try:
            naveski = math_utils.calculate_naveski(
                mol_fracs=mol_fracs, molar_masses=M_vals, total_mass_g=total_mass,
            )
        except ValueError as e:
            self._result_edit.setPlainText(f"\u26a0 {e}")
            return

        avg_M = math.fsum(x * M for x, M in zip(mol_fracs, M_vals))
        W = max(len(n) for n in names)

        lines = [
            "Mode: vertex molar fractions",
            "",
            "Composition:",
            *[f"  {n:<{W}} : {x:.6f}" for n, x in zip(names, mol_fracs)],
            "",
            f"\u27e8M\u27e9 = {avg_M:.2f} g/mol",
            "",
            f"{'\u2500' * 40}",
            f"Naveski for {total_mass:.4f} g:",
            f"{'\u2500' * 40}",
        ]

        total_check = 0.0
        for name, x, M, m in zip(names, mol_fracs, M_vals, naveski):
            total_check += m
            lines.append(f"  {name:<{W}}  x={x:.4f}  M={M:.2f}  \u2192  {m:.4f} g")

        lines.append(f"{'\u2500' * 40}")
        lines.append(f"  {'Total':<{W}}  {'':>20}  =  {total_check:.4f} g")

        self._result_edit.setPlainText("\n".join(lines))

    def _calculate_ratio_mode(self) -> None:
        m0, m1, m2 = (float(m) for m in self._molar_masses)  # type: ignore[arg-type]
        vertex_masses: tuple[float, float, float] = (m0, m1, m2)
        total_mass = self._spin_total.value()
        names = self._comp_names

        compounds: list[tuple[str, NamedComposition, float]] = []
        for row in self._ratio_rows:
            uid = row["combo"].currentData()
            n = row["spin"].value()
            if not uid:
                self._result_edit.setPlainText("\u26a0 Select compounds")
                return
            nc = self._controller.find_composition(uid)
            if nc is None:
                self._result_edit.setPlainText("\u26a0 Composition not found")
                return
            compounds.append((mathtext_to_plain(nc.name), nc, n))

        if len(compounds) < 2:
            self._result_edit.setPlainText("\u26a0 Need at least 2 compounds")
            return

        M_compounds = []
        for _, nc, _ in compounds:
            M = math_utils.molar_mass_from_vertices(nc.composition, vertex_masses)
            M_compounds.append(M)

        raw_masses = [n * M for (_, _, n), M in zip(compounds, M_compounds)]
        raw_total = math.fsum(raw_masses)

        if raw_total < EPSILON_ZERO:
            self._result_edit.setPlainText("\u26a0 Total mass is zero")
            return

        naveski = [m / raw_total * total_mass for m in raw_masses]

        total_moles = math.fsum(n for _, _, n in compounds)
        mol_fracs_compounds = [n / total_moles for _, _, n in compounds]

        result_a, result_b, result_c = 0.0, 0.0, 0.0
        for (_, nc, _), mol_frac in zip(compounds, mol_fracs_compounds):
            n_total = nc.composition.total
            if n_total < EPSILON_ZERO:
                continue
            a_n, b_n, c_n = nc.composition.normalized
            atom_frac = mol_frac * n_total
            result_a += atom_frac * a_n
            result_b += atom_frac * b_n
            result_c += atom_frac * c_n

        total_abc = result_a + result_b + result_c
        if total_abc > EPSILON_ZERO:
            result_a /= total_abc
            result_b /= total_abc
            result_c /= total_abc

        W = max(len(name) for name, _, _ in compounds)
        W = max(W, max(len(n) for n in names))

        lines = [
            "Mode: compound molar ratio",
            "",
            "Compounds:",
        ]

        for (name, _, n), M, mf in zip(compounds, M_compounds, mol_fracs_compounds):
            lines.append(f"  {name:<{W}}  n={n:.4f}  mol.%={mf*100:.2f}%  M={M:.2f} g/mol")

        lines.extend([
            "",
            "Resulting vertex composition:",
            f"  {names[0]:<{W}} : {result_a:.6f}",
            f"  {names[1]:<{W}} : {result_b:.6f}",
            f"  {names[2]:<{W}} : {result_c:.6f}",
            "",
            f"{'\u2500' * 44}",
            f"Naveski for {total_mass:.4f} g:",
            f"{'\u2500' * 44}",
        ])

        total_check = 0.0
        for (name, _, n), M, m in zip(compounds, M_compounds, naveski):
            total_check += m
            lines.append(f"  {name:<{W}}  n={n:.4f}  M={M:.2f}  \u2192  {m:.4f} g")

        lines.append(f"{'\u2500' * 44}")
        lines.append(f"  {'Total':<{W}}  {'':>22}  =  {total_check:.4f} g")

        self._result_edit.setPlainText("\n".join(lines))
