from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, 
                               QComboBox, QPushButton, QCheckBox, QLabel, QGroupBox)
from PySide6.QtCore import Signal
from core.models import RenderOverlay, Composition, TieLine
from core.project_controller import ProjectController
from core.exceptions import EntityNotFoundError
from ui.widgets.helpers import populate_combo
from typing import Optional

class IntersectionDialog(QDialog):
    """
    Диалог расчёта пересечения линий.
    
    Signals:
        overlay_changed(RenderOverlay): Испускается при изменении overlay для отрисовки
        intersection_found(Composition): Испускается при добавлении точки пересечения
    """
    
    overlay_changed = Signal(RenderOverlay)
    intersection_found = Signal(Composition)
    
    def __init__(self, controller: ProjectController, parent=None):
        super().__init__(parent)
        self._controller = controller
        self.found_intersection: Optional[Composition] = None # Здесь храним найденную точку (Composition)
        
        self.setWindowTitle("Intersection Calculator")
        self.setFixedWidth(400)
        
        self._init_ui()
        
        # Заполняем списки
        self._populate_combos()
        
        # Сразу считаем при открытии
        self._recalc()

    def _init_ui(self):
        layout = QVBoxLayout(self)
        
        # Группа выбора линий
        gb_sel = QGroupBox("Select Lines to Intersect")
        form = QFormLayout()
        
        self.cb_line1 = QComboBox()
        self.cb_line1.currentIndexChanged.connect(self._recalc)
        
        self.cb_line2 = QComboBox()
        self.cb_line2.currentIndexChanged.connect(self._recalc)
        
        # Добавляем tooltips для выбора линий
        self.cb_line1.setToolTip("First line for intersection")
        self.cb_line2.setToolTip("Second line for intersection")
        
        form.addRow("Line 1:", self.cb_line1)
        form.addRow("Line 2:", self.cb_line2)
        gb_sel.setLayout(form)
        layout.addWidget(gb_sel)
        
        # Опции
        self.chk_extrap = QCheckBox("Show Extrapolations (to borders)")
        self.chk_extrap.setChecked(True)
        self.chk_extrap.toggled.connect(self._recalc)
        
        # Добавляем tooltip для опции экстраполяции
        self.chk_extrap.setToolTip("Extend lines to triangle boundaries to find intersection")
        
        layout.addWidget(self.chk_extrap)
        
        # Результат
        self.lbl_result = QLabel("Result: ...")
        self.lbl_result.setWordWrap(True)
        self.lbl_result.setStyleSheet("font-weight: bold; padding: 10px; background: #f0f0f0; border-radius: 4px;")
        layout.addWidget(self.lbl_result)
        
        # Кнопки
        btns = QHBoxLayout()
        self.btn_add = QPushButton("Add Intersection as Composition")
        self.btn_add.setEnabled(False)
        self.btn_add.clicked.connect(self._on_add_comp)
        
        # Добавляем tooltip для кнопки сохранения
        self.btn_add.setToolTip("Save intersection point as a new composition")
        
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.reject)
        
        btns.addWidget(self.btn_add)
        btns.addWidget(btn_close)
        layout.addLayout(btns)

    def _populate_combos(self):
        """Заполняет комбобоксы списком линий"""
        lines = self._controller.get_all_lines()
        
        def get_line_text(line: TieLine) -> str:
            try:
                start, end = self._controller.get_line_endpoints(line.uid)
                return f"{start.name} — {end.name}"
            except EntityNotFoundError:
                return "? — ?"
        
        for cb in (self.cb_line1, self.cb_line2):
            populate_combo(
                cb,
                lines,
                get_text=get_line_text,
                get_data=lambda line: line.uid,
                preserve_selection=False
            )
        
        if self.cb_line2.count() > 1:
            self.cb_line2.setCurrentIndex(1)

    def _recalc(self):
        """Пересчитывает пересечение и ИСПУСКАЕТ СИГНАЛ с overlay"""
        uid1 = self.cb_line1.currentData()
        uid2 = self.cb_line2.currentData()
        
        # Сброс состояния
        overlay = RenderOverlay()
        self.found_intersection = None
        self.btn_add.setEnabled(False)
        
        # Валидация
        if uid1 == uid2 or not uid1 or not uid2:
            self.lbl_result.setText("Select two different lines.")
            self._emit_overlay(overlay)
            return
        
        # Вызов контроллера (вся логика теперь там)
        result = self._controller.calculate_intersection(uid1, uid2, self.chk_extrap.isChecked())
        
        # Обновление UI по результату
        self.lbl_result.setText(result.message)
        
        # Применяем стиль, если он есть, иначе сбрасываем на дефолт
        if result.status_style:
            self.lbl_result.setStyleSheet(result.status_style)
        else:
            self.lbl_result.setStyleSheet("font-weight: bold; padding: 10px; background: #f0f0f0; border-radius: 4px;")

        # Сохраняем результат для кнопки Add
        if result.intersection and result.is_inside:
            self.found_intersection = result.intersection
            self.btn_add.setEnabled(True)
            
        # Обновляем графику
        self._emit_overlay(result.overlay or RenderOverlay())
    
    def _emit_overlay(self, overlay: RenderOverlay):
        """Безопасно испускает сигнал overlay_changed"""
        self.overlay_changed.emit(overlay)

    def _on_add_comp(self):
        """Обработчик кнопки 'Add Intersection as Composition'"""
        if self.found_intersection:
            # ✅ Испускаем сигнал с результатом
            self.intersection_found.emit(self.found_intersection)
            self.accept()
    
    def _on_close(self) -> None:
        """Обработчик закрытия — очищаем overlay"""
        self.overlay_changed.emit(RenderOverlay())  # Пустой overlay
        self.reject()
    
    def closeEvent(self, event) -> None:
        """Перехватываем закрытие окна (крестик)"""
        self.overlay_changed.emit(RenderOverlay())
        super().closeEvent(event)
