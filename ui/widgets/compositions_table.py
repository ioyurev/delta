from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, 
                               QLabel, QLineEdit, QPushButton, QCheckBox, 
                               QDoubleSpinBox, QTableWidgetItem, QHeaderView, 
                               QMenu, QTableWidget, QApplication)
from PySide6.QtCore import Signal, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QBrush, QKeyEvent
from core.models import ProjectData, CompositionUpdate, Composition
from core.constants import (
    COMP_NAME_MAX_LENGTH, 
    DISPLAY_DECIMALS_TABLE, 
    COORD_INPUT_MIN, 
    COORD_INPUT_MAX, 
    TOOLTIP_COORDINATE,
    NORMALIZATION_WARNING_THRESHOLD
)
import math

_COLUMN_TO_FIELD = {1: 'a', 2: 'b', 3: 'c'}

def _get_error_color() -> QColor:
    """Возвращает цвет ошибки, адаптированный к теме"""
    palette = QApplication.palette()
    base = palette.base().color()
    if base.lightness() < 128:
        return QColor(100, 40, 40)
    return QColor(255, 200, 200)

def _get_normal_color() -> QColor:
    """Возвращает нормальный цвет фона из текущей палитры"""
    return QApplication.palette().base().color()


class CompositionsTable(QWidget):
    composition_edited = Signal(str, CompositionUpdate) 
    request_add_composition = Signal()
    request_edit_style = Signal(str) 
    request_delete_composition = Signal(str)
    components_changed = Signal(list)
    grid_changed = Signal(bool, float)
    view_mode_changed = Signal(bool)
    validation_error = Signal(str)

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        
        # --- 1. System Settings ---
        gb_sys = QGroupBox("System Settings")
        sys_lay = QVBoxLayout()
        
        # Components
        h_comp = QHBoxLayout()
        self.ed_a = QLineEdit("A")
        self.ed_a.setFixedWidth(40)
        self.ed_b = QLineEdit("B")
        self.ed_b.setFixedWidth(40)
        self.ed_c = QLineEdit("C")
        self.ed_c.setFixedWidth(40)
        
        # ВМЕСТО КНОПКИ: Подключаем сигнал завершения редактирования
        # Изменения применятся при нажатии Enter или потере фокуса
        self.ed_a.editingFinished.connect(self._on_comps_update)
        self.ed_b.editingFinished.connect(self._on_comps_update)
        self.ed_c.editingFinished.connect(self._on_comps_update)
        
        self.ed_a.setToolTip("Name of component A. Press Enter to apply.")
        self.ed_b.setToolTip("Name of component B. Press Enter to apply.")
        self.ed_c.setToolTip("Name of component C. Press Enter to apply.")
        
        h_comp.addWidget(QLabel("Labels:"))
        h_comp.addWidget(self.ed_a)
        h_comp.addWidget(self.ed_b)
        h_comp.addWidget(self.ed_c)
        sys_lay.addLayout(h_comp)
        
        # View & Grid
        h_sets = QHBoxLayout()
        self.chk_inv = QCheckBox("Inverted")
        self.chk_inv.toggled.connect(lambda v: self.view_mode_changed.emit(v))
        
        self.chk_grid = QCheckBox("Grid")
        self.chk_grid.toggled.connect(self._on_grid_update)
        
        self.sp_step = QDoubleSpinBox()
        self.sp_step.setRange(0.01, 0.5)
        self.sp_step.setSingleStep(0.05)
        self.sp_step.setPrefix("Step: ")
        self.sp_step.valueChanged.connect(self._on_grid_update)
        
        self.chk_inv.setToolTip("Flip triangle upside down (vertex C at bottom)")
        self.chk_grid.setToolTip("Show/hide grid lines on the diagram")
        self.sp_step.setToolTip("Grid spacing (0.1 = 10% intervals)")
        
        h_sets.addWidget(self.chk_inv)
        h_sets.addWidget(self.chk_grid)
        h_sets.addWidget(self.sp_step)
        sys_lay.addLayout(h_sets)
        
        gb_sys.setLayout(sys_lay)
        layout.addWidget(gb_sys)

        # --- 2. Table ---
        self.table = QTableWidget()
        self.table.setColumnCount(4)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self.table.itemChanged.connect(self._on_item_changed)
        
        # Tooltip для всей таблицы
        self.table.setToolTip(
            "Composition coordinates in molar fractions.\n"
            "Values are normalized: A + B + C = 1\n"
            "Double-click to edit. Right-click for options."
        )
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        self.table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
        btn_add = QPushButton("➕ Add New Composition")
        btn_add.setStyleSheet("""
            QPushButton {
                padding: 8px 16px;
                font-weight: bold;
            }
        """)
        btn_add.clicked.connect(self.request_add_composition.emit)
        btn_add.setToolTip("Create a new composition point (Ctrl+click on diagram also works)")
        
        layout.addWidget(self.table)
        
        # --- 3. Action Buttons (NEW) ---
        # Создаем панель кнопок, аналогичную LinesManager
        btns_layout = QHBoxLayout()
        
        self.btn_add = QPushButton("➕ Add")
        self.btn_add.clicked.connect(self.request_add_composition.emit)
        self.btn_add.setToolTip("Create a new composition point")
        
        self.btn_edit = QPushButton("✏️ Edit") # Аналог Edit в линиях
        self.btn_edit.clicked.connect(self._on_style_click)
        self.btn_edit.setToolTip("Edit marker style (color, shape, size)")
        
        self.btn_del = QPushButton("🗑️ Delete")
        self.btn_del.clicked.connect(self._on_del_click)
        self.btn_del.setToolTip("Delete selected composition")
        
        btns_layout.addWidget(self.btn_add)
        btns_layout.addWidget(self.btn_edit)
        btns_layout.addWidget(self.btn_del)
        
        layout.addLayout(btns_layout)
        
        self._block_signals = False
        self._row_to_uid: dict[int, str] = {}
        self._previous_values: dict[tuple[int, int], str] = {}

    def _is_row_valid(self, row: int) -> bool:
        """Проверяет, валидны ли координаты в строке"""
        try:
            item_a = self.table.item(row, 1)
            item_b = self.table.item(row, 2)
            item_c = self.table.item(row, 3)
            
            if not item_a or not item_b or not item_c:
                return False
                
            a = float(item_a.text().replace(',', '.'))
            b = float(item_b.text().replace(',', '.'))
            c = float(item_c.text().replace(',', '.'))
            
            comp = Composition(a=a, b=b, c=c)
            return comp.is_physically_valid
        except (ValueError, AttributeError):
            return False

    def _get_normalization_status(self, composition) -> tuple[bool, str]:
        """
        Проверяет, требуется ли нормализация для состава.
        
        Returns:
            (needs_warning, tooltip_text)
        """
        total = composition.total
        
        if abs(total) < 1e-9:
            return True, "⚠ Sum ≈ 0 (invalid composition)"
        
        if abs(total - 1.0) > NORMALIZATION_WARNING_THRESHOLD:
            try:
                a, b, c = composition.normalized
                return True, (
                    f"⚠ Input sum = {total:.4f} (not normalized)\n"
                    f"Normalized values: {a:.4f}, {b:.4f}, {c:.4f}\n"
                    f"Calculations use normalized values (sum = 1)"
                )
            except Exception:
                return True, "⚠ Cannot normalize composition"
        
        return False, "Values are normalized (sum ≈ 1)"

    def update_view(self, project_data: ProjectData) -> None:
        self.ed_a.setText(project_data.components[0])
        self.ed_b.setText(project_data.components[1])
        self.ed_c.setText(project_data.components[2])
        
        self.chk_inv.blockSignals(True)
        self.chk_inv.setChecked(project_data.is_inverted)
        self.chk_inv.blockSignals(False)
        
        self.chk_grid.blockSignals(True)
        self.sp_step.blockSignals(True)
        self.chk_grid.setChecked(project_data.grid.visible)
        self.sp_step.setValue(project_data.grid.step)
        self.chk_grid.blockSignals(False)
        self.sp_step.blockSignals(False)

        self._block_signals = True
        
        current_rows = self.table.rowCount()
        target_rows = len(project_data.compositions)
        
        if current_rows < target_rows:
            for _ in range(target_rows - current_rows):
                self.table.insertRow(self.table.rowCount())
        elif current_rows > target_rows:
            for _ in range(current_rows - target_rows):
                self.table.removeRow(self.table.rowCount() - 1)
        
        # Устанавливаем заголовки
        headers = ["Name"] + list(project_data.components)
        self.table.setHorizontalHeaderLabels(headers)
        
        # Добавляем tooltips к заголовкам
        name_header = self.table.horizontalHeaderItem(0)
        if name_header:
            name_header.setToolTip("Composition name (identifier)")
        
        for col in range(1, 4):
            header_item = self.table.horizontalHeaderItem(col)
            if header_item:
                header_item.setToolTip(TOOLTIP_COORDINATE)
        
        self._row_to_uid = {}
        self._previous_values = {}
        
        for i, p in enumerate(project_data.compositions):
            self._row_to_uid[i] = p.uid
            
            # Проверяем статус нормализации
            needs_warning, norm_tooltip = self._get_normalization_status(p.composition)
            
            # Используем константу для точности отображения
            d = DISPLAY_DECIMALS_TABLE
            vals = [
                p.name,
                f"{p.composition.a:.{d}f}",
                f"{p.composition.b:.{d}f}",
                f"{p.composition.c:.{d}f}"
            ]
            
            for col, val in enumerate(vals):
                item = self.table.item(i, col)
                if not item:
                    item = QTableWidgetItem()
                    self.table.setItem(i, col, item)
                
                if item.text() != val:
                    item.setText(val)
                
                self._previous_values[(i, col)] = val
                
                # Устанавливаем фон и tooltip в зависимости от статуса
                if col > 0:  # Только для координатных ячеек
                    if needs_warning:
                        # Бледно-жёлтый фон для ненормализованных
                        item.setBackground(QBrush(QColor(255, 255, 200)))
                        item.setToolTip(norm_tooltip)
                    else:
                        item.setBackground(QBrush(_get_normal_color()))
                        item.setToolTip(TOOLTIP_COORDINATE)
                else:
                    item.setBackground(QBrush(_get_normal_color()))
        
        # После заполнения — проверяем валидность и подсвечиваем
        for i, p in enumerate(project_data.compositions):
            if not p.composition.is_physically_valid:
                # Подсвечиваем всю строку бледно-красным
                for col in range(4):
                    item = self.table.item(i, col)
                    if item:
                        item.setBackground(QBrush(QColor(255, 230, 230)))
                        item.setToolTip("Warning: Composition has negative molar fractions")
                
        self._block_signals = False

    def select_composition(self, uid: str) -> None:
        for row, row_uid in self._row_to_uid.items():
            if row_uid == uid:
                self.table.selectRow(row)
                self.table.scrollTo(self.table.model().index(row, 0))
                break

    def _on_comps_update(self):
        self.components_changed.emit([self.ed_a.text(), self.ed_b.text(), self.ed_c.text()])

    def _on_grid_update(self):
        self.grid_changed.emit(self.chk_grid.isChecked(), self.sp_step.value())

    def _on_item_changed(self, item: QTableWidgetItem):
        if self._block_signals:
            return
        
        uid = self._row_to_uid.get(item.row())
        if not uid:
            return
        
        col = item.column()
        txt = item.text().strip()
        key = (item.row(), col)
        
        if col == 0:
            if not txt:
                prev = self._previous_values.get(key, "Unnamed")
                self._show_validation_error(item, f"Name cannot be empty, restored '{prev}'")
                self._block_signals = True
                item.setText(prev)
                self._block_signals = False
                return
            
            self._previous_values[key] = txt
            self.composition_edited.emit(uid, CompositionUpdate(name=txt[:COMP_NAME_MAX_LENGTH]))
            return
        
        field = _COLUMN_TO_FIELD.get(col)
        if not field:
            return
        
        try:
            val = float(txt.replace(',', '.'))
        except ValueError:
            prev = self._previous_values.get(key, "0.0")
            self._show_validation_error(item, f"Invalid number '{txt}', restored to {prev}")
            self._block_signals = True
            item.setText(prev)
            self._block_signals = False
            return
        
        if val < COORD_INPUT_MIN:
            self._show_validation_error(item, f"Value must be ≥ {COORD_INPUT_MIN}, using {COORD_INPUT_MIN}")
            val = COORD_INPUT_MIN
            self._block_signals = True
            item.setText(f"{COORD_INPUT_MIN:.{DISPLAY_DECIMALS_TABLE}f}")
            self._block_signals = False
        
        if val > COORD_INPUT_MAX:
            self._show_validation_error(item, f"Value must be ≤ {COORD_INPUT_MAX}, clamped")
            val = COORD_INPUT_MAX
            self._block_signals = True
            item.setText(f"{COORD_INPUT_MAX:.{DISPLAY_DECIMALS_TABLE}f}")
            self._block_signals = False
        
        self._previous_values[key] = item.text()
        self.composition_edited.emit(uid, CompositionUpdate.coordinate(field, val))
        
        # Проверяем сумму после изменения и показываем предупреждение
        self._check_row_normalization(item.row())

    def _show_validation_error(self, item: QTableWidgetItem, message: str):
        item.setBackground(QBrush(_get_error_color()))
        self.validation_error.emit(message)
        QTimer.singleShot(2000, lambda: self._reset_cell_background(item))

    def _reset_cell_background(self, item: QTableWidgetItem):
        try:
            item.setBackground(QBrush(_get_normal_color()))
        except RuntimeError:
            pass

    def _check_row_normalization(self, row: int):
        """Проверяет нормализацию строки и показывает предупреждение если нужно"""
        try:
            item_a = self.table.item(row, 1)
            item_b = self.table.item(row, 2)
            item_c = self.table.item(row, 3)
            
            if not item_a or not item_b or not item_c:
                return
                
            a = float(item_a.text().replace(',', '.'))
            b = float(item_b.text().replace(',', '.'))
            c = float(item_c.text().replace(',', '.'))
        except (ValueError, AttributeError):
            return
        
        total = math.fsum([a, b, c])
        
        if abs(total) < 1e-9:
            self.validation_error.emit("Warning: Sum ≈ 0 (invalid composition)")
            return
        
        if abs(total - 1.0) > NORMALIZATION_WARNING_THRESHOLD:
            # Вычисляем нормализованные значения
            na, nb, nc = a / total, b / total, c / total
            self.validation_error.emit(
                f"Note: Sum = {total:.3f}. Normalized: {na:.3f} : {nb:.3f} : {nc:.3f}"
            )

    def _on_context_menu(self, position):
        item = self.table.itemAt(position)
        if item:
            row = item.row()
            uid = self._row_to_uid.get(row)
            
            menu = QMenu()
            
            action_style = QAction("✏️ Edit Style...", self)
            action_style.triggered.connect(lambda: self.request_edit_style.emit(uid))
            menu.addAction(action_style)
            
            menu.addSeparator()

            action_del = QAction("Delete Composition", self)
            action_del.triggered.connect(lambda: self.request_delete_composition.emit(uid))
            menu.addAction(action_del)
            
            menu.exec(self.table.viewport().mapToGlobal(position))

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Delete:
            item = self.table.currentItem()
            if item:
                uid = self._row_to_uid.get(item.row())
                if uid:
                    self.request_delete_composition.emit(uid)
                    return
        
        if event.key() == Qt.Key.Key_F2:
            item = self.table.currentItem()
            if item:
                self.table.editItem(item)
                return
        
        super().keyPressEvent(event)

    # НОВЫЕ СЛОТЫ ДЛЯ КНОПОК
    def _on_style_click(self):
        item = self.table.currentItem()
        if item:
            uid = self._row_to_uid.get(item.row())
            if uid:
                self.request_edit_style.emit(uid)
        else:
            self.validation_error.emit("Select a composition to style")

    def _on_del_click(self):
        item = self.table.currentItem()
        if item:
            uid = self._row_to_uid.get(item.row())
            if uid:
                self.request_delete_composition.emit(uid)
        else:
            self.validation_error.emit("Select a composition to delete")
