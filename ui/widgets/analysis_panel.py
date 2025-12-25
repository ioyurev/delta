from PySide6.QtWidgets import (QWidget, QVBoxLayout, QGroupBox, QLabel, 
                               QComboBox, QFormLayout, QRadioButton, QButtonGroup, 
                               QHBoxLayout, QTableWidget, 
                               QTableWidgetItem, QHeaderView, QApplication)
from PySide6.QtCore import Qt, Signal, QTimer
from PySide6.QtGui import QColor, QBrush
from delta.models import Composition, RenderOverlay, OverlayLine, NamedComposition, CompositionError
from delta import math_utils
from delta.exceptions import DegenerateBasisError, DegenerateTriangleError
from delta.constants import (
    EPSILON_ZERO,
    EPSILON_SEGMENT,
    TOLERANCE_ON_LINE_STRICT,
    DISPLAY_DECIMALS_ANALYSIS,
    COORD_INPUT_MIN,
    COORD_INPUT_MAX,
    NORMALIZATION_WARNING_THRESHOLD,
)
from typing import Optional, TYPE_CHECKING
import math

if TYPE_CHECKING:
    from delta.project_controller import ProjectController
from ui.widgets.helpers import populate_combo, STYLE_MESSAGE_WARNING, STYLE_MESSAGE_ERROR, get_message_style


def _get_error_color() -> QColor:
    """Возвращает цвет ошибки (копия логики из таблицы)"""
    palette = QApplication.palette()
    base = palette.base().color()
    if base.lightness() < 128:
        return QColor(100, 40, 40)
    return QColor(255, 200, 200)

def _get_normal_color() -> QColor:
    """Возвращает нормальный цвет фона"""
    return QApplication.palette().base().color()


