from PySide6.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QFormLayout, 
                               QComboBox, QPushButton, QCheckBox, QLabel, QGroupBox)
from PySide6.QtCore import Signal
from core.models import RenderOverlay, Composition, TieLine, IntersectionStatus, OverlayLine, IntersectionResult
from core.project_controller import ProjectController
from core.exceptions import EntityNotFoundError, ValidationError
from core import math_utils
from core.constants import DISPLAY_DECIMALS_CURSOR
from ui.widgets.helpers import populate_combo, get_message_style
from typing import Optional

class IntersectionDialog(QDialog):
    """
    Диалог расчёта пересечения линий.
    
    Signals:
        overlay_changed(RenderOverlay): Испускается при изменении overlay для отрисовки
        intersection_found(Composition): Испускается при добавлении точки пересечения
    """
    
    # Стили результатов
    _STYLE_SUCCESS = "color: green; font-weight: bold; background: #e0f0e0; padding: 10px; border-radius: 4px;"
    _STYLE_WARNING = "color: orange; font-weight: bold; background: #fff0e0; padding: 10px; border-radius: 4px;"
    _STYLE_ERROR = "color: red; font-weight: bold; background: #ffe0e0; padding: 10px; border-radius: 4px;"
    _STYLE_DEFAULT = "font-weight: bold; padding: 10px; background: #f0f0f0; border-radius: 4px;"
    
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
        self.lbl_result.setStyleSheet(get_message_style("default"))
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
        """Пересчитывает пересечение и обновляет UI"""
        uid1 = self.cb_line1.currentData()
        uid2 = self.cb_line2.currentData()
        
        # Сброс состояния
        self.found_intersection = None
        self.btn_add.setEnabled(False)
        
        # Валидация на уровне UI
        if not uid1 or not uid2:
            self._show_result("Select two lines.", self._STYLE_DEFAULT)
            self._emit_overlay(RenderOverlay())
            return
        
        if uid1 == uid2:
            self._show_result("Select two different lines.", self._STYLE_DEFAULT)
            self._emit_overlay(RenderOverlay())
            return
        
        # Вызов контроллера (только данные)
        try:
            result = self._controller.calculate_intersection(uid1, uid2)
        except (EntityNotFoundError, ValidationError) as e:
            self._show_result(f"Error: {e}", self._STYLE_ERROR)
            self._emit_overlay(RenderOverlay())
            return
        
        # Построение overlay (UI-логика)
        overlay = self._build_overlay(result, uid1, uid2)
        
        # Форматирование результата (UI-логика)
        self._display_result(result)
        
        # Обновляем графику
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
    
    def _build_overlay(self, result: IntersectionResult, uid1: str, uid2: str) -> RenderOverlay:
        """Строит overlay для отображения на графике"""
        overlay = RenderOverlay()
        overlay.highlight_lines_uids = [uid1, uid2]
        
        # Экстраполяции
        if self.chk_extrap.isChecked():
            if result.line1_endpoints:
                start1, end1 = result.line1_endpoints
                self._add_extrapolation(overlay, start1, end1, uid1)
            if result.line2_endpoints:
                start2, end2 = result.line2_endpoints
                self._add_extrapolation(overlay, start2, end2, uid2)
        
        # Точка пересечения
        if result.status == IntersectionStatus.FOUND and result.intersection:
            overlay.intersect_point = result.intersection
        
        return overlay

    def _add_extrapolation(self, overlay: RenderOverlay, start: Composition, end: Composition, line_uid: str):
        """Добавляет линию экстраполяции до границ треугольника"""
        # Получаем цвет линии
        try:
            line = self._controller.get_line(line_uid)
            color = line.style.color
        except EntityNotFoundError:
            color = "gray"
        
        intersections = math_utils.get_line_triangle_intersections(start, end)
        if len(intersections) == 2:
            overlay.extrap_lines.append(
                OverlayLine(start=intersections[0], end=intersections[1], color=color)
            )

    def _display_result(self, result: IntersectionResult):
        """Форматирует и отображает результат"""
        if result.status == IntersectionStatus.FOUND:
            comp = result.intersection
            # Проверка на None перед доступом к атрибутам
            if comp is None:
                self._show_result("Intersection found but somehow composition is None.", self._STYLE_ERROR)
                return
                
            names = self._controller.get_components()
            d = DISPLAY_DECIMALS_CURSOR
            
            try:
                a, b, c = comp.normalized
                message = (
                    f"Intersection found:\n"
                    f"{names[0]} = {a:.{d}f}\n"
                    f"{names[1]} = {b:.{d}f}\n"
                    f"{names[2]} = {c:.{d}f}\n"
                    f"{'─' * 16}\n"
                    f"Σ = 1.0 (normalized)"
                )
            except Exception:
                message = (
                    f"Intersection found:\n"
                    f"{names[0]} = {comp.a:.{d}f}\n"
                    f"{names[1]} = {comp.b:.{d}f}\n"
                    f"{names[2]} = {comp.c:.{d}f}"
                )
            self._show_result(message, self._STYLE_SUCCESS)
            self.found_intersection = comp
            self.btn_add.setEnabled(True)
            
        elif result.status == IntersectionStatus.OUTSIDE:
            self._show_result("Intersection is outside the triangle.", self._STYLE_WARNING)
            
        elif result.status == IntersectionStatus.PARALLEL:
            self._show_result("Lines are parallel.", self._STYLE_ERROR)
            
        else:
            self._show_result("Invalid input.", self._STYLE_DEFAULT)

    def _show_result(self, message: str, style: str):
        """Устанавливает текст и стиль результата"""
        self.lbl_result.setText(message)
        self.lbl_result.setStyleSheet(style)

    def _on_close(self) -> None:
        """Обработчик закрытия — очищаем overlay"""
        self.overlay_changed.emit(RenderOverlay())  # Пустой overlay
        self.reject()
    
    def closeEvent(self, event) -> None:
        """Перехватываем закрытие окна (крестик)"""
        self.overlay_changed.emit(RenderOverlay())
        super().closeEvent(event)
