"""Виджет для задания области отображения диаграммы."""

from typing import List

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QHeaderView,
    QCheckBox, QDoubleSpinBox,
)
from PySide6.QtCore import Signal

from delta.models import Composition, ProjectData
from ui.widgets.helpers import CopyableTableWidget, create_coord_spin


class DisplayRegionWidget(QWidget):
    """
    Виджет задания многоугольника ограничения области отображения.

    Пользователь добавляет анонимные точки (минимум 3), образующие замкнутый
    контур. Всё, что за пределами контура, скрывается белой маской.
    Масштаб диаграммы адаптируется к bounding box контура.

    Signals:
        region_changed(List[Composition]): raw-координаты точек полигона
        enabled_changed(bool): включение/отключение маски
    """

    region_changed = Signal(list)
    enabled_changed = Signal(bool)

    _COL_A = 0
    _COL_B = 1
    _COL_C = 2

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QVBoxLayout(self)

        info = QLabel(
            "Define a closed polygon to restrict the diagram display area.\n"
            "Minimum 3 points required. Specify raw (unnormalized) coordinates."
        )
        info.setWordWrap(True)
        layout.addWidget(info)

        self._chk_enabled = QCheckBox("Enable display region mask")
        self._chk_enabled.setToolTip(
            "When checked, everything outside the polygon is hidden\n"
            "and the diagram scale adapts to the polygon bounding box."
        )
        self._chk_enabled.toggled.connect(self._on_enabled_toggled)
        layout.addWidget(self._chk_enabled)

        self._table = CopyableTableWidget()
        self._table.setColumnCount(3)
        self._table.setHorizontalHeaderLabels(["A", "B", "C"])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self._table)

        btns = QHBoxLayout()
        self._btn_add = QPushButton("➕ Add Point")
        self._btn_add.clicked.connect(self._on_add)
        self._btn_remove = QPushButton("🗑️ Remove Selected")
        self._btn_remove.clicked.connect(self._on_remove)
        btns.addWidget(self._btn_add)
        btns.addWidget(self._btn_remove)
        layout.addLayout(btns)

        self._status = QLabel("")
        self._status.setWordWrap(True)
        layout.addWidget(self._status)

        layout.addStretch()

        self._block_emit = False

    # =========================================================================
    # PUBLIC API
    # =========================================================================

    def update_view(self, project_data: ProjectData) -> None:
        """Загружает состояние из project_data."""
        names = project_data.components
        self._table.setHorizontalHeaderLabels(list(names))

        self._chk_enabled.blockSignals(True)
        self._chk_enabled.setChecked(project_data.display_region_enabled)
        self._chk_enabled.blockSignals(False)

        self._block_emit = True
        self._table.setRowCount(0)
        for comp in project_data.display_region:
            self._append_row(comp.a, comp.b, comp.c)
        self._block_emit = False

        self._update_status()

    # =========================================================================
    # PRIVATE
    # =========================================================================

    def _append_row(self, a: float = 33.0, b: float = 33.0, c: float = 34.0) -> None:
        row = self._table.rowCount()
        self._table.insertRow(row)
        for col, val in enumerate([a, b, c]):
            spin = create_coord_spin(val)
            spin.valueChanged.connect(self._on_spin_changed)
            self._table.setCellWidget(row, col, spin)

    def _collect_region(self) -> List[Composition]:
        pts: List[Composition] = []
        for row in range(self._table.rowCount()):
            a_w = self._table.cellWidget(row, self._COL_A)
            b_w = self._table.cellWidget(row, self._COL_B)
            c_w = self._table.cellWidget(row, self._COL_C)
            if (isinstance(a_w, QDoubleSpinBox) and isinstance(b_w, QDoubleSpinBox)
                    and isinstance(c_w, QDoubleSpinBox)):
                pts.append(Composition(
                    a=a_w.value(), b=b_w.value(), c=c_w.value()
                ))
        return pts

    def _update_status(self) -> None:
        n = self._table.rowCount()
        enabled = self._chk_enabled.isChecked()
        if not enabled:
            self._status.setText("Mask disabled.")
        elif n == 0:
            self._status.setText("⚠ No points defined.")
        elif n < 3:
            self._status.setText(f"⚠ Need at least 3 points (current: {n}).")
        else:
            self._status.setText(f"✔ Region active ({n} points).")

    def _on_enabled_toggled(self, enabled: bool) -> None:
        self._update_status()
        self.enabled_changed.emit(enabled)

    def _on_add(self) -> None:
        self._append_row(33.0, 33.0, 34.0)
        self._update_status()
        self._emit()

    def _on_remove(self) -> None:
        rows = sorted(
            {idx.row() for idx in self._table.selectedIndexes()},
            reverse=True,
        )
        if not rows:
            row = self._table.rowCount() - 1
            if row >= 0:
                rows = [row]
        for row in rows:
            self._table.removeRow(row)
        self._update_status()
        self._emit()

    def _on_spin_changed(self) -> None:
        if not self._block_emit:
            self._emit()

    def _emit(self) -> None:
        self.region_changed.emit(self._collect_region())