class AnalysisPanel(QWidget):
    update_needed = Signal()
    overlay_changed = Signal()

    def __init__(self, controller: 'ProjectController'):
        super().__init__()
        self._controller = controller
        
        # Флаг для блокировки сигналов таблицы при программном изменении
        self._block_table_signals = False
        # Кэш предыдущих значений для отката [col] -> value
        self._manual_prev_values = {0: "0.0", 1: "0.0", 2: "0.0"}

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
        
        self.rb_linear.setToolTip("Calculate lever rule along a tie-line (2 compositions)")
        self.rb_ternary.setToolTip("Calculate fractions inside a triangle (3 compositions)")
        
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
        
        self.cb_comp_a.setToolTip("First basis composition (endpoint of tie-line)")
        self.cb_comp_b.setToolTip("Second basis composition (endpoint of tie-line)")
        self.cb_comp_c.setToolTip("Third basis composition (vertex of ternary sub-triangle)")
        
        self.cb_comp_a.currentIndexChanged.connect(self._on_basis_changed)
        self.cb_comp_b.currentIndexChanged.connect(self._on_basis_changed)
        self.cb_comp_c.currentIndexChanged.connect(self._on_basis_changed)
        
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
        self.cb_target_source.setToolTip("Choose how to specify the target point")
        
        v_target.addWidget(self.cb_target_source)
        
        # === СТРАНИЦЫ ===
        
        # P0: Mouse Cursor
        self.page_cursor = QWidget()
        v_c = QVBoxLayout(self.page_cursor)
        v_c.setContentsMargins(0, 5, 0, 5)
        lbl_cursor = QLabel("Move mouse over the plot...")
        lbl_cursor.setAlignment(Qt.AlignmentFlag.AlignCenter)
        lbl_cursor.setStyleSheet("color: gray; font-style: italic;")
        v_c.addWidget(lbl_cursor)
        
        # P1: Existing Composition
        self.page_existing = QWidget()
        v_e = QVBoxLayout(self.page_existing)
        v_e.setContentsMargins(0, 5, 0, 5)
        self.cb_target_comp = QComboBox()
        self.cb_target_comp.currentIndexChanged.connect(self._on_calc_request)
        self.cb_target_comp.setToolTip("Select existing composition as target")
        v_e.addWidget(self.cb_target_comp)
        
        # P2: Manual Input (TABLE)
        self.page_manual = QWidget()
        v_m = QVBoxLayout(self.page_manual)
        v_m.setContentsMargins(0, 5, 0, 5)
        
        # Настройка таблицы
        self.table_manual = QTableWidget(1, 3)
        self.table_manual.setFixedHeight(60) # Высота одной строки + заголовок
        self.table_manual.verticalHeader().setVisible(False) # Скрываем номера строк
        self.table_manual.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        
        # Инициализация ячеек
        self._block_table_signals = True
        for col in range(3):
            item = QTableWidgetItem("0.000000")
            self.table_manual.setItem(0, col, item)
        self._block_table_signals = False
        
        self.table_manual.itemChanged.connect(self._on_manual_item_changed)
        self.table_manual.setToolTip(
            "Enter molar fractions (or any proportional values).\n"
            "Values are automatically normalized so that sum = 1.\n"
            "Example: entering 1, 2, 3 gives 0.167, 0.333, 0.500"
        )
        
        v_m.addWidget(self.table_manual)
        
        self.lbl_sum_warning = QLabel("Norm: 0.000 : 0.000 : 0.000")
        self.lbl_sum_warning.setAlignment(Qt.AlignmentFlag.AlignRight)
        v_m.addWidget(self.lbl_sum_warning)
        
        # Добавляем все страницы
        v_target.addWidget(self.page_cursor)
        v_target.addWidget(self.page_existing)
        v_target.addWidget(self.page_manual)
        
        gb_target.setLayout(v_target)
        layout.addWidget(gb_target)
        
        # --- 4. Result ---
        self.lbl_info = QLabel("Result...")
        self.lbl_info.setWordWrap(True)
        self.lbl_info.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        
        self.lbl_info.setStyleSheet(self._get_default_style())
        
        layout.addWidget(self.lbl_info)
        layout.addStretch()
        
        self._last_cursor_comp = Composition(a=0,b=0,c=0)
        self._on_source_changed()

    def update_view(self):
        # Обновляем комбобоксы
        comp_combos = [
            self.cb_comp_a,
            self.cb_comp_b, 
            self.cb_comp_c,
            self.cb_target_comp
        ]
        self._populate_comp_combos(comp_combos)
        
        # Обновляем заголовки таблицы (компоненты)
        comps = self._controller.get_components()
        self.table_manual.setHorizontalHeaderLabels(comps)

    def _on_manual_item_changed(self, item: QTableWidgetItem):
        """Логика валидации таблицы (1-в-1 как в CompositionsTable)"""
        if self._block_table_signals:
            return
            
        col = item.column()
        txt = item.text().strip()
        
        try:
            val = float(txt.replace(',', '.'))
        except ValueError:
            prev = self._manual_prev_values.get(col, "0.0")
            self._flash_error(item)
            self._block_table_signals = True
            item.setText(prev)
            self._block_table_signals = False
            return
        
        # Clamping
        if val < COORD_INPUT_MIN:
            self._flash_error(item)
            val = COORD_INPUT_MIN
            self._block_table_signals = True
            item.setText(f"{COORD_INPUT_MIN:.6f}")
            self._block_table_signals = False
        elif val > COORD_INPUT_MAX:
            self._flash_error(item)
            val = COORD_INPUT_MAX
            self._block_table_signals = True
            item.setText(f"{COORD_INPUT_MAX:.6f}")
            self._block_table_signals = False
            
        # Обновляем кэш
        self._manual_prev_values[col] = item.text()
        
        # Проверяем сумму и запускаем расчет
        self._check_manual_sum()
        self._on_calc_request()

    def _flash_error(self, item: QTableWidgetItem):
        """Мигает красным фоном"""
        item.setBackground(QBrush(_get_error_color()))
        QTimer.singleShot(1000, lambda: self._reset_cell_bg(item))

    def _reset_cell_bg(self, item: QTableWidgetItem):
        try:
            item.setBackground(QBrush(_get_normal_color()))
        except RuntimeError:
            pass

    def _get_manual_value(self, col: int) -> float:
        """Безопасно получает float из ячейки"""
        item = self.table_manual.item(0, col)
        if not item:
            return 0.0
        try:
            return float(item.text().replace(',', '.'))
        except ValueError:
            return 0.0

    def _check_manual_sum(self):
        val_a = self._get_manual_value(0)
        val_b = self._get_manual_value(1)
        val_c = self._get_manual_value(2)
        
        total = math.fsum([val_a, val_b, val_c])
        d = DISPLAY_DECIMALS_ANALYSIS
        
        if total < EPSILON_ZERO:
            self.lbl_sum_warning.setText("⚠ Sum ≈ 0 — cannot normalize")
            self.lbl_sum_warning.setStyleSheet("color: red; font-weight: bold;")
            return
        
        nA = val_a / total
        nB = val_b / total
        nC = val_c / total
        
        # Разное оформление в зависимости от того, нужна ли нормализация
        if abs(total - 1.0) > NORMALIZATION_WARNING_THRESHOLD:
            # Сумма отличается от 1 — показываем предупреждение
            self.lbl_sum_warning.setText(
                f"⚠ Sum = {total:.{d}f} → Will use: {nA:.{d}f} : {nB:.{d}f} : {nC:.{d}f}"
            )
            self.lbl_sum_warning.setStyleSheet("color: #856404; background-color: #fff3cd; padding: 2px 4px; border-radius: 2px;")
        else:
            # Сумма ≈ 1 — всё нормально
            self.lbl_sum_warning.setText(
                f"✓ Normalized: {nA:.{d}f} : {nB:.{d}f} : {nC:.{d}f}"
            )
            self.lbl_sum_warning.setStyleSheet("color: #155724; background-color: #d4edda; padding: 2px 4px; border-radius: 2px;")

    def _populate_comp_combos(self, combos: list[QComboBox]) -> None:
        sorted_comps = sorted(self._controller.get_all_compositions(), key=lambda p: p.name)
        for cb in combos:
            populate_combo(
                cb,
                sorted_comps,
                get_text=lambda p: p.name or "[Unnamed]",
                get_data=lambda p: p.uid
            )

    def _on_settings_changed(self):
        is_ternary = self.rb_ternary.isChecked()
        self.cb_comp_c.setVisible(is_ternary)
        self.lbl_c.setVisible(is_ternary)
        
        # Проверяем валидность базиса при переключении в Ternary
        if is_ternary:
            self._validate_ternary_basis()
        
        self._emit_update_req()
        self._on_calc_request()

    def _on_source_changed(self):
        idx = self.cb_target_source.currentIndex()
        self.page_cursor.setVisible(idx == 0)
        self.page_existing.setVisible(idx == 1)
        self.page_manual.setVisible(idx == 2)
        self._on_calc_request()

    def on_cursor_move(self, comp: Composition):
        self._last_cursor_comp = comp
        if self.cb_target_source.currentIndex() == 0:
            self._calculate_and_display(comp)
            self.overlay_changed.emit()

    def _on_calc_request(self, value: Optional[float] = None):
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
            a = self._get_manual_value(0)
            b = self._get_manual_value(1)
            c = self._get_manual_value(2)
            target_comp = Composition(a=a, b=b, c=c)
            if target_comp.total < EPSILON_ZERO:
                self.lbl_info.setText("Invalid composition (Sum ≈ 0)")
                self.lbl_info.setStyleSheet("color: red;")
                return
                
        if target_comp:
            self._calculate_and_display(target_comp)
            self._emit_update_req()

    def _calculate_and_display(self, comp: Composition):
        if comp.total < EPSILON_ZERO:
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
                    self.lbl_info.setStyleSheet(self._get_default_style())
                    return
                
                if not is_mouse_source:
                    if not math_utils.is_point_on_line(p_a.composition, p_b.composition, comp, tol=TOLERANCE_ON_LINE_STRICT):
                        self.lbl_info.setText("Error: Point is NOT on the selected line.")
                        self.lbl_info.setStyleSheet("color: #D8000C; background-color: #FFBABA; padding: 10px; border-radius: 4px;")
                        return

                try:
                    t = math_utils.get_lever_fraction(p_a.composition, p_b.composition, comp)
                except DegenerateBasisError as e:
                    self.lbl_info.setText(f"Error: {e.reason}")
                    self.lbl_info.setStyleSheet("color: #D8000C; background-color: #FFBABA; padding: 10px; border-radius: 4px;")
                    return
                
                if t < -EPSILON_SEGMENT or t > (1.0 + EPSILON_SEGMENT):
                    self.lbl_info.setText("Error: Point is OUTSIDE the segment.")
                    self.lbl_info.setStyleSheet("color: #D8000C; background-color: #FFBABA; padding: 10px; border-radius: 4px;")
                    return
                else:
                    self.lbl_info.setStyleSheet(self._get_default_style())

                val_a = 1.0 - t
                val_b = t
                
                d = DISPLAY_DECIMALS_ANALYSIS
                res_text = (
                    f"Lever Rule (mol.%):\n"
                    f"  {p_a.name:<10} : {val_a*100:.{d}f}%\n"
                    f"  {p_b.name:<10} : {val_b*100:.{d}f}%\n"
                    f"  {'─' * 20}\n"
                    f"  {'Total':<10} : {(val_a + val_b)*100:.{d}f}%"
                )
                
                if not is_mouse_source:
                    ints = math_utils.find_integer_ratio([val_a, val_b])
                    if ints:
                        res_text += (f"\n\nStoichiometry (molar ratio):\n"
                                     f"  {p_a.name:<10} : {ints[0]}\n"
                                     f"  {p_b.name:<10} : {ints[1]}")
                
                self.lbl_info.setText(res_text)
                
            # --- TERNARY MODE ---
            else:
                uid_c = self.cb_comp_c.currentData()
                p_c = self._get_comp(uid_c)
                
                if not p_c or len({uid_a, uid_b, uid_c}) < 3:
                    self.lbl_info.setText("Error: Select 3 distinct compositions.")
                    self.lbl_info.setStyleSheet(STYLE_MESSAGE_ERROR)
                    return
                
                # Проверка коллинеарности перед расчётом
                if math_utils.are_compositions_collinear(
                    p_a.composition, p_b.composition, p_c.composition
                ):
                    self.lbl_info.setText(
                        "Error: Compositions are collinear.\n"
                        "Cannot calculate fractions for degenerate triangle."
                    )
                    self.lbl_info.setStyleSheet(STYLE_MESSAGE_ERROR)
                    return

                is_inv = self._controller.is_inverted()

                try:
                    pt_a = math_utils.bary_to_cart(p_a.composition, is_inv)
                    pt_b = math_utils.bary_to_cart(p_b.composition, is_inv)
                    pt_c = math_utils.bary_to_cart(p_c.composition, is_inv)
                    pt_t = math_utils.bary_to_cart(comp, is_inv)
                except CompositionError:
                    self.lbl_info.setText("Error: One of the basis compositions is invalid (sum=0).")
                    return

                try:
                    u, v, w = math_utils.get_barycentric_from_cartesian(
                        float(pt_a[0]), float(pt_a[1]), 
                        float(pt_b[0]), float(pt_b[1]), 
                        float(pt_c[0]), float(pt_c[1]), 
                        float(pt_t[0]), float(pt_t[1])
                    )
                except DegenerateTriangleError as e:
                    self.lbl_info.setText(f"Error: {e.reason}")
                    self.lbl_info.setStyleSheet("color: #D8000C; background-color: #FFBABA; padding: 10px; border-radius: 4px;")
                    return
                
                is_inside = (
                    -EPSILON_SEGMENT <= u <= 1.0 + EPSILON_SEGMENT and
                    -EPSILON_SEGMENT <= v <= 1.0 + EPSILON_SEGMENT and
                    -EPSILON_SEGMENT <= w <= 1.0 + EPSILON_SEGMENT
                )

                if not is_inside:
                    self.lbl_info.setText("Point is OUTSIDE the selected triangle.")
                    self.lbl_info.setStyleSheet("color: #D8000C; background-color: #FFBABA; padding: 10px; border-radius: 4px;")
                    return
                
                self.lbl_info.setStyleSheet(self._get_default_style())

                d = DISPLAY_DECIMALS_ANALYSIS
                total = u + v + w
                res_text = (
                    f"Basis Fractions (mol.%):\n"
                    f"  {p_a.name:<10} : {u*100:.{d}f}%\n"
                    f"  {p_b.name:<10} : {v*100:.{d}f}%\n"
                    f"  {p_c.name:<10} : {w*100:.{d}f}%\n"
                    f"  {'─' * 20}\n"
                    f"  {'Total':<10} : {total*100:.{d}f}%"
                )
                
                if not is_mouse_source:
                    ints = math_utils.find_integer_ratio([u, v, w])
                    if ints:
                        res_text += (f"\n\nStoichiometry (molar ratio):\n"
                                     f"  {p_a.name:<10} : {ints[0]}\n"
                                     f"  {p_b.name:<10} : {ints[1]}\n"
                                     f"  {p_c.name:<10} : {ints[2]}")
                
                self.lbl_info.setText(res_text)

        except (CompositionError, ValueError, ZeroDivisionError, DegenerateBasisError, DegenerateTriangleError) as e:
            self.lbl_info.setText(f"Calculation Error: {str(e)}")
            self.lbl_info.setStyleSheet("color: #D8000C; background-color: #FFBABA; padding: 10px; border-radius: 4px;")

    def get_overlay_data(self) -> RenderOverlay:
        overlay = RenderOverlay()
        
        if not self.isVisible():
            return overlay
        
        idx = self.cb_target_source.currentIndex()
        
        if idx == 1: 
            uid = self.cb_target_comp.currentData()
            p = self._get_comp(uid)
            if p:
                overlay.projection_point = p.composition
                
        elif idx == 2: 
            a = self._get_manual_value(0)
            b = self._get_manual_value(1)
            c = self._get_manual_value(2)
            c_obj = Composition(a=a, b=b, c=c)
            if c_obj.total > 1e-9:
                overlay.projection_point = c_obj

        uid_a = self.cb_comp_a.currentData()
        uid_b = self.cb_comp_b.currentData()
        
        if self.rb_linear.isChecked():
            if uid_a and uid_b and uid_a != uid_b:
                p_a_obj = self._get_comp(uid_a)
                p_b_obj = self._get_comp(uid_b)
                
                if p_a_obj and p_b_obj:
                    p1 = p_a_obj.composition
                    p2 = p_b_obj.composition
                    
                    overlay.extrap_lines.append(
                        OverlayLine(start=p1, end=p2, color="gray", style="--", highlight=True)
                    )
                    
                    if idx == 0:
                        cursor_comp = self._last_cursor_comp
                        is_inv = self._controller.is_inverted()
                        
                        proj_comp = math_utils.get_closest_composition_on_segment(
                            p1, p2, cursor_comp, is_inv
                        )
                        
                        overlay.extrap_lines.append(
                            OverlayLine(start=cursor_comp, end=proj_comp, color="blue", style=":")
                        )
                        overlay.projection_point = proj_comp
                    
        else:
            uid_c = self.cb_comp_c.currentData()
            if uid_a and uid_b and uid_c and len({uid_a, uid_b, uid_c}) == 3:
                p_a_obj = self._get_comp(uid_a)
                p_b_obj = self._get_comp(uid_b)
                p_c_obj = self._get_comp(uid_c)
                
                if p_a_obj and p_b_obj and p_c_obj:
                    overlay.triangle_overlay = [p_a_obj.composition, p_b_obj.composition, p_c_obj.composition]
                 
        return overlay

    def _get_comp(self, uid: str) -> Optional[NamedComposition]:
        return self._controller.find_composition(uid)

    def _check_ternary_basis_validity(self) -> tuple[bool, str]:
        """
        Проверяет валидность базиса для Ternary режима.
        
        Returns:
            (is_valid, message)
        """
        uid_a = self.cb_comp_a.currentData()
        uid_b = self.cb_comp_b.currentData()
        uid_c = self.cb_comp_c.currentData()
        
        # Проверка: выбраны три разные точки
        if not uid_a or not uid_b or not uid_c:
            return False, "Select all three basis compositions"
        
        if len({uid_a, uid_b, uid_c}) < 3:
            return False, "Select three different compositions"
        
        # Получаем составы
        p_a = self._get_comp(uid_a)
        p_b = self._get_comp(uid_b)
        p_c = self._get_comp(uid_c)
        
        if not p_a or not p_b or not p_c:
            return False, "One or more compositions not found"
        
        # Проверка коллинеарности
        if math_utils.are_compositions_collinear(
            p_a.composition, p_b.composition, p_c.composition
        ):
            return False, (
                "Selected compositions are collinear (lie on a line).\n"
                "Choose three non-collinear points to form a valid triangle."
            )
        
        # Проверка площади (дополнительно — для маленьких треугольников)
        area = math_utils.get_triangle_area(
            p_a.composition, p_b.composition, p_c.composition
        )
        
        if area < 0.001:  # Очень маленький треугольник
            return True, (
                f"Warning: Very small triangle (area = {area:.4f}).\n"
                "Results may have reduced precision."
            )
        
        return True, ""

    def _validate_ternary_basis(self):
        """Проверяет и показывает статус базиса для Ternary режима"""
        is_valid, message = self._check_ternary_basis_validity()
        
        if not is_valid:
            self.lbl_info.setText(f"⚠ {message}")
            self.lbl_info.setStyleSheet(STYLE_MESSAGE_WARNING)
        elif message:  # Warning (маленький треугольник)
            self.lbl_info.setText(message)
            self.lbl_info.setStyleSheet(STYLE_MESSAGE_WARNING)

    def _on_basis_changed(self):
        """Обработчик изменения базисных точек"""
        # Проверяем валидность в Ternary режиме
        if self.rb_ternary.isChecked():
            self._validate_ternary_basis()
        
        self._on_calc_request()

    def _get_default_style(self) -> str:
        """Возвращает адаптивный стиль для основного окна результатов"""
        return get_message_style("default")

    def _emit_update_req(self):
        self.update_needed.emit()
