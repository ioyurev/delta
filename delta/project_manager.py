"""
Менеджер проекта — чистая бизнес-логика без Qt-зависимостей.

Используется:
- ProjectController (Qt-обёртка для GUI)
- Diagram API (headless-фасад для скриптов)
"""

import copy
from typing import Optional, List, Dict, Callable
from pydantic import ValidationError as PydanticValidationError

from delta.models import (
    ProjectData, NamedComposition, TieLine, Composition,
    CompositionUpdate, StyleUpdate, IntersectionResult, IntersectionStatus
)
from delta import math_utils
from delta.constants import EPSILON_BOUNDARY
from delta.serializer import ProjectSerializer
from delta.exceptions import EntityNotFoundError, DuplicateEntityError, ValidationError
from loguru import logger


class ProjectManager:
    """
    Управляет данными проекта и предоставляет CRUD-операции.
    
    Не зависит от Qt. Для уведомлений использует callback.
    
    Attributes:
        project_data: Данные проекта (только для чтения!)
        is_modified: Флаг несохранённых изменений
    
    Example (headless):
        manager = ProjectManager()
        uid = manager.create_composition("Point A", 0.5, 0.3, 0.2)
        manager.save_to_file("project.json")
    
    Example (с GUI):
        def on_change():
            canvas.redraw()
        
        manager = ProjectManager(on_change=on_change)
    """
    
    DEFAULT_MAX_UNDO_SIZE = 50
    
    def __init__(
        self,
        on_change: Optional[Callable[[], None]] = None,
        enable_undo: bool = True,
        max_undo_size: int = DEFAULT_MAX_UNDO_SIZE
    ):
        """
        Args:
            on_change: Callback при изменении данных (для UI-обновлений)
            enable_undo: Включить Undo/Redo
            max_undo_size: Максимальный размер стека отмены
        """
        self._on_change = on_change
        self._enable_undo = enable_undo
        self._max_undo_size = max_undo_size
        
        self._project = ProjectData()
        self._is_modified = False
        
        # Кэши для O(1) доступа
        self._comp_map: Dict[str, NamedComposition] = {}
        self._line_map: Dict[str, TieLine] = {}
        
        # Режим пакетной обработки (подавляет уведомления)
        self._batch_mode = False
        
        # Undo/Redo стеки
        self._undo_stack: List[ProjectData] = []
        self._redo_stack: List[ProjectData] = []

    # =========================================================================
    # СВОЙСТВА
    # =========================================================================

    @property
    def project_data(self) -> ProjectData:
        """
        Данные проекта для чтения.
        
        WARNING: Не модифицируйте напрямую! Используйте методы менеджера.
        """
        return self._project

    @property
    def is_modified(self) -> bool:
        """Есть ли несохранённые изменения"""
        return self._is_modified

    # =========================================================================
    # ГЕТТЕРЫ
    # =========================================================================

    def has_compositions(self) -> bool:
        return len(self._project.compositions) > 0

    def get_composition_count(self) -> int:
        return len(self._project.compositions)

    def get_line_count(self) -> int:
        return len(self._project.lines)

    def get_components(self) -> List[str]:
        return list(self._project.components)

    def is_inverted(self) -> bool:
        return self._project.is_inverted

    def get_all_compositions(self) -> List[NamedComposition]:
        return self._project.compositions

    def get_all_lines(self) -> List[TieLine]:
        return self._project.lines

    # =========================================================================
    # ПОИСК
    # =========================================================================

    def get_composition(self, uid: str) -> NamedComposition:
        """
        Возвращает состав по UID.
        
        Raises:
            EntityNotFoundError: если не найден
        """
        comp = self._comp_map.get(uid)
        if comp is None:
            raise EntityNotFoundError("Composition", uid)
        return comp

    def find_composition(self, uid: str) -> Optional[NamedComposition]:
        """Мягкий поиск — возвращает None если не найден"""
        return self._comp_map.get(uid)

    def get_line(self, uid: str) -> TieLine:
        """
        Возвращает линию по UID.
        
        Raises:
            EntityNotFoundError: если не найдена
        """
        line = self._line_map.get(uid)
        if line is None:
            raise EntityNotFoundError("Line", uid)
        return line

    def find_line(self, uid: str) -> Optional[TieLine]:
        """Мягкий поиск — возвращает None если не найдена"""
        return self._line_map.get(uid)

    def get_line_endpoints(self, line_uid: str) -> tuple[NamedComposition, NamedComposition]:
        """
        Возвращает (start, end) составы для линии.
        
        Raises:
            EntityNotFoundError: если линия или составы не найдены
        """
        line = self.get_line(line_uid)
        start_comp = self.get_composition(line.start_uid)
        end_comp = self.get_composition(line.end_uid)
        return start_comp, end_comp

    # =========================================================================
    # СОЗДАНИЕ
    # =========================================================================

    def create_composition(
        self,
        name: str = "New",
        a: float = 0.0,
        b: float = 0.0,
        c: float = 0.0,
        show_label: bool = True,
        show_marker: bool = True,
        validate: bool = True
    ) -> str:
        """
        Создаёт состав и возвращает его UID.
        
        Args:
            name: Имя состава
            a, b, c: Координаты (будут нормализованы)
            show_label: Показывать текстовую метку
            show_marker: Показывать маркер
            validate: Проверять физическую валидность
            
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
                    f"must be non-negative."
                )
            
            comp = NamedComposition(name=name, composition=composition)
        except PydanticValidationError as e:
            error_msg = e.errors()[0]['msg'] if e.errors() else "Invalid data"
            raise ValidationError(str(error_msg))
        
        comp.style.show_label = show_label
        comp.style.show_marker = show_marker
        
        self._project.compositions.append(comp)
        self._comp_map[comp.uid] = comp
        
        logger.bind(uid=comp.uid).info(f"Created composition '{name}'")
        self._notify_change()
        return comp.uid

    def create_line(self, start_uid: str, end_uid: str) -> str:
        """
        Создаёт линию между двумя составами.
        
        Returns:
            UID созданной линии
            
        Raises:
            ValidationError: если start == end или координаты совпадают
            DuplicateEntityError: если линия уже существует
            EntityNotFoundError: если составы не найдены
        """
        if start_uid == end_uid:
            raise ValidationError("Cannot create line: start and end must be different")
        
        start_comp = self.get_composition(start_uid)
        end_comp = self.get_composition(end_uid)
        
        if start_comp.composition.normalized_is_close(end_comp.composition):
            raise ValidationError(
                f"Cannot create line: '{start_comp.name}' and '{end_comp.name}' "
                f"have identical coordinates"
            )
        
        for line in self._project.lines:
            if {line.start_uid, line.end_uid} == {start_uid, end_uid}:
                raise DuplicateEntityError("Line already exists")
        
        line = TieLine(start_uid=start_uid, end_uid=end_uid)
        self._project.lines.append(line)
        self._line_map[line.uid] = line
        
        logger.bind(uid=line.uid).info(f"Created line {start_uid} -> {end_uid}")
        self._notify_change()
        return line.uid

    # =========================================================================
    # ОБНОВЛЕНИЕ
    # =========================================================================

    def update_components(self, names: List[str]) -> None:
        if len(names) == 3:
            self._project.components = names
            self._notify_change()

    def update_grid(self, visible: bool, step: float) -> None:
        self._project.grid.visible = visible
        self._project.grid.step = step
        self._notify_change()

    def update_view_mode(self, is_inverted: bool) -> None:
        if self._project.is_inverted == is_inverted:
            return
        self._project.is_inverted = is_inverted
        self._notify_change()

    def update_composition(
        self,
        uid: str,
        update: CompositionUpdate,
        validate: bool = True
    ) -> None:
        """
        Обновляет состав.
        
        Raises:
            EntityNotFoundError: если не найден
            ValidationError: если validate=True и данные невалидны
        """
        comp = self.get_composition(uid)
        
        if validate and update.has_coordinate_changes():
            new_a = update.a if update.a is not None else comp.composition.a
            new_b = update.b if update.b is not None else comp.composition.b
            new_c = update.c if update.c is not None else comp.composition.c
            
            try:
                new_composition = Composition(a=new_a, b=new_b, c=new_c)
                
                if not new_composition.is_physically_valid:
                    raise ValidationError(
                        "Invalid: values would result in negative fractions"
                    )
                
                self._check_degenerate_lines(uid, new_composition)
            except PydanticValidationError as e:
                error_msg = e.errors()[0]['msg'] if e.errors() else "Invalid data"
                raise ValidationError(str(error_msg))
        
        update.apply_to(comp)
        self._notify_change()

    def update_composition_style(self, uid: str, update: StyleUpdate) -> None:
        comp = self.get_composition(uid)
        update.apply_to(comp.style)
        self._notify_change()

    def update_line_style(self, uid: str, update: StyleUpdate) -> None:
        line = self.get_line(uid)
        update.apply_to(line.style)
        self._notify_change()

    def update_line_endpoints(self, line_uid: str, start_uid: str, end_uid: str) -> None:
        """
        Обновляет конечные точки линии.
        
        Raises:
            ValidationError: если start == end или создаёт дубликат
            EntityNotFoundError: если не найдены
        """
        if start_uid == end_uid:
            raise ValidationError("Start and end must be different")
        
        start_comp = self.get_composition(start_uid)
        end_comp = self.get_composition(end_uid)
        
        if start_comp.composition.normalized_is_close(end_comp.composition):
            raise ValidationError("Compositions have identical coordinates")
        
        for line in self._project.lines:
            if line.uid != line_uid:
                if {line.start_uid, line.end_uid} == {start_uid, end_uid}:
                    raise DuplicateEntityError("Line with these endpoints exists")
        
        line = self.get_line(line_uid)
        line.start_uid = start_uid
        line.end_uid = end_uid
        self._notify_change()

    def set_composition_label_pos(self, uid: str, x: float, y: float) -> None:
        comp = self.get_composition(uid)
        is_inv = self._project.is_inverted
        
        try:
            pt = math_utils.bary_to_cart(comp.composition, is_inv)
        except ValueError as e:
            raise ValidationError(f"Invalid coordinates: {e}")
        
        comp.label_offset = (float(x - pt[0]), float(y - pt[1]))
        self._notify_change()

    def set_vertex_label_pos(self, index: int, x: float, y: float) -> None:
        self._project.vertex_labels_pos[str(index)] = (x, y)
        self._notify_change()

    # =========================================================================
    # УДАЛЕНИЕ
    # =========================================================================

    def delete_composition(self, uid: str) -> None:
        """
        Удаляет состав и связанные линии.
        
        Raises:
            EntityNotFoundError: если не найден
        """
        self.get_composition(uid)  # Проверка существования
        
        logger.info(f"Deleting composition: {uid}")
        
        old_batch = self._batch_mode
        self._batch_mode = True
        
        try:
            del self._comp_map[uid]
            self._project.compositions = [
                p for p in self._project.compositions if p.uid != uid
            ]
            
            lines_to_remove = [
                line.uid for line in self._project.lines
                if line.start_uid == uid or line.end_uid == uid
            ]
            
            for line_uid in lines_to_remove:
                if line_uid in self._line_map:
                    del self._line_map[line_uid]
            
            self._project.lines = [
                line for line in self._project.lines
                if line.uid not in lines_to_remove
            ]
        finally:
            self._batch_mode = old_batch
        
        self._notify_change()

    def delete_line(self, uid: str) -> None:
        self.get_line(uid)  # Проверка существования
        del self._line_map[uid]
        self._project.lines = [line for line in self._project.lines if line.uid != uid]
        self._notify_change()

    # =========================================================================
    # РАСЧЁТЫ
    # =========================================================================

    def calculate_intersection(
        self,
        line1_uid: str,
        line2_uid: str
    ) -> IntersectionResult:
        """
        Рассчитывает пересечение двух линий.
        
        Raises:
            EntityNotFoundError: если линия не найдена
            ValidationError: если line1 == line2
        """
        if not line1_uid or not line2_uid:
            return IntersectionResult(status=IntersectionStatus.INVALID_INPUT)
        
        if line1_uid == line2_uid:
            raise ValidationError("Cannot intersect line with itself")
        
        p1, p2 = self.get_line_endpoints(line1_uid)
        p3, p4 = self.get_line_endpoints(line2_uid)
        
        result = IntersectionResult(
            line1_endpoints=(p1.composition, p2.composition),
            line2_endpoints=(p3.composition, p4.composition),
        )
        
        intersect = math_utils.solve_intersection(
            p1.composition, p2.composition,
            p3.composition, p4.composition
        )
        
        if intersect is None:
            result.status = IntersectionStatus.PARALLEL
            return result
        
        arr = intersect.normalized
        is_inside = all(x >= -EPSILON_BOUNDARY for x in arr)
        
        result.intersection = intersect
        result.status = IntersectionStatus.FOUND if is_inside else IntersectionStatus.OUTSIDE
        
        return result

    # =========================================================================
    # СЕРИАЛИЗАЦИЯ
    # =========================================================================

    def save_to_file(self, filepath: str) -> None:
        """Сохраняет проект в JSON"""
        ProjectSerializer.save_to_file(self._project, filepath)
        self._is_modified = False

    def load_from_file(self, filepath: str) -> None:
        """Загружает проект из JSON"""
        new_project = ProjectSerializer.load_from_file(filepath)
        self._project = new_project
        self._rebuild_cache()
        self.clear_undo_history()
        self._is_modified = False
        self._notify_change(save_undo=False)

    def new_project(self) -> None:
        """Сбрасывает к пустому проекту"""
        self._project = ProjectData()
        self._rebuild_cache()
        self.clear_undo_history()
        self._is_modified = False
        logger.info("Project reset")
        self._notify_change(save_undo=False)

    # =========================================================================
    # UNDO / REDO
    # =========================================================================

    def undo(self) -> bool:
        if not self._enable_undo or not self._undo_stack:
            return False
        
        self._redo_stack.append(copy.deepcopy(self._project))
        self._project = self._undo_stack.pop()
        self._rebuild_cache()
        self._notify_change(save_undo=False)
        
        logger.info(f"Undo. Stack: {len(self._undo_stack)}")
        return True

    def redo(self) -> bool:
        if not self._enable_undo or not self._redo_stack:
            return False
        
        self._undo_stack.append(copy.deepcopy(self._project))
        self._project = self._redo_stack.pop()
        self._rebuild_cache()
        self._notify_change(save_undo=False)
        
        logger.info(f"Redo. Stack: {len(self._redo_stack)}")
        return True

    def can_undo(self) -> bool:
        return self._enable_undo and len(self._undo_stack) > 0

    def can_redo(self) -> bool:
        return self._enable_undo and len(self._redo_stack) > 0

    def clear_undo_history(self) -> None:
        self._undo_stack.clear()
        self._redo_stack.clear()

    # =========================================================================
    # ПРИВАТНЫЕ МЕТОДЫ
    # =========================================================================

    def _rebuild_cache(self) -> None:
        self._comp_map = {comp.uid: comp for comp in self._project.compositions}
        self._line_map = {line.uid: line for line in self._project.lines}

    def _notify_change(self, save_undo: bool = True) -> None:
        if self._batch_mode:
            return
        
        self._is_modified = True
        
        if save_undo and self._enable_undo:
            self._save_undo_state()
        
        if self._on_change:
            self._on_change()

    def _save_undo_state(self) -> None:
        self._undo_stack.append(copy.deepcopy(self._project))
        self._redo_stack.clear()
        
        if len(self._undo_stack) > self._max_undo_size:
            self._undo_stack.pop(0)

    def _check_degenerate_lines(self, composition_uid: str, new_coords: Composition) -> None:
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
                            f"Would create zero-length line with '{other_comp.name}'"
                        )
                except EntityNotFoundError:
                    pass