from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, 
                               QLabel, QLineEdit, QPushButton, QCheckBox, 
                               QDoubleSpinBox, QTableWidgetItem, QHeaderView, 
                               QMenu, QTableWidget, QApplication)
from PySide6.QtCore import Signal, Qt, QTimer
from PySide6.QtGui import QAction, QColor, QBrush, QKeyEvent
from core.models import ProjectData, CompositionUpdate

# Маппинг колонка -> поле CompositionUpdate
_COLUMN_TO_FIELD = {1: 'a', 2: 'b', 3: 'c'}

# Цвета для подсветки (адаптивные)
def _get_error_color() -> QColor:
    """Возвращает цвет ошибки, адаптированный к теме"""
    palette = QApplication.palette()
    base = palette.base().color()
    # Если тёмная тема — тёмно-красный, иначе светло-красный
    if base.lightness() < 128:
        return QColor(100, 40, 40)  # Тёмно-красный для тёмной темы
    return QColor(255, 200, 200)  # Светло-красный для светлой темы

def _get_normal_color() -> QColor:
    """Возвращает нормальный цвет фона из текущей палитры"""
    return QApplication.palette().base().color()


class CompositionsTable(QWidget):
    data_changed = Signal(str, CompositionUpdate) 
    composition_added = Signal()
    style_request = Signal(str) 
    composition_deleted = Signal(str)
    components_changed = Signal(list)
    grid_changed = Signal(bool, float)
    view_mode_changed = Signal(bool)
    
    # Новый сигнал для сообщений
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
        btn_set = QPushButton("Update Names")
        btn_set.clicked.connect(self._on_comps_update)
        
        # Добавляем tooltips
        self.ed_a.setToolTip("Name of component A (vertex)")
        self.ed_b.setToolTip("Name of component B (vertex)")
        self.ed_c.setToolTip("Name of component C (vertex)")
        btn_set.setToolTip("Apply new component names to the diagram")
        
        h_comp.addWidget(QLabel("Labels:"))
        h_comp.addWidget(self.ed_a)
        h_comp.addWidget(self.ed_b)
        h_comp.addWidget(self.ed_c)
        h_comp.addWidget(btn_set)
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
        
        # Добавляем tooltips
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
        
        # Добавляем tooltip для таблицы
        self.table.setToolTip("Double-click cell to edit. Right-click for more options.")
        
        # Контекстное меню
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        
        # Устанавливаем фокус-политику для таблицы
        self.table.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        
        btn_add = QPushButton("➕ Add New Composition")
        btn_add.setStyleSheet("""
            QPushButton {
                padding: 8px 16px;
                font-weight: bold;
            }
        """)
        btn_add.clicked.connect(self.composition_added.emit)
        
        # Добавляем tooltip для кнопки добавления
        btn_add.setToolTip("Create a new composition point (Ctrl+click on diagram also works)")
        
        layout.addWidget(self.table)
        layout.addWidget(btn_add)
        
        self._block_signals = False
        self._row_to_uid: dict[int, str] = {}
        self._previous_values: dict[tuple[int, int], str] = {}  # Кэш предыдущих значений

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
        
        self.table.setHorizontalHeaderLabels(["Name"] + list(project_data.components))
        self._row_to_uid = {}
        self._previous_values = {}  # Очищаем кэш
        
        for i, p in enumerate(project_data.compositions):
            self._row_to_uid[i] = p.uid
            
            vals = [
                p.name,
                f"{p.composition.a:.4f}",
                f"{p.composition.b:.4f}",
                f"{p.composition.c:.4f}"
            ]
            
            for col, val in enumerate(vals):
                item = self.table.item(i, col)
                if not item:
                    item = QTableWidgetItem()
                    self.table.setItem(i, col, item)
                
                if item.text() != val:
                    item.setText(val)
                
                # Сохраняем текущее значение как "предыдущее"
                self._previous_values[(i, col)] = val
                
                # Сбрасываем фон на нормальный
                item.setBackground(QBrush(_get_normal_color()))
                
        self._block_signals = False

    def select_composition(self, uid: str) -> None:
        """Выделяет строку с указанным составом и прокручивает к ней"""
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
        
        # Колонка 0 — имя (валидация не нужна)
        if col == 0:
            if not txt:
                # Пустое имя → восстановить предыдущее или "Unnamed"
                prev = self._previous_values.get(key, "Unnamed")
                self._show_validation_error(item, f"Name cannot be empty, restored '{prev}'")
                self._block_signals = True
                item.setText(prev)
                self._block_signals = False
                return
            
            self._previous_values[key] = txt
            self.data_changed.emit(uid, CompositionUpdate(name=txt[:100]))
            return
        
        # Колонки 1-3 — координаты
        field = _COLUMN_TO_FIELD.get(col)
        if not field:
            return
        
        # Пытаемся распарсить число
        try:
            val = float(txt.replace(',', '.'))
        except ValueError:
            prev = self._previous_values.get(key, "0.0")
            self._show_validation_error(item, f"Invalid number '{txt}', restored to {prev}")
            self._block_signals = True
            item.setText(prev)
            self._block_signals = False
            return
        
        # Проверка на отрицательное
        if val < 0:
            self._show_validation_error(item, "Negative values not allowed, using 0.0")
            val = 0.0
            self._block_signals = True
            item.setText("0.0000")
            self._block_signals = False
        
        # Проверка на слишком большое значение
        if val > 1000:
            self._show_validation_error(item, "Value too large, clamped to 1000")
            val = 1000.0
            self._block_signals = True
            item.setText("1000.0000")
            self._block_signals = False
        
        # Обновляем кэш
        self._previous_values[key] = item.text()
        
        self.data_changed.emit(uid, CompositionUpdate.coordinate(field, val))

    def _show_validation_error(self, item: QTableWidgetItem, message: str):
        """Показывает ошибку валидации"""
        # 1. Подсвечиваем ячейку красным
        item.setBackground(QBrush(_get_error_color()))
        
        # 2. Испускаем сигнал для StatusBar
        self.validation_error.emit(message)
        
        # 3. Через 2 секунды убираем подсветку
        QTimer.singleShot(2000, lambda: self._reset_cell_background(item))

    def _reset_cell_background(self, item: QTableWidgetItem):
        """Сбрасывает фон ячейки на нормальный"""
        try:
            item.setBackground(QBrush(_get_normal_color()))
        except RuntimeError:
            # Ячейка могла быть удалена
            pass

    def _on_context_menu(self, position):
        """Обработчик ПКМ по таблице"""
        item = self.table.itemAt(position)
        if item:
            row = item.row()
            uid = self._row_to_uid.get(row)
            
            menu = QMenu()
            
            action_style = QAction("Customize Marker...", self)
            action_style.triggered.connect(lambda: self.style_request.emit(uid))
            menu.addAction(action_style)
            
            menu.addSeparator()

            action_del = QAction("Delete Composition", self)
            action_del.triggered.connect(lambda: self.composition_deleted.emit(uid))
            menu.addAction(action_del)
            
            menu.exec(self.table.viewport().mapToGlobal(position))

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Обработка нажатий клавиш"""
        if event.key() == Qt.Key.Key_Delete:
            item = self.table.currentItem()
            if item:
                uid = self._row_to_uid.get(item.row())
                if uid:
                    self.composition_deleted.emit(uid)
                    return
        
        # F2 — редактирование текущей ячейки
        if event.key() == Qt.Key.Key_F2:
            item = self.table.currentItem()
            if item:
                self.table.editItem(item)
                return
        
        super().keyPressEvent(event)
