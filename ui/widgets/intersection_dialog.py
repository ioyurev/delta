from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, 
                               QComboBox, QPushButton, QCheckBox, QLabel, QGroupBox)
from PySide6.QtCore import Signal
from core.models import RenderOverlay, OverlayLine, Composition
from core import math_utils
from core.project_controller import ProjectController 

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
        self.found_intersection = None # Здесь храним найденную точку (Composition)
        
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
        
        form.addRow("Line 1:", self.cb_line1)
        form.addRow("Line 2:", self.cb_line2)
        gb_sel.setLayout(form)
        layout.addWidget(gb_sel)
        
        # Опции
        self.chk_extrap = QCheckBox("Show Extrapolations (to borders)")
        self.chk_extrap.setChecked(True)
        self.chk_extrap.toggled.connect(self._recalc)
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
        
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.reject)
        
        btns.addWidget(self.btn_add)
        btns.addWidget(btn_close)
        layout.addLayout(btns)

    def _populate_combos(self):
        """Заполняет комбобоксы списком линий"""
        # 2. Используем геттер контроллера
        lines = self._controller.get_all_lines()
        
        for i, line in enumerate(lines):
            # 3. Используем "умный" метод контроллера для поиска концов
            start_comp, end_comp = self._controller.get_line_endpoints(line.uid)
            
            n1 = start_comp.name if start_comp else "?"
            n2 = end_comp.name if end_comp else "?"
            txt = f"{i+1}: {n1} — {n2}"
            
            self.cb_line1.addItem(txt, line.uid)
            self.cb_line2.addItem(txt, line.uid)
        
        # По умолчанию выбираем разные линии
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
        
        # 4. Получаем объекты линий через контроллер
        line1 = self._controller.get_line(uid1)
        line2 = self._controller.get_line(uid2)
        
        if not line1 or not line2:
            self.lbl_result.setText("Invalid lines.")
            self._emit_overlay(overlay)
            return
        
        # 5. Получаем составы (точки) через контроллер
        p1_comp, p2_comp = self._controller.get_line_endpoints(line1.uid)
        p3_comp, p4_comp = self._controller.get_line_endpoints(line2.uid)
        
        # Явная проверка для Pylance (Type Narrowing)
        if p1_comp is None or p2_comp is None or p3_comp is None or p4_comp is None:
            self.lbl_result.setText("Invalid lines (missing compositions).")
            self._emit_overlay(overlay)
            return
        
        # Подсветка выбранных линий
        overlay.highlight_lines_uids = [uid1, uid2]
        # Экстраполяция до границ
        if self.chk_extrap.isChecked():
            ext1 = math_utils.get_line_triangle_intersections(p1_comp.composition, p2_comp.composition)
            if len(ext1) == 2:
                overlay.extrap_lines.append(
                    OverlayLine(start=ext1[0], end=ext1[1], color=line1.style.color)
                )
            
            ext2 = math_utils.get_line_triangle_intersections(p3_comp.composition, p4_comp.composition)
            if len(ext2) == 2:
                overlay.extrap_lines.append(
                    OverlayLine(start=ext2[0], end=ext2[1], color=line2.style.color)
                )
        
        # Расчёт пересечения
        intersect = math_utils.solve_intersection(p1_comp.composition, p2_comp.composition, p3_comp.composition, p4_comp.composition)
        
        if intersect:
            # Используем normalized вместо устаревшего as_array()
            arr = intersect.normalized
            is_inside = all(x >= -0.001 for x in arr)
            
            if is_inside:
                self.found_intersection = intersect
                self.btn_add.setEnabled(True)
                overlay.intersect_point = intersect
                
                nms = self._controller.get_components()
                self.lbl_result.setText(
                    f"Intersection found:\n"
                    f"{nms[0]} = {intersect.a:.4f}\n"
                    f"{nms[1]} = {intersect.b:.4f}\n"
                    f"{nms[2]} = {intersect.c:.4f}"
                )
                self.lbl_result.setStyleSheet(
                    "color: green; font-weight: bold; "
                    "background: #e0f0e0; padding: 10px;"
                )
            else:
                self.lbl_result.setText("Intersection is outside the triangle.")
                self.lbl_result.setStyleSheet(
                    "color: orange; font-weight: bold; "
                    "background: #fff0e0; padding: 10px;"
                )
        else:
            self.lbl_result.setText("Lines are parallel.")
            self.lbl_result.setStyleSheet(
                "color: red; font-weight: bold; "
                "background: #ffe0e0; padding: 10px;"
            )
        
        # ✅ Испускаем сигнал вместо прямого вызова
        self._emit_overlay(overlay)
    
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
