from typing import Optional, List, Dict
import copy
from PySide6.QtCore import QObject, Signal
from pydantic import ValidationError as PydanticValidationError
from core.models import ProjectData, NamedComposition, TieLine, Composition, CompositionUpdate, StyleUpdate, IntersectionResult, IntersectionStatus
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
                           show_marker: bool = True,
                           validate: bool = True
                           ) -> str:
        """
        Создаёт состав и возвращает его UID.
        
        Args:
            name: Имя состава
            a, b, c: Координаты
            show_label: Показывать текстовую метку
            show_marker: Показывать маркер
            validate: Проверять физическую валидность (default: True)
            
        Returns:
            UID созданного состава
            
        Raises:
            ValidationError: если validate=True и состав невалиден
        """
        try:
            composition = Composition(a=a, b=b, c=c)
            
            if validate and not composition.is_physically_valid:
                raise ValidationError(
                    f"Invalid composition: normalized values ({a}, {b}, {c}) "
                    f"must be non-negative. Check your input."
                )
            
            comp = NamedComposition(
                name=name,
                composition=composition
            )
        except PydanticValidationError as e:
            # Преобразуем ошибки Pydantic в ValidationError
            error_msg = e.errors()[0]['msg'] if e.errors() else "Invalid composition data"
            raise ValidationError(str(error_msg))
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
            ValidationError: если start_uid == end_uid или координаты совпадают
            DuplicateEntityError: если такая линия уже существует
            EntityNotFoundError: если один из составов не найден
        """
        # Валидация UID
        if start_uid == end_uid:
            raise ValidationError("Cannot create line: start and end must be different")
        
        # Получаем составы (выбросит EntityNotFoundError если не найден)
        start_comp = self.get_composition(start_uid)
        end_comp = self.get_composition(end_uid)
        
        # Проверка на совпадение координат (вырожденная линия)
        if start_comp.composition.normalized_is_close(end_comp.composition):
            raise ValidationError(
                f"Cannot create line: compositions '{start_comp.name}' and '{end_comp.name}' "
                f"have identical coordinates (zero-length tie-line)"
            )
        
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

    def update_composition(self, uid: str, update: CompositionUpdate, validate: bool = True) -> None:
        """
        Обновляет состав, используя DTO.
        
        Args:
            uid: Идентификатор состава
            update: DTO с изменениями
            validate: Проверять физическую валидность и вырожденные линии
            
        Raises:
            EntityNotFoundError: если состав не найден
            ValidationError: если validate=True и новые координаты невалидны или создают вырожденную линию
        """
        comp = self.get_composition(uid)
        
        if validate and update.has_coordinate_changes():
            new_a = update.a if update.a is not None else comp.composition.a
            new_b = update.b if update.b is not None else comp.composition.b
            new_c = update.c if update.c is not None else comp.composition.c
            
            try:
                new_composition = Composition(a=new_a, b=new_b, c=new_c)
                
                # Проверка физической валидности
                if not new_composition.is_physically_valid:
                    raise ValidationError(
                        "Invalid composition: values would result in negative molar fractions"
                    )
                
                # Проверка на вырожденные линии
                self._check_degenerate_lines(uid, new_composition)
            except PydanticValidationError as e:
                # Преобразуем ошибки Pydantic в ValidationError
                error_msg = e.errors()[0]['msg'] if e.errors() else "Invalid composition data"
                raise ValidationError(str(error_msg))
        
        update.apply_to(comp)
        self._notify_change()

    def _check_degenerate_lines(self, composition_uid: str, new_coords: Composition) -> None:
        """
        Проверяет, не станут ли связанные линии вырожденными после изменения координат.
        
        Raises:
            ValidationError: если изменение создаст вырожденную линию
        """
        for line in self._project.lines:
            other_uid = None
            
            if line.start_uid == composition_uid:
                other_uid = line.end_uid
            elif line.end_uid == composition_uid:
                other_uid = line.start_uid
            
            if other_uid:
                try:
                    other_comp = self.get_composition(other_uid)
                    if new_coords.normalized_is_close(other_comp.composition):
                        raise ValidationError(
                            f"Cannot update: would create zero-length line with '{other_comp.name}'"
                        )
                except EntityNotFoundError:
                    # Другой конец линии не существует — пропускаем
                    pass

    def delete_composition(self, uid: str) -> None:
        """
        Удаляет состав и связанные линии.
        
        Raises:
            EntityNotFoundError: если состав не найден
        """
        # Проверяем существование (выбросит EntityNotFoundError если нет)
        self.get_composition(uid)
        
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

    def delete_line(self, uid: str) -> None:
        """
        Удаляет линию.
        
        Raises:
            EntityNotFoundError: если линия не найдена
        """
        # Проверяем существование
        self.get_line(uid)
        
        del self._line_map[uid]
        self._project.lines = [line for line in self._project.lines if line.uid != uid]
        self._notify_change()

    def update_line_endpoints(self, line_uid: str, start_uid: str, end_uid: str) -> None:
        """
        Обновляет конечные точки существующей линии, не меняя её UID.
        
        Raises:
            ValidationError: если start == end, координаты совпадают, или линия-дубликат
            EntityNotFoundError: если линия или составы не найдены
        """
        if start_uid == end_uid:
            raise ValidationError("Start and end must be different")
        
        # Получаем составы для проверки координат
        start_comp = self.get_composition(start_uid)
        end_comp = self.get_composition(end_uid)
        
        # Проверка на совпадение координат
        if start_comp.composition.normalized_is_close(end_comp.composition):
            raise ValidationError(
                f"Cannot update line: compositions '{start_comp.name}' and '{end_comp.name}' "
                f"have identical coordinates"
            )
        
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

    def calculate_intersection(self, line1_uid: str, line2_uid: str) -> IntersectionResult:
        """
        Рассчитывает пересечение двух линий.
        
        Возвращает только данные. UI сам строит overlay и форматирует сообщения.
        
        Raises:
            EntityNotFoundError: если линия или состав не найден
            ValidationError: если line1_uid == line2_uid
        """
        if not line1_uid or not line2_uid:
            return IntersectionResult(status=IntersectionStatus.INVALID_INPUT)
        
        if line1_uid == line2_uid:
            raise ValidationError("Cannot intersect line with itself")
        
        # Получаем данные (исключения пробросятся наверх)
        p1, p2 = self.get_line_endpoints(line1_uid)
        p3, p4 = self.get_line_endpoints(line2_uid)
        
        # Сохраняем endpoints для UI (построение overlay)
        result = IntersectionResult(
            line1_endpoints=(p1.composition, p2.composition),
            line2_endpoints=(p3.composition, p4.composition),
        )
        
        # Расчёт пересечения
        intersect = math_utils.solve_intersection(
            p1.composition, p2.composition, 
            p3.composition, p4.composition
        )
        
        if intersect is None:
            result.status = IntersectionStatus.PARALLEL
            return result
        
        # Проверка: внутри треугольника?
        arr = intersect.normalized
        is_inside = all(x >= -EPSILON_BOUNDARY for x in arr)
        
        result.intersection = intersect
        result.status = IntersectionStatus.FOUND if is_inside else IntersectionStatus.OUTSIDE
        
        return result

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
