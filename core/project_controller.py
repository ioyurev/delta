from typing import Optional, List, Dict
import copy
from PySide6.QtCore import QObject, Signal
from core.models import ProjectData, NamedComposition, TieLine, Composition, CompositionUpdate, StyleUpdate, IntersectionResult, RenderOverlay, OverlayLine
from core import math_utils
from core.constants import EPSILON_BOUNDARY
from core.serializer import ProjectSerializer
from core.exceptions import EntityNotFoundError, DuplicateEntityError, ValidationError
from loguru import logger

MAX_UNDO_STACK_SIZE = 50

class ProjectController(QObject):
    data_changed = Signal()  # Испускается при любой мутации данных
    
    def __init__(self):
        super().__init__()
        self._project = ProjectData()  # PRIVATE: Use public methods or project_data property
        
        # --- КЭШИ ДЛЯ O(1) ДОСТУПА ---
        # Синхронизируются со списками в _project
        self._comp_map: Dict[str, NamedComposition] = {}
        self._line_map: Dict[str, TieLine] = {}
        
        # --- РЕЖИМ ПАКЕТНОЙ ОБРАБОТКИ ---
        # Подавляет сигналы при каскадных операциях
        self._batch_mode = False
        
        # --- Undo/Redo стеки ---
        self._undo_stack: list[ProjectData] = []
        self._redo_stack: list[ProjectData] = []

    def _rebuild_cache(self):
        """Пересоздает карты быстрого доступа на основе списков"""
        self._comp_map = {comp.uid: comp for comp in self._project.compositions}
        self._line_map = {line.uid: line for line in self._project.lines}

    # ========== ПУБЛИЧНЫЙ API (только методы) ==========
    
    def has_compositions(self) -> bool:
        """Проверка наличия составов (вместо прямого доступа к списку)"""
        return len(self._project.compositions) > 0
    
    def get_composition_count(self) -> int:
        """Количество составов"""
        return len(self._project.compositions)
    
    def get_line_count(self) -> int:
        """Количество линий"""
        return len(self._project.lines)
    
    def get_components(self) -> List[str]:
        """Возвращает КОПИЮ списка компонентов"""
        return list(self._project.components)
    
    def is_inverted(self) -> bool:
        """Режим треугольника"""
        return self._project.is_inverted

    # --- 1. Публичное свойство для "Чтения" состояния (для Canvas и Table) ---
    @property
    def project_data(self) -> ProjectData:
        """
        Returns project data for READ-ONLY operations (rendering, display).
        
        DO NOT modify the returned object directly!
        Use controller methods for any mutations:
          - create_composition(), update_composition(), delete_composition()
          - create_line(), update_line_style(), delete_line()
          - update_components(), update_grid(), update_view_mode()
        
        For O(1) lookups, use:
          - get_composition(uid)
          - get_line(uid)
        """
        return self._project

    # --- 2. Методы поиска (Lookups) ---
    
    def get_composition(self, uid: str) -> NamedComposition:
        """
        Возвращает состав по UID.
        
        Raises:
            EntityNotFoundError: если состав не найден
        """
        comp = self._comp_map.get(uid)
        if comp is None:
            raise EntityNotFoundError("Composition", uid)
        return comp

    def find_composition(self, uid: str) -> Optional[NamedComposition]:
        """Мягкий поиск — возвращает None если не найден (для UI)"""
        return self._comp_map.get(uid)

    def get_line(self, uid: str) -> TieLine:
        """
        Возвращает линию по UID.
        
        Raises:
            EntityNotFoundError: если линия не найдена
        """
        line = self._line_map.get(uid)
        if line is None:
            raise EntityNotFoundError("Line", uid)
        return line

    def find_line(self, uid: str) -> Optional[TieLine]:
        """Мягкий поиск — возвращает None если не найден (для UI)"""
        return self._line_map.get(uid)
        
    def get_line_endpoints(self, line_uid: str) -> tuple[NamedComposition, NamedComposition]:
        """
        Возвращает составы (начало, конец) для линии.
        Убирает логику поиска из UI.
        
        Raises:
            EntityNotFoundError: если линия или один из составов не найден
        """
        line = self.get_line(line_uid)
        start_comp = self.get_composition(line.start_uid)
        end_comp = self.get_composition(line.end_uid)
        return start_comp, end_comp

    def get_all_compositions(self) -> List[NamedComposition]:
        """Возвращает список всех составов"""
        return self._project.compositions

    def get_all_lines(self) -> List[TieLine]:
        """Возвращает список всех линий"""
        return self._project.lines
    
    # ========== МУТАЦИИ (изменения только здесь) ==========
    
    def create_composition(self, name: str = "New", a: float = 0.0, b: float = 0.0, c: float = 0.0,
                           show_label: bool = True,
                           show_marker: bool = True
                           ) -> str:
        """
        Создаёт состав и возвращает его UID.
        Не возвращает сам объект NamedComposition!
        """
        comp = NamedComposition(
            name=name,
            composition=Composition(a, b, c)
        )
        # Применяем настройку видимости метки
        comp.style.show_label = show_label
        comp.style.show_marker = show_marker
        
        # 1. Добавляем в список (для порядка и сохранения)
        self._project.compositions.append(comp)
        # 2. Добавляем в кэш (для скорости)
        self._comp_map[comp.uid] = comp
        # bind добавляет контекст к логу (удобно для фильтрации)
        logger.bind(uid=comp.uid).info(f"Created composition '{name}'")
        self._notify_change()
        return comp.uid

    def create_line(self, start_uid: str, end_uid: str) -> str:
        """
        Создаёт линию между двумя составами.
        
        Returns:
            UID созданной линии
            
        Raises:
            ValidationError: если start_uid == end_uid
            DuplicateEntityError: если такая линия уже существует
            EntityNotFoundError: если один из составов не найден
        """
        # Валидация
        if start_uid == end_uid:
            raise ValidationError("Cannot create line: start and end must be different")
        
        # Проверяем существование составов (выбросит EntityNotFoundError)
        self.get_composition(start_uid)
        self.get_composition(end_uid)
        
        # Проверка на дубликат
        for line in self._project.lines:
            if {line.start_uid, line.end_uid} == {start_uid, end_uid}:
                raise DuplicateEntityError(f"Line between {start_uid} and {end_uid} already exists")
        
        line = TieLine(start_uid=start_uid, end_uid=end_uid)
        self._project.lines.append(line)
        self._line_map[line.uid] = line
        
        logger.bind(uid=line.uid).info(f"Created line {start_uid} -> {end_uid}")
        self._notify_change()
        return line.uid

    def update_components(self, names: List[str]):
        if len(names) == 3:
            self._project.components = names
            self._notify_change()

    def update_grid(self, visible: bool, step: float):
        self._project.grid.visible = visible
        self._project.grid.step = step
        self._notify_change()

    def update_composition_style(self, uid: str, update: StyleUpdate) -> None:
        """
        Обновляет визуальный стиль конкретного состава.
        
        Raises:
            EntityNotFoundError: если состав не найден
        """
        comp = self.get_composition(uid)
        update.apply_to(comp.style)
        self._notify_change()

    def update_view_mode(self, is_inverted: bool):
        """
        Переключает режим треугольника.
        Смещения меток (label_offset) не зависят от инверсии, они относительны.
        """
        if self._project.is_inverted == is_inverted:
            return
        self._project.is_inverted = is_inverted
        self._notify_change()

    def update_composition(self, uid: str, update: CompositionUpdate) -> None:
        """
        Обновляет состав, используя DTO.
        
        Raises:
            EntityNotFoundError: если состав не найден
        """
        comp = self.get_composition(uid)
        update.apply_to(comp)
        self._notify_change()

    def delete_composition(self, uid: str) -> str:
        """
        Удаляет состав и связанные линии.
        Возвращает имя удалённого состава для обратной связи.
        
        Raises:
            EntityNotFoundError: если состав не найден
        """
        comp = self.get_composition(uid)
        deleted_name = comp.name or "Unnamed"
        
        logger.info(f"Deleting composition: {uid}")
        
        # Включаем режим пакетной обработки для подавления сигналов
        old_batch_mode = self._batch_mode
        self._batch_mode = True
        
        try:
            # Удаляем из кэша и списка
            del self._comp_map[uid]
            self._project.compositions = [p for p in self._project.compositions if p.uid != uid]
            
            # Каскадное удаление линий без уведомлений
            lines_to_remove = [line.uid for line in self._project.lines 
                               if line.start_uid == uid or line.end_uid == uid]
            
            for line_uid in lines_to_remove:
                if line_uid in self._line_map:
                    del self._line_map[line_uid]
            
            self._project.lines = [line for line in self._project.lines if line.uid not in lines_to_remove]
            
        finally:
            # Восстанавливаем предыдущий режим
            self._batch_mode = old_batch_mode
            
        # Один финальный сигнал
        self._notify_change()
        
        return deleted_name

    def _save_undo_state(self) -> None:
        """Сохраняет текущее состояние в стек отмены"""
        self._undo_stack.append(copy.deepcopy(self._project))
        self._redo_stack.clear()
        
        # Ограничиваем размер стека
        if len(self._undo_stack) > MAX_UNDO_STACK_SIZE:
            self._undo_stack.pop(0)

    def _notify_change(self, save_undo: bool = True) -> None:
        """Уведомляет подписчиков об изменении данных"""
        if not self._batch_mode:
            if save_undo:
                self._save_undo_state()
            self.data_changed.emit()

    # ========== ПРИВАТНЫЕ МЕТОДЫ ==========
    
    def set_composition_label_pos(self, uid: str, x: float, y: float) -> None:
        """
        Принимает абсолютные координаты (x, y), куда пользователь перетащил метку.
        Вычисляет и сохраняет смещение (offset) относительно точки состава.
        
        Raises:
            EntityNotFoundError: если состав не найден
            ValidationError: если координаты недопустимы
        """
        comp = self.get_composition(uid)
        is_inv = self._project.is_inverted
        
        # Используем bary_to_cart (с нормализацией), а не raw!
        # Это гарантирует, что мы считаем отступ от той точки, которая реально на экране.
        try:
            pt = math_utils.bary_to_cart(comp.composition, is_inv)
        except ValueError as e:
            raise ValidationError(f"Invalid composition coordinates: {e}")

        # Приводим к float (важно для JSON сериализации и стабильности)
        dx = float(x - pt[0])
        dy = float(y - pt[1])
        
        comp.label_offset = (dx, dy)
        self._notify_change()

    # --- CRUD для Линий ---
    def update_line_style(self, uid: str, update: StyleUpdate) -> None:
        """
        Обновляет стиль линии.
        
        Raises:
            EntityNotFoundError: если линия не найдена
        """
        line = self.get_line(uid)
        update.apply_to(line.style)
        self._notify_change()

    def delete_line(self, uid: str) -> tuple[str, str]:
        """
        Удаляет линию.
        Возвращает имена составов (start_name, end_name) для обратной связи.
        
        Raises:
            EntityNotFoundError: если линия не найдена
        """
        line = self.get_line(uid)
        
        start_name = "?"
        end_name = "?"
        try:
            start_comp = self.get_composition(line.start_uid)
            end_comp = self.get_composition(line.end_uid)
            start_name = start_comp.name or "Unnamed"
            end_name = end_comp.name or "Unnamed"
        except EntityNotFoundError:
            pass
        
        del self._line_map[uid]
        self._project.lines = [line for line in self._project.lines if line.uid != uid]
        self._notify_change()
        
        return start_name, end_name

    def update_line_endpoints(self, line_uid: str, start_uid: str, end_uid: str) -> None:
        """
        Обновляет конечные точки существующей линии, не меняя её UID.
        
        Raises:
            ValidationError: если start == end или линия-дубликат
            EntityNotFoundError: если линия или составы не найдены
        """
        if start_uid == end_uid:
            raise ValidationError("Start and end must be different")
        
        # Проверка дубликата
        for line in self._project.lines:
            if line.uid != line_uid:
                if {line.start_uid, line.end_uid} == {start_uid, end_uid}:
                    raise DuplicateEntityError("Line with these endpoints already exists")
        
        line = self.get_line(line_uid)
        line.start_uid = start_uid
        line.end_uid = end_uid
        self._notify_change()

    def set_vertex_label_pos(self, index: int, x: float, y: float):
        """Сохраняет позицию метки вершины (0=A, 1=B, 2=C)"""
        self._project.vertex_labels_pos[str(index)] = (x, y)
        self._notify_change()

    # --- Сериализация ---
    def save_project(self, filepath: str) -> None:
        """
        Сохраняет проект.
        Raises: ProjectFileError если что-то пошло не так.
        """
        # Делегируем работу сериализатору
        ProjectSerializer.save_to_file(self._project, filepath)

    def new_project(self):
        """Сбрасывает проект к начальному состоянию"""
        self._project = ProjectData()
        self._rebuild_cache()
        self.clear_undo_history()
        logger.info("Project reset to new state")
        self._notify_change(save_undo=False)

    def load_project(self, filepath: str) -> None:
        """
        Загружает проект.
        Raises: ProjectFileError если что-то пошло не так.
        """
        # 1. Загружаем "чистые" данные
        new_project = ProjectSerializer.load_from_file(filepath)
        
        # 2. Применяем их
        self._project = new_project
        
        # 3. ВАЖНО: Перестраиваем кэш!
        # Без этой строки поиск по UID не будет работать для загруженных проектов
        self._rebuild_cache()
        self.clear_undo_history()

    def calculate_intersection(self, line1_uid: str, line2_uid: str, show_extrapolations: bool = True) -> IntersectionResult:
        """
        Рассчитывает пересечение двух линий и возвращает результат с готовым overlay.
        """
        overlay = RenderOverlay()
        result = IntersectionResult(overlay=overlay)
        
        # 1. Валидация входных данных
        if not line1_uid or not line2_uid or line1_uid == line2_uid:
            result.message = "Select two different lines."
            return result
            
        try:
            line1 = self.get_line(line1_uid)
            line2 = self.get_line(line2_uid)
            p1, p2 = self.get_line_endpoints(line1.uid)
            p3, p4 = self.get_line_endpoints(line2.uid)
        except EntityNotFoundError:
            result.message = "Invalid lines data."
            return result

        # 2. Подсветка и экстраполяция (визуал)
        overlay.highlight_lines_uids = [line1_uid, line2_uid]
        
        if show_extrapolations:
            # Используем вспомогательную функцию для экстраполяции
            self._add_extrapolations(overlay, p1.composition, p2.composition, line1.style.color)
            self._add_extrapolations(overlay, p3.composition, p4.composition, line2.style.color)

        # 3. Расчёт пересечения (математика)
        intersect = math_utils.solve_intersection(
            p1.composition, p2.composition, 
            p3.composition, p4.composition
        )
        
        if intersect:
            arr = intersect.normalized
            is_inside = all(x >= -EPSILON_BOUNDARY for x in arr)
            
            result.intersection = intersect
            result.is_inside = is_inside
            
            if is_inside:
                overlay.intersect_point = intersect
                names = self.get_components()
                result.message = (
                    f"Intersection found:\n"
                    f"{names[0]} = {intersect.a:.4f}\n"
                    f"{names[1]} = {intersect.b:.4f}\n"
                    f"{names[2]} = {intersect.c:.4f}"
                )
                result.status_style = "color: green; font-weight: bold; background: #e0f0e0; padding: 10px;"
            else:
                result.message = "Intersection is outside the triangle."
                result.status_style = "color: orange; font-weight: bold; background: #fff0e0; padding: 10px;"
        else:
            result.message = "Lines are parallel."
            result.status_style = "color: red; font-weight: bold; background: #ffe0e0; padding: 10px;"
            
        return result

    def _add_extrapolations(self, overlay: RenderOverlay, start: Composition, end: Composition, color: str):
        """Helper to add extrapolation lines to overlay"""
        intersections = math_utils.get_line_triangle_intersections(start, end)
        if len(intersections) == 2:
            overlay.extrap_lines.append(
                OverlayLine(start=intersections[0], end=intersections[1], color=color)
            )

    # ========== Undo/Redo МЕТОДЫ ==========

    def undo(self) -> bool:
        """
        Отменяет последнее действие.
        
        Returns:
            True если отмена выполнена, False если стек пуст
        """
        if not self._undo_stack:
            return False
        
        # Сохраняем текущее состояние для redo
        self._redo_stack.append(copy.deepcopy(self._project))
        
        # Восстанавливаем предыдущее
        self._project = self._undo_stack.pop()
        self._rebuild_cache()
        
        # Уведомляем без сохранения в undo
        self._notify_change(save_undo=False)
        
        logger.info(f"Undo performed. Stack size: {len(self._undo_stack)}")
        return True

    def redo(self) -> bool:
        """
        Повторяет отменённое действие.
        
        Returns:
            True если повтор выполнен, False если стек пуст
        """
        if not self._redo_stack:
            return False
        
        # Сохраняем текущее состояние для undo
        self._undo_stack.append(copy.deepcopy(self._project))
        
        # Восстанавливаем следующее
        self._project = self._redo_stack.pop()
        self._rebuild_cache()
        
        # Уведомляем без сохранения в undo
        self._notify_change(save_undo=False)
        
        logger.info(f"Redo performed. Stack size: {len(self._redo_stack)}")
        return True

    def can_undo(self) -> bool:
        """Проверяет возможность отмены"""
        return len(self._undo_stack) > 0

    def can_redo(self) -> bool:
        """Проверяет возможность повтора"""
        return len(self._redo_stack) > 0

    def clear_undo_history(self) -> None:
        """Очищает историю (при загрузке/создании проекта)"""
        self._undo_stack.clear()
        self._redo_stack.clear()
