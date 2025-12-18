from PySide6.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout, QGroupBox, 
                               QLabel, QLineEdit, QPushButton, QCheckBox, 
                               QDoubleSpinBox, QTableWidgetItem, QHeaderView, QMenu, QTableWidget)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QAction
from core.models import ProjectData, CompositionUpdate

class CompositionsTable(QWidget):
    data_changed = Signal(str, CompositionUpdate) 
    composition_added = Signal()
    style_request = Signal(str) 
    composition_deleted = Signal(str)
    components_changed = Signal(list)
    grid_changed = Signal(bool, float)
    view_mode_changed = Signal(bool)

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
        
        # ВКЛЮЧАЕМ КОНТЕКСТНОЕ МЕНЮ
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._on_context_menu)
        
        btn_add = QPushButton("Add New Composition")
        btn_add.clicked.connect(self.composition_added.emit)
        
        layout.addWidget(self.table)
        layout.addWidget(btn_add)
        
        self._block_signals = False
        self._row_to_uid = {} 

    def update_view(self, project_data: ProjectData) -> None:
        # Обновляем настройки UI
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

        # ЭФФЕКТИВНОЕ ОБНОВЛЕНИЕ ТАБЛИЦЫ (без потери фокуса)
        self._block_signals = True
        
        # 1. Синхронизируем количество строк
        current_rows = self.table.rowCount()
        target_rows = len(project_data.compositions)
        
        if current_rows < target_rows:
            # Добавляем недостающие строки
            for _ in range(target_rows - current_rows):
                self.table.insertRow(self.table.rowCount())
        elif current_rows > target_rows:
            # Удаляем лишние строки (с конца)
            for _ in range(current_rows - target_rows):
                self.table.removeRow(self.table.rowCount() - 1)
        
        # 2. Обновляем заголовки
        self.table.setHorizontalHeaderLabels(["Name"] + list(project_data.components))
        self._row_to_uid = {}
        
        # 3. Обновляем данные точечно (только изменившиеся ячейки)
        for i, p in enumerate(project_data.compositions):
            self._row_to_uid[i] = p.uid
            
            # Данные для ячеек
            vals = [
                p.name,
                f"{p.composition.a:.4f}",
                f"{p.composition.b:.4f}",
                f"{p.composition.c:.4f}"
            ]
            
            for col, val in enumerate(vals):
                item = self.table.item(i, col)
                if not item:
                    # Создаем новую ячейку, если её нет
                    item = QTableWidgetItem()
                    self.table.setItem(i, col, item)
                
                # Обновляем текст ТОЛЬКО если он отличается
                if item.text() != val:
                    item.setText(val)
                
        self._block_signals = False

    def _on_comps_update(self):
        self.components_changed.emit([self.ed_a.text(), self.ed_b.text(), self.ed_c.text()])

    def _on_grid_update(self):
        self.grid_changed.emit(self.chk_grid.isChecked(), self.sp_step.value())

    def _on_item_changed(self, item):
        if self._block_signals:
            return
        
        row = item.row()
        col = item.column()
        uid = self._row_to_uid.get(row)
        if not uid:
            return
        
        txt = item.text()
        update_obj = None # Готовим объект
        
        if col == 0:
            # Имя
            if len(txt) > 100:
                txt = txt[:100]
            # Создаем типизированный update только с именем
            update_obj = CompositionUpdate(name=txt)
            
        else:
            # Координаты a, b, c
            try:
                val = float(txt.replace(',', '.'))
                if val < 0:
                    val = 0.0
                    item.setText("0.0")
                
                # Определяем, какое поле обновляем, по номеру колонки
                if col == 1:
                    update_obj = CompositionUpdate(a=val)
                elif col == 2:
                    update_obj = CompositionUpdate(b=val)
                elif col == 3:
                    update_obj = CompositionUpdate(c=val)
                    
            except ValueError:
                item.setText("0.0")
                return

        # Если объект создан, отправляем сигнал
        if update_obj:
            self.data_changed.emit(uid, update_obj)

    def _on_context_menu(self, position):
        """Обработчик ПКМ по таблице"""
        item = self.table.itemAt(position)
        if item:
            row = item.row()
            uid = self._row_to_uid.get(row)
            
            menu = QMenu()
            
            # Action: Style
            action_style = QAction("Customize Marker...", self)
            action_style.triggered.connect(lambda: self.style_request.emit(uid))
            menu.addAction(action_style)
            
            menu.addSeparator()

            # Action: Delete (НОВОЕ)
            action_del = QAction("Delete Composition", self)
            # Добавляем красный цвет тексту для опасного действия (опционально)
            # action_del.setStyleSheet("color: red;") - в меню Qt это сложнее, пока оставим стандартно
            action_del.triggered.connect(lambda: self.composition_deleted.emit(uid))
            menu.addAction(action_del)
            
            menu.exec(self.table.viewport().mapToGlobal(position))
