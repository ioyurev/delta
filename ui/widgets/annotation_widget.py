"""Виджет для управления текстовыми аннотациями на диаграмме."""

from typing import Optional

from PySide6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QLabel, QPushButton,
    QListWidget, QListWidgetItem, QLineEdit, QCheckBox,
    QComboBox, QFrame, QScrollArea, QFormLayout,
    QGroupBox,
)
from PySide6.QtCore import Signal, Qt

from delta.models import ProjectData, TextAnnotation, Composition
from ui.widgets.helpers import (
    ColorPickerButton, create_double_spin, PickableCoordWidget,
)


class AnnotationWidget(QWidget):
    """
    Вкладка управления текстовыми аннотациями.

    Signals:
        request_add()                 — добавить новую аннотацию
        request_remove(uid)           — удалить аннотацию
        annotation_changed(uid, dict) — изменить поле(я) аннотации
        canvas_pick_requested(field)  — запрос выбора точки на холсте
                                        field: 'position' | 'arrow_target'
    """

    request_add = Signal()
    request_remove = Signal(str)
    annotation_changed = Signal(str, object)   # (uid, dict of fields)
    canvas_pick_requested = Signal(str)         # field name

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
        self._btn_add = QPushButton("➕ Add")
        self._btn_add.clicked.connect(self.request_add)
        self._btn_remove = QPushButton("🗑️ Remove")
        self._btn_remove.clicked.connect(self._on_remove_clicked)
        btn_row.addWidget(self._btn_add)
        btn_row.addWidget(self._btn_remove)
        root.addLayout(btn_row)

        # ── Список аннотаций ─────────────────────────────────────
        # Галочка в списке управляет видимостью (visible)
        self._list = QListWidget()
        self._list.setMaximumHeight(120)
        self._list.currentRowChanged.connect(self._on_row_changed)
        self._list.itemChanged.connect(self._on_item_changed)
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

        # ── Text ─────────────────────────────────────────────────
        form.addWidget(QLabel("<b>Text</b>"))
        self._txt_edit = QLineEdit()
        self._txt_edit.setPlaceholderText("Annotation text (\\n for new line)")
        self._txt_edit.editingFinished.connect(
            lambda: self._emit_field('text', self._txt_edit.text())
        )
        form.addWidget(self._txt_edit)

        # ── Position ─────────────────────────────────────────────
        form.addWidget(QLabel("<b>Position (barycentric)</b>"))
        self._pos_coord = PickableCoordWidget()
        self._pos_coord.value_changed.connect(
            lambda c: self._emit_field('position', c)
        )
        self._pos_coord.pick_requested.connect(
            lambda: self._on_pick_requested('position')
        )
        form.addWidget(self._pos_coord)

        # ── Font ─────────────────────────────────────────────────
        font_box = QGroupBox("Font")
        font_form = QFormLayout(font_box)
        font_form.setSpacing(4)

        self._font_size = create_double_spin(4.0, 72.0, 10.0, 1.0, 1)
        self._font_size.valueChanged.connect(
            lambda v: self._emit_field('font_size', v)
        )
        font_form.addRow("Size:", self._font_size)

        self._color = ColorPickerButton("#000000")
        self._color.color_changed.connect(lambda c: self._emit_field('color', c))
        font_form.addRow("Color:", self._color)

        style_row = QHBoxLayout()
        self._chk_bold = QCheckBox("Bold")
        self._chk_bold.toggled.connect(lambda v: self._emit_field('bold', v))
        self._chk_italic = QCheckBox("Italic")
        self._chk_italic.toggled.connect(lambda v: self._emit_field('italic', v))
        style_row.addWidget(self._chk_bold)
        style_row.addWidget(self._chk_italic)
        font_form.addRow("Style:", style_row)

        ha_row = QHBoxLayout()
        self._ha = QComboBox()
        self._ha.addItems(["left", "center", "right"])
        self._ha.currentTextChanged.connect(lambda v: self._emit_field('ha', v))
        self._va = QComboBox()
        self._va.addItems(["top", "center", "bottom", "baseline"])
        self._va.currentTextChanged.connect(lambda v: self._emit_field('va', v))
        ha_row.addWidget(self._ha)
        ha_row.addWidget(self._va)
        font_form.addRow("Align:", ha_row)

        form.addWidget(font_box)

        # ── Box ──────────────────────────────────────────────────
        box_box = QGroupBox("Background Box")
        box_form = QFormLayout(box_box)
        box_form.setSpacing(4)

        self._chk_box = QCheckBox("Enable")
        self._chk_box.toggled.connect(lambda v: self._emit_field('box_enabled', v))
        box_form.addRow("", self._chk_box)

        self._box_fill = ColorPickerButton("#ffffff")
        self._box_fill.color_changed.connect(lambda c: self._emit_field('box_facecolor', c))
        box_form.addRow("Fill:", self._box_fill)

        self._box_edge = ColorPickerButton("#000000")
        self._box_edge.color_changed.connect(lambda c: self._emit_field('box_edgecolor', c))
        box_form.addRow("Edge:", self._box_edge)

        self._box_alpha = create_double_spin(0.0, 1.0, 0.8, 0.05, 2)
        self._box_alpha.valueChanged.connect(lambda v: self._emit_field('box_alpha', v))
        box_form.addRow("Alpha:", self._box_alpha)

        self._box_pad = create_double_spin(0.0, 5.0, 0.3, 0.1, 2)
        self._box_pad.valueChanged.connect(lambda v: self._emit_field('box_pad', v))
        box_form.addRow("Padding:", self._box_pad)

        form.addWidget(box_box)

        # ── Arrow ─────────────────────────────────────────────────
        arrow_box = QGroupBox("Arrow / Pointer")
        arrow_form = QFormLayout(arrow_box)
        arrow_form.setSpacing(4)

        self._chk_arrow = QCheckBox("Enable")
        self._chk_arrow.toggled.connect(lambda v: self._emit_field('arrow_enabled', v))
        arrow_form.addRow("", self._chk_arrow)

        self._arr_coord = PickableCoordWidget()
        self._arr_coord.value_changed.connect(
            lambda c: self._emit_field('arrow_target', c)
        )
        self._arr_coord.pick_requested.connect(
            lambda: self._on_pick_requested('arrow_target')
        )
        arrow_form.addRow("Target:", self._arr_coord)

        self._arrow_color = ColorPickerButton("#000000")
        self._arrow_color.color_changed.connect(lambda c: self._emit_field('arrow_color', c))
        arrow_form.addRow("Color:", self._arrow_color)

        form.addWidget(arrow_box)
        form.addStretch()

        self._detail_widget = inner
        self._detail_widget.setEnabled(False)

    # =========================================================================
    # PUBLIC API
    # =========================================================================

    def update_view(self, project_data: ProjectData) -> None:
        """Обновляет список и детальную панель из project_data."""
        self._project_data = project_data
        prev_uid = self._current_uid

        self._block_emit = True
        self._list.blockSignals(True)
        self._list.clear()
        for ann in project_data.annotations:
            item = QListWidgetItem(ann.text or "<empty>")
            item.setData(Qt.ItemDataRole.UserRole, ann.uid)
            item.setCheckState(
                Qt.CheckState.Checked if ann.visible else Qt.CheckState.Unchecked
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

        # Обновляем детальную панель
        selected: Optional[TextAnnotation] = self._find_ann(project_data, self._current_uid)
        if selected is not None:
            self._populate_detail(selected, project_data.components)
        else:
            self._detail_widget.setEnabled(False)

    def receive_pick(self, field: str, comp: Composition) -> None:
        """Получает результат выбора точки на холсте."""
        self._block_emit = True
        if field == 'position':
            self._pos_coord.set_value(comp)
        elif field == 'arrow_target':
            self._arr_coord.set_value(comp)
        self._block_emit = False
        self._emit_field(field, comp)

    # =========================================================================
    # PRIVATE
    # =========================================================================

    def _find_ann(
        self, project_data: ProjectData, uid: Optional[str]
    ) -> Optional[TextAnnotation]:
        if uid is None:
            return None
        return next((a for a in project_data.annotations if a.uid == uid), None)

    def _populate_detail(self, ann: TextAnnotation, components: list) -> None:
        self._block_emit = True
        self._detail_widget.setEnabled(True)

        self._txt_edit.setText(ann.text)
        self._pos_coord.set_value(ann.position)

        self._font_size.setValue(ann.font_size)
        self._color.set_color(ann.color)
        self._chk_bold.setChecked(ann.bold)
        self._chk_italic.setChecked(ann.italic)
        self._ha.setCurrentText(ann.ha)
        self._va.setCurrentText(ann.va)

        self._chk_box.setChecked(ann.box_enabled)
        self._box_fill.set_color(ann.box_facecolor)
        self._box_edge.set_color(ann.box_edgecolor)
        self._box_alpha.setValue(ann.box_alpha)
        self._box_pad.setValue(ann.box_pad)

        self._chk_arrow.setChecked(ann.arrow_enabled)
        target = ann.arrow_target if ann.arrow_target is not None else Composition(a=33.0, b=33.0, c=34.0)
        self._arr_coord.set_value(target)
        self._arrow_color.set_color(ann.arrow_color)

        self._block_emit = False

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
        if self._project_data is not None:
            ann = self._find_ann(self._project_data, uid)
            if ann is not None:
                self._populate_detail(ann, self._project_data.components)
                return
        self._detail_widget.setEnabled(uid is not None)

    def _on_item_changed(self, item: QListWidgetItem) -> None:
        """Галочка в списке → переключить видимость аннотации."""
        if self._block_emit:
            return
        uid = item.data(Qt.ItemDataRole.UserRole)
        if uid:
            visible = item.checkState() == Qt.CheckState.Checked
            self.annotation_changed.emit(uid, {'visible': visible})

    def _on_remove_clicked(self) -> None:
        uid = self._current_uid
        if uid:
            self.request_remove.emit(uid)

    def _on_pick_requested(self, field: str) -> None:
        self.canvas_pick_requested.emit(field)

    def _emit_field(self, field: str, value: object) -> None:
        if self._block_emit or self._current_uid is None:
            return
        self.annotation_changed.emit(self._current_uid, {field: value})
