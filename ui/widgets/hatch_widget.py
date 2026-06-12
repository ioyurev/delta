"""Виджет управления hatch-регионами на диаграмме."""

from __future__ import annotations

from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QLineEdit, QCheckBox,
    QComboBox, QFrame, QScrollArea, QFormLayout,
    QGroupBox,
)
from PySide6.QtCore import Signal, Qt

from delta.models import (
    ProjectData, HatchRegion, Composition, NamedComposition,
    StraightSegment, LineRefSegment, CurveRefSegment,
)
from ui.widgets.helpers import (
    ColorPickerButton, create_double_spin,
    mathtext_to_plain,
)


class HatchWidget(QWidget):
    """
    Вкладка управления hatch-регионами.

    Signals:
        request_add()
        request_remove(uid)
        region_changed(uid, dict)
        segments_changed(uid, list[BoundarySegment])
    """

    request_add = Signal()
    request_remove = Signal(str)
    region_changed = Signal(str, object)       # (uid, dict of fields)
    segments_changed = Signal(str, object)     # (uid, list[BoundarySegment])

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._block_emit = False
        self._current_uid: Optional[str] = None
        self._project_data: Optional[ProjectData] = None

        root = QVBoxLayout(self)
        root.setContentsMargins(4, 4, 4, 4)
        root.setSpacing(4)

        # ── Кнопки ───────────────────────────────────────────────
        btn_row = QHBoxLayout()
        self._btn_add = QPushButton("➕ Add Region")
        self._btn_add.clicked.connect(self.request_add)
        self._btn_remove = QPushButton("🗑️ Remove")
        self._btn_remove.clicked.connect(self._on_remove_clicked)
        btn_row.addWidget(self._btn_add)
        btn_row.addWidget(self._btn_remove)
        root.addLayout(btn_row)

        # ── Список регионов ──────────────────────────────────────
        self._list = QListWidget()
        self._list.setMaximumHeight(120)
        self._list.currentRowChanged.connect(self._on_row_changed)
        self._list.itemChanged.connect(self._on_item_visibility_changed)
        root.addWidget(self._list)

        # ── Панель редактирования ────────────────────────────────
        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        root.addWidget(sep)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        root.addWidget(scroll, stretch=1)

        inner = QWidget()
        scroll.setWidget(inner)
        form = QVBoxLayout(inner)
        form.setContentsMargins(0, 0, 4, 0)
        form.setSpacing(6)

        # ── Name ─────────────────────────────────────────────────
        form.addWidget(QLabel("<b>Name</b>"))
        self._txt_name = QLineEdit()
        self._txt_name.editingFinished.connect(
            lambda: self._emit_field("name", self._txt_name.text())
        )
        form.addWidget(self._txt_name)

        # ── Style ────────────────────────────────────────────────
        style_box = QGroupBox("Style")
        style_form = QFormLayout(style_box)
        style_form.setSpacing(4)

        self._txt_hatch = QLineEdit("//")
        self._txt_hatch.setToolTip(
            "Hatch pattern: / \\ | - + x o O . *\n"
            "Repeat for density: // is denser than /"
        )
        self._txt_hatch.editingFinished.connect(
            lambda: self._emit_field("hatch_pattern", self._txt_hatch.text())
        )
        style_form.addRow("Pattern:", self._txt_hatch)

        self._color_hatch = ColorPickerButton("#000000")
        self._color_hatch.color_changed.connect(
            lambda c: self._emit_field("hatch_color", c)
        )
        style_form.addRow("Hatch color:", self._color_hatch)

        self._color_fill = ColorPickerButton("#000000")
        self._color_fill.color_changed.connect(
            lambda c: self._emit_field("fill_color", c)
        )
        style_form.addRow("Fill color:", self._color_fill)

        self._spin_alpha = create_double_spin(0.0, 1.0, 0.05, 0.05, 2)
        self._spin_alpha.valueChanged.connect(
            lambda v: self._emit_field("fill_alpha", v)
        )
        style_form.addRow("Fill alpha:", self._spin_alpha)

        self._color_edge = ColorPickerButton("#000000")
        self._color_edge.color_changed.connect(
            lambda c: self._emit_field("edge_color", c)
        )
        style_form.addRow("Edge color:", self._color_edge)

        self._spin_edge_w = create_double_spin(0.0, 10.0, 1.0, 0.5, 1)
        self._spin_edge_w.valueChanged.connect(
            lambda v: self._emit_field("edge_width", v)
        )
        style_form.addRow("Edge width:", self._spin_edge_w)

        form.addWidget(style_box)

        # ── Segments ─────────────────────────────────────────────
        seg_box = QGroupBox("Boundary Segments")
        seg_layout = QVBoxLayout(seg_box)

        self._seg_list = QListWidget()
        self._seg_list.setMaximumHeight(100)
        self._seg_list.currentRowChanged.connect(self._on_seg_row_changed)
        seg_layout.addWidget(self._seg_list)

        seg_btns = QHBoxLayout()
        self._btn_add_seg = QPushButton("+ Between Points")
        self._btn_add_seg.setToolTip("Add a straight segment between two existing compositions")
        self._btn_add_seg.clicked.connect(lambda: self._add_segment("straight"))
        self._btn_add_line_seg = QPushButton("+ Along Line")
        self._btn_add_line_seg.setToolTip("Add boundary along an existing straight line")
        self._btn_add_line_seg.clicked.connect(lambda: self._add_segment("line_ref"))
        self._btn_add_curve_seg = QPushButton("+ Along Curve")
        self._btn_add_curve_seg.setToolTip("Add boundary along an existing curve line")
        self._btn_add_curve_seg.clicked.connect(lambda: self._add_segment("curve_ref"))
        self._btn_del_seg = QPushButton("🗑️")
        self._btn_del_seg.setFixedWidth(30)
        self._btn_del_seg.clicked.connect(self._remove_segment)
        seg_btns.addWidget(self._btn_add_seg)
        seg_btns.addWidget(self._btn_add_line_seg)
        seg_btns.addWidget(self._btn_add_curve_seg)
        seg_btns.addWidget(self._btn_del_seg)
        seg_layout.addLayout(seg_btns)

        # Straight detail: два ComboBox для выбора compositions
        self._straight_widget = QWidget()
        sw_layout = QFormLayout(self._straight_widget)
        sw_layout.setContentsMargins(0, 0, 0, 0)
        self._cb_seg_start = QComboBox()
        self._cb_seg_start.setToolTip("Start composition for this segment")
        self._cb_seg_start.currentIndexChanged.connect(self._on_seg_detail_changed)
        self._cb_seg_end = QComboBox()
        self._cb_seg_end.setToolTip("End composition for this segment")
        self._cb_seg_end.currentIndexChanged.connect(self._on_seg_detail_changed)
        sw_layout.addRow("From:", self._cb_seg_start)
        sw_layout.addRow("To:", self._cb_seg_end)

        # Ref detail: ComboBox для line/curve + reverse
        self._ref_widget = QWidget()
        rw_layout = QFormLayout(self._ref_widget)
        rw_layout.setContentsMargins(0, 0, 0, 0)
        self._cb_ref = QComboBox()
        self._cb_ref.currentIndexChanged.connect(self._on_seg_detail_changed)
        self._chk_reverse = QCheckBox("Reverse direction")
        self._chk_reverse.toggled.connect(self._on_seg_detail_changed)
        rw_layout.addRow("Reference:", self._cb_ref)
        rw_layout.addRow("", self._chk_reverse)

        seg_layout.addWidget(self._straight_widget)
        seg_layout.addWidget(self._ref_widget)
        self._straight_widget.hide()
        self._ref_widget.hide()

        form.addWidget(seg_box)
        form.addStretch()

        self._detail_widget = inner
        self._detail_widget.setEnabled(False)
        self._current_seg_idx = -1
        self._current_seg_kind = ""

    # =========================================================================
    # PUBLIC API
    # =========================================================================

    def update_view(self, project_data: ProjectData) -> None:
        self._project_data = project_data
        prev_uid = self._current_uid

        self._block_emit = True
        self._list.blockSignals(True)
        self._list.clear()
        for region in project_data.hatch_regions:
            item = QListWidgetItem(region.name or "<unnamed>")
            item.setData(Qt.ItemDataRole.UserRole, region.uid)
            item.setCheckState(
                Qt.CheckState.Checked if region.visible else Qt.CheckState.Unchecked
            )
            self._list.addItem(item)
        self._list.blockSignals(False)
        self._block_emit = False

        # Восстанавливаем выбор
        restored = False
        if prev_uid:
            for i in range(self._list.count()):
                if self._list.item(i).data(Qt.ItemDataRole.UserRole) == prev_uid:
                    self._list.setCurrentRow(i)
                    restored = True
                    break
        if not restored:
            self._current_uid = None
            self._detail_widget.setEnabled(False)

        if self._current_uid:
            region_found: HatchRegion | None = self._find_region(self._current_uid)
            if region_found:
                self._populate_detail(region_found)

    # =========================================================================
    # PRIVATE
    # =========================================================================

    def _find_region(self, uid: Optional[str]) -> Optional[HatchRegion]:
        if uid is None or self._project_data is None:
            return None
        return next((r for r in self._project_data.hatch_regions if r.uid == uid), None)

    def _populate_detail(self, region: HatchRegion) -> None:
        self._block_emit = True
        self._detail_widget.setEnabled(True)

        self._txt_name.setText(region.name)
        self._txt_hatch.setText(region.hatch_pattern)
        self._color_hatch.set_color(region.hatch_color)
        self._color_fill.set_color(region.fill_color)
        self._spin_alpha.setValue(region.fill_alpha)
        self._color_edge.set_color(region.edge_color)
        self._spin_edge_w.setValue(region.edge_width)

        self._rebuild_seg_list(region)
        self._block_emit = False

    def _rebuild_seg_list(self, region: HatchRegion) -> None:
        self._seg_list.blockSignals(True)
        self._seg_list.clear()
        for i, seg in enumerate(region.segments):
            if isinstance(seg, StraightSegment):
                start_name = self._find_comp_name_by_coords(seg.start)
                end_name = self._find_comp_name_by_coords(seg.end)
                label = f"[{i}] {start_name} → {end_name}"
            elif isinstance(seg, LineRefSegment):
                name = self._get_line_display_name(seg.line_uid)
                rev = " ◀" if seg.reverse else ""
                label = f"[{i}] Line: {name}{rev}"
            elif isinstance(seg, CurveRefSegment):
                name = self._get_curve_display_name(seg.curve_uid)
                rev = " ◀" if seg.reverse else ""
                label = f"[{i}] Curve: {name}{rev}"
            else:
                label = f"[{i}] ???"
            self._seg_list.addItem(label)
        self._seg_list.blockSignals(False)
        self._current_seg_idx = -1
        self._straight_widget.hide()
        self._ref_widget.hide()

    def _get_line_display_name(self, uid: str) -> str:
        if self._project_data is None:
            return uid[:8]
        comp_map = {c.uid: c.name for c in self._project_data.compositions}
        for ln in self._project_data.lines:
            if ln.uid == uid:
                n1 = mathtext_to_plain(comp_map.get(ln.start_uid, "?"))
                n2 = mathtext_to_plain(comp_map.get(ln.end_uid, "?"))
                return f"{n1}—{n2}"
        return uid[:8]

    def _get_curve_display_name(self, uid: str) -> str:
        if self._project_data is None:
            return uid[:8]
        comp_map = {c.uid: c.name for c in self._project_data.compositions}
        for cl in self._project_data.curve_lines:
            if cl.uid == uid:
                n1 = mathtext_to_plain(comp_map.get(cl.start_uid, "?"))
                n2 = mathtext_to_plain(comp_map.get(cl.end_uid, "?"))
                return f"{n1}—{n2}"
        return uid[:8]

    def _on_row_changed(self, row: int) -> None:
        if row < 0:
            self._current_uid = None
            self._detail_widget.setEnabled(False)
            return
        item = self._list.item(row)
        if item is None:
            return
        uid = item.data(Qt.ItemDataRole.UserRole)
        self._current_uid = uid
        region = self._find_region(uid)
        if region:
            self._populate_detail(region)

    def _on_item_visibility_changed(self, item: QListWidgetItem) -> None:
        if self._block_emit:
            return
        uid = item.data(Qt.ItemDataRole.UserRole)
        if uid:
            visible = item.checkState() == Qt.CheckState.Checked
            self.region_changed.emit(uid, {"visible": visible})

    def _on_remove_clicked(self) -> None:
        if self._current_uid:
            self.request_remove.emit(self._current_uid)

    def _emit_field(self, field: str, value: object) -> None:
        if self._block_emit or self._current_uid is None:
            return
        self.region_changed.emit(self._current_uid, {field: value})

    # ── Segment editing ──────────────────────────────────────────

    def _add_segment(self, kind: str) -> None:
        if self._current_uid is None or self._project_data is None:
            return
        region = self._find_region(self._current_uid)
        if region is None:
            return

        comps = self._project_data.compositions
        new_segs = list(region.segments)

        if kind == "straight":
            if len(comps) < 2:
                return
            # Берём координаты первых двух compositions
            new_segs.append(StraightSegment(
                start=comps[0].composition,
                end=comps[1].composition,
            ))
        elif kind == "line_ref":
            lines = self._project_data.lines
            if not lines:
                return
            new_segs.append(LineRefSegment(line_uid=lines[0].uid))
        elif kind == "curve_ref":
            curves = self._project_data.curve_lines
            if not curves:
                return
            new_segs.append(CurveRefSegment(curve_uid=curves[0].uid))

        self.segments_changed.emit(self._current_uid, new_segs)

    def _remove_segment(self) -> None:
        if self._current_uid is None:
            return
        region = self._find_region(self._current_uid)
        if region is None:
            return
        idx = self._seg_list.currentRow()
        if idx < 0 or idx >= len(region.segments):
            return
        new_segs = list(region.segments)
        new_segs.pop(idx)
        self.segments_changed.emit(self._current_uid, new_segs)

    def _on_seg_row_changed(self, row: int) -> None:
        self._current_seg_idx = row
        if self._current_uid is None:
            return
        region = self._find_region(self._current_uid)
        if region is None or row < 0 or row >= len(region.segments):
            self._straight_widget.hide()
            self._ref_widget.hide()
            return

        seg = region.segments[row]
        self._block_emit = True

        if isinstance(seg, StraightSegment):
            self._current_seg_kind = "straight"
            self._straight_widget.show()
            self._ref_widget.hide()
            self._populate_comp_combos()
            # Найти compositions, ближайшие к координатам сегмента
            self._select_closest_comp(self._cb_seg_start, seg.start)
            self._select_closest_comp(self._cb_seg_end, seg.end)

        elif isinstance(seg, LineRefSegment):
            self._current_seg_kind = "line_ref"
            self._straight_widget.hide()
            self._ref_widget.show()
            self._populate_ref_combo("line")
            idx = self._cb_ref.findData(seg.line_uid)
            if idx >= 0:
                self._cb_ref.setCurrentIndex(idx)
            self._chk_reverse.setChecked(seg.reverse)

        elif isinstance(seg, CurveRefSegment):
            self._current_seg_kind = "curve_ref"
            self._straight_widget.hide()
            self._ref_widget.show()
            self._populate_ref_combo("curve")
            idx = self._cb_ref.findData(seg.curve_uid)
            if idx >= 0:
                self._cb_ref.setCurrentIndex(idx)
            self._chk_reverse.setChecked(seg.reverse)

        self._block_emit = False

    def _populate_ref_combo(self, kind: str) -> None:
        self._cb_ref.blockSignals(True)
        self._cb_ref.clear()
        if self._project_data is None:
            self._cb_ref.blockSignals(False)
            return

        if kind == "line":
            for ln in self._project_data.lines:
                self._cb_ref.addItem(self._get_line_display_name(ln.uid), ln.uid)
        else:
            for cl in self._project_data.curve_lines:
                self._cb_ref.addItem(self._get_curve_display_name(cl.uid), cl.uid)
        self._cb_ref.blockSignals(False)

    def _on_seg_detail_changed(self) -> None:
        if self._block_emit or self._current_uid is None:
            return
        region = self._find_region(self._current_uid)
        if region is None:
            return
        idx = self._current_seg_idx
        if idx < 0 or idx >= len(region.segments):
            return

        new_segs = list(region.segments)

        if self._current_seg_kind == "straight":
            start_uid = self._cb_seg_start.currentData()
            end_uid = self._cb_seg_end.currentData()
            start_comp = self._find_comp_by_uid(start_uid)
            end_comp = self._find_comp_by_uid(end_uid)
            if start_comp is None or end_comp is None:
                return
            new_segs[idx] = StraightSegment(
                start=start_comp.composition,
                end=end_comp.composition,
            )
        elif self._current_seg_kind == "line_ref":
            uid = self._cb_ref.currentData()
            if uid:
                new_segs[idx] = LineRefSegment(
                    line_uid=uid,
                    reverse=self._chk_reverse.isChecked(),
                )
        elif self._current_seg_kind == "curve_ref":
            uid = self._cb_ref.currentData()
            if uid:
                new_segs[idx] = CurveRefSegment(
                    curve_uid=uid,
                    reverse=self._chk_reverse.isChecked(),
                )

        self.segments_changed.emit(self._current_uid, new_segs)

    def _populate_comp_combos(self) -> None:
        """Заполняет ComboBox'ы для straight-сегмента списком compositions."""
        for cb in (self._cb_seg_start, self._cb_seg_end):
            cb.blockSignals(True)
            cb.clear()
            if self._project_data:
                for comp in sorted(self._project_data.compositions, key=lambda c: c.name):
                    name = mathtext_to_plain(comp.name) if comp.name else "[Unnamed]"
                    cb.addItem(name, comp.uid)
            cb.blockSignals(False)

    def _select_closest_comp(self, cb: QComboBox, target: Composition) -> None:
        """Выбирает в ComboBox composition, ближайшую к target по координатам."""
        if self._project_data is None:
            return

        best_idx = 0
        best_dist = float("inf")
        for i in range(cb.count()):
            uid = cb.itemData(i)
            comp = self._find_comp_by_uid(uid)
            if comp is None:
                continue
            try:
                t1 = target.normalized
                t2 = comp.composition.normalized
                dist = sum((a - b) ** 2 for a, b in zip(t1, t2))
                if dist < best_dist:
                    best_dist = dist
                    best_idx = i
            except Exception:
                continue

        cb.setCurrentIndex(best_idx)

    def _find_comp_by_uid(self, uid: Optional[str]) -> Optional[NamedComposition]:
        """Ищет NamedComposition по uid в текущих данных проекта."""
        if uid is None or self._project_data is None:
            return None
        return next(
            (c for c in self._project_data.compositions if c.uid == uid),
            None,
        )

    def _find_comp_name_by_coords(self, target: Composition) -> str:
        """Находит имя composition, ближайшей к координатам target."""
        if self._project_data is None:
            return "?"
        best_name = "?"
        best_dist = float("inf")
        for comp in self._project_data.compositions:
            try:
                t1 = target.normalized
                t2 = comp.composition.normalized
                dist = sum((a - b) ** 2 for a, b in zip(t1, t2))
                if dist < best_dist:
                    best_dist = dist
                    best_name = mathtext_to_plain(comp.name) if comp.name else "?"
            except Exception:
                continue
        return best_name
