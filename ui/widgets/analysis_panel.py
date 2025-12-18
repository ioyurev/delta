from PySide6.QtWidgets import (QWidget, QVBoxLayout, QGroupBox, QLabel, 
                               QComboBox, QFormLayout, QRadioButton, QButtonGroup, 
                               QHBoxLayout, QStackedWidget)
from PySide6.QtCore import Qt, Signal
from core.models import Composition, RenderOverlay, OverlayLine, ProjectData, NamedComposition, CompositionError
from core import math_utils
from typing import Optional
from ui.widgets.helpers import create_composition_spin
from fractions import Fraction
from math import gcd
from functools import reduce


class AnalysisPanel(QWidget):
    update_needed = Signal()
    overlay_changed = Signal()

    def __init__(self):
        super().__init__()
        layout = QVBoxLayout(self)
        
        # --- 1. Mode ---
        gb_mode = QGroupBox("1. Basis Mode")
        h_mode = QHBoxLayout()
        self.rb_linear = QRadioButton("Linear (2 Compositions)")
        self.rb_ternary = QRadioButton("Ternary (3 Compositions)")
        self.rb_linear.setChecked(True)
        
        self.bg = QButtonGroup()
        self.bg.addButton(self.rb_linear)
        self.bg.addButton(self.rb_ternary)
        
        h_mode.addWidget(self.rb_linear)
        h_mode.addWidget(self.rb_ternary)
        
        gb_mode.setLayout(h_mode)
        layout.addWidget(gb_mode)
        
        self.bg.buttonClicked.connect(self._on_settings_changed)

        # --- 2. Basis ---
        gb_basis = QGroupBox("2. Define Basis")
        form_basis = QFormLayout()
        
        self.cb_comp_a = QComboBox()
        self.cb_comp_b = QComboBox()
        self.cb_comp_c = QComboBox()
        
        self.cb_comp_c.setVisible(False)
        self.lbl_c = QLabel("Composition C:")
        self.lbl_c.setVisible(False)
        
        self.cb_comp_a.currentIndexChanged.connect(self._on_calc_request)
        self.cb_comp_b.currentIndexChanged.connect(self._on_calc_request)
        self.cb_comp_c.currentIndexChanged.connect(self._on_calc_request)
        
        form_basis.addRow("Composition A:", self.cb_comp_a)
        form_basis.addRow("Composition B:", self.cb_comp_b)
        form_basis.addRow(self.lbl_c, self.cb_comp_c)
        gb_basis.setLayout(form_basis)
        layout.addWidget(gb_basis)

        # --- 3. Target ---
        gb_target = QGroupBox("3. Target Point")
        v_target = QVBoxLayout()
        
        self.cb_target_source = QComboBox()
        self.cb_target_source.addItems(["Mouse Cursor", "Existing Composition", "Manual Input"])
        self.cb_target_source.currentIndexChanged.connect(self._on_source_changed)
        v_target.addWidget(self.cb_target_source)
        
        self.stack = QStackedWidget()
        
        # P0
        lbl_cursor = QLabel("Move mouse over the plot...")
        lbl_cursor.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_cursor.setStyleSheet("color: gray; font-style: italic;")
        self.stack.addWidget(lbl_cursor)
        # P1
        self.cb_target_comp = QComboBox()
        self.cb_target_comp.currentIndexChanged.connect(self._on_calc_request)
        self.stack.addWidget(self.cb_target_comp)
        # P2 (Manual)
        widget_manual = QWidget()
        v_man = QVBoxLayout(widget_manual) # Меняем QHBoxLayout на QVBoxLayout
        v_man.setContentsMargins(0,0,0,0)
        
        h_inputs = QHBoxLayout()
        self.sp_a = self._create_spin()
        self.sp_b = self._create_spin()
        self.sp_c = self._create_spin()
        
        # Подключаем проверку суммы к изменению спинбоксов
        self.sp_a.valueChanged.connect(self._check_manual_sum)
        self.sp_b.valueChanged.connect(self._check_manual_sum)
        self.sp_c.valueChanged.connect(self._check_manual_sum)

        h_inputs.addWidget(QLabel("A:"))
        h_inputs.addWidget(self.sp_a)
        h_inputs.addWidget(QLabel("B:"))
        h_inputs.addWidget(self.sp_b)
        h_inputs.addWidget(QLabel("C:"))
        h_inputs.addWidget(self.sp_c)
        
        v_man.addLayout(h_inputs)
        
        # Добавляем лейбл суммы
        self.lbl_sum_warning = QLabel("Sum: 0.00")
        self.lbl_sum_warning.setAlignment(Qt.AlignmentFlag.AlignRight)
        v_man.addWidget(self.lbl_sum_warning)
        
        self.stack.addWidget(widget_manual)
        
        v_target.addWidget(self.stack)
        gb_target.setLayout(v_target)
        layout.addWidget(gb_target)
        
        # --- 4. Result ---
        self.lbl_info = QLabel("Result...")
        self.lbl_info.setWordWrap(True)
        self.lbl_info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        
        # Сохраняем исходный стиль в переменную класса
        self.default_style = """
            QLabel {
                font-family: monospace;
                font-size: 13px; 
                font-weight: bold; 
                color: #333;
                background-color: #f0f8ff;
                border: 1px solid #c0d8f0;
                border-radius: 4px;
                padding: 10px;
            }
        """
        # Применяем его
        self.lbl_info.setStyleSheet(self.default_style)
        
        layout.addWidget(self.lbl_info)
        layout.addStretch()
        
        self.project = None
        self._last_cursor_comp = Composition(0,0,0)

    def _create_spin(self):
        return create_composition_spin(on_change=self._on_calc_request)

    def _check_manual_sum(self):
        total = self.sp_a.value() + self.sp_b.value() + self.sp_c.value()
        self.lbl_sum_warning.setText(f"Sum: {total:.3f}")
        
        # Если сумма отличается от 1.0 более чем на 1%, красим в красный
        if abs(total - 1.0) > 0.01:
            self.lbl_sum_warning.setStyleSheet("color: red; font-weight: bold;")
            self.lbl_sum_warning.setText(f"Sum: {total:.3f} (Must be 1.0)")
        else:
            self.lbl_sum_warning.setStyleSheet("color: green;")

    def update_view(self, project_data: ProjectData):
        self.project = project_data
        
        # Все комбобоксы с составами
        comp_combos = [
            self.cb_comp_a,
            self.cb_comp_b, 
            self.cb_comp_c,
            self.cb_target_comp
        ]
        
        self._populate_comp_combos(comp_combos)

    def _populate_comp_combos(self, combos: list):
        """Заполняет список комбобоксов составами"""
        if not self.project:
            return
        
        # Сортируем один раз
        sorted_comps = sorted(self.project.compositions, key=lambda p: p.name)
        
        for cb in combos:
            cur_uid = cb.currentData()
            
            cb.blockSignals(True)
            cb.clear()
            
            for p in sorted_comps:
                name = p.name or "[Unnamed]"
                cb.addItem(name, p.uid)
            
            # Восстанавливаем выбор
            if cur_uid:
                idx = cb.findData(cur_uid)
                if idx >= 0:
                    cb.setCurrentIndex(idx)
            
            cb.blockSignals(False)

    def _on_settings_changed(self):
        is_ternary = self.rb_ternary.isChecked()
        self.cb_comp_c.setVisible(is_ternary)
        self.lbl_c.setVisible(is_ternary)
        self._emit_update_req()
        self._on_calc_request()

    def _on_source_changed(self):
        self.stack.setCurrentIndex(self.cb_target_source.currentIndex())
        self._on_calc_request()

    def on_cursor_move(self, comp: Composition):
        self._last_cursor_comp = comp
        if self.cb_target_source.currentIndex() == 0:
            self._calculate_and_display(comp)
            self.overlay_changed.emit()

    def _on_calc_request(self, value: Optional[float] = None):
        if not self.project:
            return
        idx = self.cb_target_source.currentIndex()
        target_comp = None
        if idx == 0:
            target_comp = self._last_cursor_comp
        elif idx == 1:
            uid = self.cb_target_comp.currentData()
            p = self._get_comp(uid)
            if p:
                target_comp = p.composition
        elif idx == 2:
            target_comp = Composition(self.sp_a.value(), self.sp_b.value(), self.sp_c.value())
            # Check for invalid composition (sum ≈ 0)
            if target_comp.total < 1e-9:
                self.lbl_info.setText("Invalid composition (Sum ≈ 0)")
                self.lbl_info.setStyleSheet("color: red;")
                return
        if target_comp:
            self._calculate_and_display(target_comp)
            self._emit_update_req()

    def _find_integer_ratio(self, floats):
        """
        Находит целочисленное соотношение для списка долей.
        
        Примеры:
            [0.5, 0.5] → [1, 1]
            [0.4, 0.0, 0.6] → [2, 0, 3]
            [0.333, 0.333, 0.333] → [1, 1, 1]
            [0.125, 0.375, 0.5] → [1, 3, 4]
        """
        
        if not floats or all(f == 0 for f in floats):
            return None
        
        # 1. Конвертируем float в Fraction с ограничением знаменателя
        #    limit_denominator(100) находит ближайшую дробь с знаменателем ≤ 100
        fractions = []
        for f in floats:
            if f < 0:
                return None  # Отрицательные — экстраполяция, ratio не имеет смысла
            frac = Fraction(f).limit_denominator(100)
            fractions.append(frac)
        
        # 2. Находим общий знаменатель (НОК всех знаменателей)
        denominators = [frac.denominator for frac in fractions]
        lcm = denominators[0]
        for d in denominators[1:]:
            lcm = lcm * d // gcd(lcm, d)
        
        # 3. Приводим к общему знаменателю → получаем целые числители
        integers = [int(frac * lcm) for frac in fractions]
        
        # 4. Сокращаем на НОД всех чисел
        common_gcd = reduce(gcd, [i for i in integers if i != 0], integers[0])
        if common_gcd > 1:
            integers = [i // common_gcd for i in integers]
        
        # 5. Проверяем, что не слишком большие числа (разумный предел)
        if any(i > 20 for i in integers):
            return None  # Слишком сложное соотношение
        
        return integers

    def _calculate_and_display(self, comp: Composition):
        # Проверка на "пустую" точку
        if comp.total < 1e-9:
            self.lbl_info.setText("Invalid composition (Sum ≈ 0)")
            self.lbl_info.setStyleSheet("color: red;")
            return

        uid_a = self.cb_comp_a.currentData()
        uid_b = self.cb_comp_b.currentData()
        p_a = self._get_comp(uid_a)
        p_b = self._get_comp(uid_b)
        
        if not p_a or not p_b:
            return

        is_mouse_source = (self.cb_target_source.currentIndex() == 0)

        try:
            # --- LINEAR MODE ---
            if self.rb_linear.isChecked():
                if uid_a == uid_b:
                    self.lbl_info.setText("Error: Basis compositions must be different.")
                    self.lbl_info.setStyleSheet(self.default_style)
                    return
                
                # ИЗМЕНЕНИЕ: Проверяем коллинеарность (лежит ли на прямой)
                # ТОЛЬКО если источник НЕ мышь.
                # Для мыши мы допускаем проекцию (перпендикуляр).
                if not is_mouse_source:
                    if not math_utils.is_point_on_line(p_a.composition, p_b.composition, comp, tol=0.01):
                        self.lbl_info.setText("Error: Point is NOT on the selected line.")
                        self.lbl_info.setStyleSheet("color: #D8000C; background-color: #FFBABA; padding: 10px; border-radius: 4px;")
                        return

                # Считаем рычаг (для Mouse Cursor это будет проекция)
                t = math_utils.get_lever_fraction(p_a.composition, p_b.composition, comp)
                
                # Проверка на экстраполяцию
                epsilon = 1e-3 
                if t < -epsilon or t > (1.0 + epsilon):
                    self.lbl_info.setText("Error: Point is OUTSIDE the segment.")
                    self.lbl_info.setStyleSheet("color: #D8000C; background-color: #FFBABA; padding: 10px; border-radius: 4px;")
                    return
                else:
                    self.lbl_info.setStyleSheet(self.default_style)

                val_a = 1.0 - t
                val_b = t
                
                res_text = (f"Basis Fractions:\n"
                            f"  {p_a.name:<10} : {val_a*100:.2f}%\n"
                            f"  {p_b.name:<10} : {val_b*100:.2f}%")
                
                if not is_mouse_source:
                    ints = self._find_integer_ratio([val_a, val_b])
                    if ints:
                        res_text += (f"\n\nStoichiometry (Ratio):\n"
                                     f"  {p_a.name:<10} : {ints[0]}\n"
                                     f"  {p_b.name:<10} : {ints[1]}")
                
                self.lbl_info.setText(res_text)
                
            # --- TERNARY MODE ---
            else:
                uid_c = self.cb_comp_c.currentData()
                p_c = self._get_comp(uid_c)
                
                if not p_c or len({uid_a, uid_b, uid_c}) < 3:
                    self.lbl_info.setText("Error: Select 3 distinct compositions.")
                    return

                is_inv = self.project.is_inverted if self.project else True

                try:
                    # ВАЖНО: Используем bary_to_cart (с нормализацией), а не _raw!
                    # Это гарантирует, что расчетный треугольник совпадает с нарисованным.
                    pt_a = math_utils.bary_to_cart(p_a.composition, is_inv)
                    pt_b = math_utils.bary_to_cart(p_b.composition, is_inv)
                    pt_c = math_utils.bary_to_cart(p_c.composition, is_inv)
                    pt_t = math_utils.bary_to_cart(comp, is_inv)
                except CompositionError:
                    self.lbl_info.setText("Error: One of the basis compositions is invalid (sum=0).")
                    return

                # 2. Считаем веса (геометрически по экранным координатам)
                # pt_a[0] это X, pt_a[1] это Y
                u, v, w = math_utils.get_barycentric_from_cartesian(
                    float(pt_a[0]), float(pt_a[1]), 
                    float(pt_b[0]), float(pt_b[1]), 
                    float(pt_c[0]), float(pt_c[1]), 
                    float(pt_t[0]), float(pt_t[1])
                )
                
                # 3. Строгая проверка границ
                # Точка внутри, только если 0 <= u,v,w <= 1
                # Добавляем epsilon для точности float
                eps = 1e-3
                is_inside = (
                    -eps <= u <= 1.0 + eps and
                    -eps <= v <= 1.0 + eps and
                    -eps <= w <= 1.0 + eps
                )

                if not is_inside:
                    self.lbl_info.setText("Point is OUTSIDE the selected triangle.")
                    self.lbl_info.setStyleSheet("color: #D8000C; background-color: #FFBABA; padding: 10px; border-radius: 4px;")
                    return
                
                # Если внутри - красим в обычный цвет
                self.lbl_info.setStyleSheet(self.default_style)

                res_text = (f"Basis Fractions (Inside Triangle):\n"
                            f"  {p_a.name:<10} : {u*100:.2f}%\n"
                            f"  {p_b.name:<10} : {v*100:.2f}%\n"
                            f"  {p_c.name:<10} : {w*100:.2f}%")
                
                if not is_mouse_source:
                    ints = self._find_integer_ratio([u, v, w])
                    if ints:
                        res_text += (f"\n\nStoichiometry (Ratio):\n"
                                     f"  {p_a.name:<10} : {ints[0]}\n"
                                     f"  {p_b.name:<10} : {ints[1]}\n"
                                     f"  {p_c.name:<10} : {ints[2]}")
                
                self.lbl_info.setText(res_text)

        except (CompositionError, ValueError, ZeroDivisionError) as e:
            self.lbl_info.setText(f"Calculation Error: {str(e)}")
            self.lbl_info.setStyleSheet("color: red;")

    def get_overlay_data(self) -> RenderOverlay:
        # Создаем пустой объект
        overlay = RenderOverlay()
        
        if not self.isVisible():
            return overlay
        
        # --- 1. ОПРЕДЕЛЯЕМ ЦЕЛЕВУЮ ТОЧКУ (Синий маркер) ---
        # Если выбран ручной ввод или существующая точка, сразу ставим маркер
        idx = self.cb_target_source.currentIndex()
        
        if idx == 1: # Existing Composition
            uid = self.cb_target_comp.currentData()
            p = self._get_comp(uid)
            if p:
                overlay.projection_point = p.composition
                
        elif idx == 2: # Manual Input
            # Берем значения из спинбоксов
            c = Composition(self.sp_a.value(), self.sp_b.value(), self.sp_c.value())
            # Рисуем только если точка валидна (не 0,0,0)
            if c.total > 1e-9:
                overlay.projection_point = c

        # --- 2. ОТРИСОВКА БАЗИСА ---
        uid_a = self.cb_comp_a.currentData()
        uid_b = self.cb_comp_b.currentData()
        
        # --- LINEAR MODE ---
        if self.rb_linear.isChecked():
            if uid_a and uid_b and uid_a != uid_b:
                p_a_obj = self._get_comp(uid_a)
                p_b_obj = self._get_comp(uid_b)
                
                if p_a_obj and p_b_obj:
                    p1 = p_a_obj.composition
                    p2 = p_b_obj.composition
                    
                    # 1. Основная линия базиса (серая, пунктир)
                    overlay.extrap_lines.append(
                        OverlayLine(start=p1, end=p2, color="gray", style="--", highlight=True)
                    )
                    
                    # 2. Спец. логика для КУРСОРА (idx == 0)
                    # В этом случае мы переписываем projection_point на проекцию
                    if idx == 0:
                        cursor_comp = self._last_cursor_comp
                        is_inv = self.project.is_inverted if self.project else True
                        
                        proj_comp = math_utils.get_closest_composition_on_segment(
                            p1, p2, cursor_comp, is_inv
                        )
                        
                        # Линия от курсора к проекции
                        overlay.extrap_lines.append(
                            OverlayLine(start=cursor_comp, end=proj_comp, color="blue", style=":")
                        )
                        
                        # Точка на базисе (перезаписываем, даже если что-то было)
                        overlay.projection_point = proj_comp
                    
        # --- TERNARY MODE ---
        else:
            uid_c = self.cb_comp_c.currentData()
            # Для тройной системы просто рисуем треугольник + точку (которая задана в блоке 1)
            if uid_a and uid_b and uid_c and len({uid_a, uid_b, uid_c}) == 3:
                p_a_obj = self._get_comp(uid_a)
                p_b_obj = self._get_comp(uid_b)
                p_c_obj = self._get_comp(uid_c)
                
                if p_a_obj and p_b_obj and p_c_obj:
                    overlay.triangle_overlay = [p_a_obj.composition, p_b_obj.composition, p_c_obj.composition]
                 
        return overlay

    def _get_comp(self, uid: str) -> Optional[NamedComposition]:
        if not self.project:
            return None
        # Поиск состава по uid в compositions
        for comp in self.project.compositions:
            if comp.uid == uid:
                return comp
        return None

    def _emit_update_req(self):
        self.update_needed.emit()
