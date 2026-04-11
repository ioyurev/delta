"""
Диалог редактирования кривой линии (CurveLine).

Позволяет:
- Задать start/end составы
- Управлять guide-точками: через таблицу или клик по холсту (значения нормируются)
- Настроить маркеры guide-точек (цвет, символ, размер)
- Настроить стиль и стрелки
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, List, TYPE_CHECKING

from typing import cast

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QFormLayout,
    QGroupBox, QComboBox, QPushButton, QCheckBox,
    QSpinBox, QHeaderView,
    QMessageBox, QLabel, QDoubleSpinBox, QSizePolicy,
)

from delta.models import (
    CurveLine, NamedComposition, VisualStyle, ArrowSettings, GuidePoint, Composition,
)
from delta.constants import LINE_WIDTH_DEFAULT, ARROW_COUNT_MIN, ARROW_COUNT_MAX
from ui.widgets.helpers import (
    create_line_width_spin, create_marker_size_spin,
    ColorPickerButton, CopyableTableWidget,
)

if TYPE_CHECKING:
    pass


@dataclass
class CurveLineDialogResult:
    uid: Optional[str]
    start_uid: str
    end_uid: str
    guide_points: List[GuidePoint]
    color: str
    line_style: str
    width: float
    poly_degree: int = 3
    show_guide_markers: bool = False
    guide_marker_color: str = "#888888"
    guide_marker_symbol: str = "o"
    guide_marker_size: float = 4.0
    arrow: ArrowSettings = field(default_factory=ArrowSettings)


class CurveLineDialog(QDialog):
    """
    Немодальный диалог редактирования CurveLine.

    Сигнал request_canvas_pick испускается, когда пользователь нажимает
    «Pick from Canvas» — главное окно переключает интерактор в режим GUIDE_PICK
    и потом вызывает add_guide_point_from_canvas().
    """

    request_canvas_pick = Signal()

    def __init__(
        self,
        compositions: List[NamedComposition],
        current_line: Optional[CurveLine] = None,
        components: Optional[List[str]] = None,
        parent=None,
    ):
        super().__init__(parent)
        self._compositions = compositions
        self._current_line = current_line
        self._line_uid = current_line.uid if current_line else None
        self._components = components if components else ["A", "B", "C"]

        self._initial_style = (
            current_line.style if current_line
            else VisualStyle(size=LINE_WIDTH_DEFAULT)
        )
        self._initial_arrow = current_line.arrow if current_line else ArrowSettings()
        self._initial_gm_style = (
            current_line.guide_marker_style if current_line
            else VisualStyle(color="#888888")
        )
        self._initial_show_gm = current_line.show_guide_markers if current_line else False

        self.setWindowTitle("Curve Line" if not current_line else "Edit Curve Line")
        self.setMinimumWidth(440)
        # Не WindowModal — остаётся поверх главного окна, но не блокирует холст
        self.setWindowModality(Qt.WindowModality.NonModal)

        layout = QVBoxLayout(self)
        self._layout = layout

        self._init_appearance()
        self._init_endpoints()
        self._init_guide_points()
        self._init_guide_markers()
        self._init_arrow_section()
        self._init_buttons()

    # =========================================================================
    # СЕКЦИИ ФОРМЫ
    # =========================================================================

    def _init_appearance(self) -> None:
        gb = QGroupBox("Appearance")
        form = QFormLayout()

        self.btn_color = ColorPickerButton(self._initial_style.color)
        self.btn_color.setToolTip("Line color")
        form.addRow("Color:", self.btn_color)

        self.cb_style = QComboBox()
        self._styles_map = {"Solid": "-", "Dashed": "--", "Dotted": ":", "DashDot": "-."}
        for name, code in self._styles_map.items():
            self.cb_style.addItem(name, code)
        cur = self._initial_style.line_style
        for i in range(self.cb_style.count()):
            if self.cb_style.itemData(i) == cur:
                self.cb_style.setCurrentIndex(i)
                break
        self.cb_style.setToolTip("Line style")
        form.addRow("Style:", self.cb_style)

        self.sb_width = create_line_width_spin(value=self._initial_style.size)
        self.sb_width.setToolTip("Line thickness in points")
        form.addRow("Width:", self.sb_width)

        self.cb_degree = QComboBox()
        degree_items = [
            ("Quadratic (2)", 2),
            ("Cubic (3)", 3),
            ("Degree 4", 4),
            ("Degree 5", 5),
        ]
        for label, val in degree_items:
            self.cb_degree.addItem(label, val)
        current_degree = self._current_line.poly_degree if self._current_line else 3
        for i in range(self.cb_degree.count()):
            if self.cb_degree.itemData(i) == current_degree:
                self.cb_degree.setCurrentIndex(i)
                break
        self.cb_degree.setToolTip(
            "Polynomial degree for curve fitting.\n"
            "Higher degree = more flexible curve, but may oscillate with few guide points."
        )
        form.addRow("Degree:", self.cb_degree)

        gb.setLayout(form)
        self._layout.addWidget(gb)

    def _init_endpoints(self) -> None:
        gb = QGroupBox("Endpoints")
        form = QFormLayout()

        self.cb_start = QComboBox()
        self.cb_end = QComboBox()

        sorted_comps = sorted(self._compositions, key=lambda p: p.name)
        for p in sorted_comps:
            nm = p.name or "[Unnamed]"
            self.cb_start.addItem(nm, p.uid)
            self.cb_end.addItem(nm, p.uid)

        if self._current_line:
            idx1 = self.cb_start.findData(self._current_line.start_uid)
            idx2 = self.cb_end.findData(self._current_line.end_uid)
            if idx1 >= 0:
                self.cb_start.setCurrentIndex(idx1)
            if idx2 >= 0:
                self.cb_end.setCurrentIndex(idx2)

        self.cb_start.setToolTip("Starting composition (curve passes through exactly)")
        self.cb_end.setToolTip("Ending composition (curve passes through exactly)")
        form.addRow("Start:", self.cb_start)
        form.addRow("End:", self.cb_end)

        gb.setLayout(form)
        self._layout.addWidget(gb)

    def _init_guide_points(self) -> None:
        gb = QGroupBox("Guide Points  (approximated, endpoints are fixed)")
        vbox = QVBoxLayout()

        # Таблица: # | comp_A | comp_B | comp_C | [delete]
        self.table = CopyableTableWidget(0, 4)
        col_labels = list(self._components) + [""]
        self.table.setHorizontalHeaderLabels(col_labels)
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        self.table.horizontalHeader().setSectionResizeMode(3, QHeaderView.ResizeMode.Fixed)
        self.table.setColumnWidth(3, 28)
        self.table.verticalHeader().setVisible(True)
        self.table.setMinimumHeight(120)
        self.table.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        self.table.setToolTip("Molar fractions — auto-normalized to sum = 1")
        vbox.addWidget(self.table)

        # Заполняем из текущей линии
        if self._current_line:
            for gp in self._current_line.guide_points:
                self._append_guide_row(gp.composition)

        # Кнопки
        btn_row = QHBoxLayout()
        btn_add_row = QPushButton("+ Add Row")
        btn_add_row.setToolTip("Add a blank guide point row")
        btn_add_row.clicked.connect(self._on_add_row)

        self.btn_pick = QPushButton("📍 Pick from Canvas")
        self.btn_pick.setToolTip(
            "Click to enter pick mode, then click on the diagram to add a guide point"
        )
        self.btn_pick.clicked.connect(self._on_pick_from_canvas)

        btn_row.addWidget(btn_add_row)
        btn_row.addWidget(self.btn_pick)
        vbox.addLayout(btn_row)

        self._pick_label = QLabel("")
        self._pick_label.setStyleSheet("color: #888; font-style: italic; font-size: 11px;")
        vbox.addWidget(self._pick_label)

        lbl_norm = QLabel("Values are auto-normalized: sum(fractions) = 1")
        lbl_norm.setStyleSheet("color: #888; font-size: 10px;")
        vbox.addWidget(lbl_norm)

        gb.setLayout(vbox)
        self._layout.addWidget(gb)

    def _init_guide_markers(self) -> None:
        gb = QGroupBox("Guide Markers")
        form = QFormLayout()

        self.chk_gm = QCheckBox("Show markers at guide points")
        self.chk_gm.setChecked(self._initial_show_gm)
        self.chk_gm.setToolTip("Draw a marker symbol at each guide point position")
        form.addRow(self.chk_gm)

        self.btn_gm_color = ColorPickerButton(self._initial_gm_style.color)
        self.btn_gm_color.setToolTip("Guide marker color")
        form.addRow("Color:", self.btn_gm_color)

        self.cb_gm_symbol = QComboBox()
        _symbols = [
            ("● Circle", "o"), ("■ Square", "s"), ("▲ Triangle up", "^"),
            ("▼ Triangle down", "v"), ("◆ Diamond", "D"), ("★ Star", "*"),
            ("✕ Cross", "x"), ("✚ Plus", "P"),
        ]
        for lbl, sym in _symbols:
            self.cb_gm_symbol.addItem(lbl, sym)
        cur_sym = self._initial_gm_style.marker_symbol
        for i in range(self.cb_gm_symbol.count()):
            if self.cb_gm_symbol.itemData(i) == cur_sym:
                self.cb_gm_symbol.setCurrentIndex(i)
                break
        self.cb_gm_symbol.setToolTip("Marker shape")
        form.addRow("Symbol:", self.cb_gm_symbol)

        self.sb_gm_size = create_marker_size_spin(value=self._initial_gm_style.size)
        self.sb_gm_size.setToolTip("Marker size in points")
        form.addRow("Size:", self.sb_gm_size)

        self._update_gm_controls(self.chk_gm.isChecked())
        self.chk_gm.toggled.connect(self._update_gm_controls)

        gb.setLayout(form)
        self._layout.addWidget(gb)

    def _init_arrow_section(self) -> None:
        gb = QGroupBox("Arrows")
        form = QFormLayout()

        self.chk_arrows = QCheckBox("Show arrows")
        self.chk_arrows.setChecked(self._initial_arrow.enabled)
        self.chk_arrows.setToolTip("Draw directional arrows along the curve")
        form.addRow(self.chk_arrows)

        self.cb_arrow_dir = QComboBox()
        self.cb_arrow_dir.addItem("→ to End", "to_end")
        self.cb_arrow_dir.addItem("← to Start", "to_start")
        idx = self.cb_arrow_dir.findData(self._initial_arrow.direction)
        if idx >= 0:
            self.cb_arrow_dir.setCurrentIndex(idx)
        self.cb_arrow_dir.setToolTip("Direction arrows point along the curve")
        form.addRow("Direction:", self.cb_arrow_dir)

        self.sb_arrow_count = QSpinBox()
        self.sb_arrow_count.setRange(ARROW_COUNT_MIN, ARROW_COUNT_MAX)
        self.sb_arrow_count.setValue(self._initial_arrow.count)
        self.sb_arrow_count.setToolTip("Number of arrows along the curve")
        form.addRow("Count:", self.sb_arrow_count)

        self._update_arrow_controls(self.chk_arrows.isChecked())
        self.chk_arrows.toggled.connect(self._update_arrow_controls)

        gb.setLayout(form)
        self._layout.addWidget(gb)

    def _init_buttons(self) -> None:
        btns = QHBoxLayout()

        btn_ok = QPushButton("OK")
        btn_ok.setDefault(True)
        btn_ok.clicked.connect(self._on_accept)

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)

        btns.addWidget(btn_ok)
        btns.addWidget(btn_cancel)
        self._layout.addLayout(btns)

    # =========================================================================
    # УПРАВЛЕНИЕ ТАБЛИЦЕЙ
    # =========================================================================

    def _append_guide_row(self, comp: Optional[Composition] = None) -> int:
        """Добавляет строку в таблицу; если comp задан — показывает нормализованные значения."""
        row = self.table.rowCount()
        self.table.insertRow(row)

        if comp is not None and comp.is_valid:
            try:
                a, b, c = comp.normalized
            except Exception:
                a, b, c = comp.a, comp.b, comp.c
        else:
            a, b, c = 1 / 3, 1 / 3, 1 / 3

        for col, val in enumerate([a, b, c]):
            spin = QDoubleSpinBox()
            spin.setRange(0.0, 1000.0)
            spin.setDecimals(4)
            spin.setSingleStep(0.01)
            spin.setValue(val)
            spin.setFrame(False)
            self.table.setCellWidget(row, col, spin)

        btn_del = QPushButton("×")
        btn_del.setFixedWidth(24)
        btn_del.setToolTip("Remove this guide point")
        btn_del.clicked.connect(lambda _checked, r=row: self._delete_row(r))
        self.table.setCellWidget(row, 3, btn_del)

        return row

    def _delete_row(self, row: int) -> None:
        """Удаляет строку; пересчитывает привязки кнопок удаления."""
        self.table.removeRow(row)
        for r in range(self.table.rowCount()):
            widget = self.table.cellWidget(r, 3)
            if widget is None:
                continue
            btn = cast(QPushButton, widget)
            try:
                btn.clicked.disconnect()
            except RuntimeError:
                pass
            btn.clicked.connect(lambda _checked, row_r=r: self._delete_row(row_r))

    def _on_add_row(self) -> None:
        self._append_guide_row()

    def _on_pick_from_canvas(self) -> None:
        self._pick_label.setText("Click on diagram to place guide point…")
        self.request_canvas_pick.emit()

    def add_guide_point_from_canvas(self, comp: Composition) -> None:
        """Вызывается главным окном после клика на холсте."""
        try:
            a, b, c = comp.normalized
            self._pick_label.setText(
                f"Added: {self._components[0]}={a:.4f}  "
                f"{self._components[1]}={b:.4f}  "
                f"{self._components[2]}={c:.4f}"
            )
        except Exception:
            self._pick_label.setText("Added guide point")
        self._append_guide_row(comp)

    # =========================================================================
    # ВСПОМОГАТЕЛЬНЫЕ
    # =========================================================================

    def _update_arrow_controls(self, enabled: bool) -> None:
        self.cb_arrow_dir.setEnabled(enabled)
        self.sb_arrow_count.setEnabled(enabled)

    def _update_gm_controls(self, enabled: bool) -> None:
        self.btn_gm_color.setEnabled(enabled)
        self.cb_gm_symbol.setEnabled(enabled)
        self.sb_gm_size.setEnabled(enabled)

    def _collect_guide_points(self) -> List[GuidePoint]:
        """Собирает guide-точки из таблицы, нормализуя значения."""
        guides = []
        for row in range(self.table.rowCount()):
            raw = [self.table.cellWidget(row, col) for col in range(3)]
            if any(w is None for w in raw):
                continue
            spins = [cast(QDoubleSpinBox, w) for w in raw]
            a, b, c = spins[0].value(), spins[1].value(), spins[2].value()
            raw_comp = Composition(a=a, b=b, c=c)
            if not raw_comp.is_valid:
                continue
            # Нормализуем перед сохранением
            na, nb, nc = raw_comp.normalized
            guides.append(GuidePoint(composition=Composition(a=na, b=nb, c=nc)))
        return guides

    def _on_accept(self) -> None:
        uid_start = self.cb_start.currentData()
        uid_end = self.cb_end.currentData()

        if uid_start == uid_end:
            QMessageBox.warning(self, "Invalid Line",
                                "Start and End compositions must be different.")
            return

        self.accept()

    # =========================================================================
    # ПУБЛИЧНЫЙ API
    # =========================================================================

    def get_data(self) -> CurveLineDialogResult:
        return CurveLineDialogResult(
            uid=self._line_uid,
            start_uid=self.cb_start.currentData(),
            end_uid=self.cb_end.currentData(),
            guide_points=self._collect_guide_points(),
            color=self.btn_color.color(),
            line_style=self.cb_style.currentData(),
            width=self.sb_width.value(),
            poly_degree=self.cb_degree.currentData(),
            show_guide_markers=self.chk_gm.isChecked(),
            guide_marker_color=self.btn_gm_color.color(),
            guide_marker_symbol=self.cb_gm_symbol.currentData(),
            guide_marker_size=self.sb_gm_size.value(),
            arrow=ArrowSettings(
                enabled=self.chk_arrows.isChecked(),
                direction=self.cb_arrow_dir.currentData(),
                count=self.sb_arrow_count.value(),
            ),
        )
