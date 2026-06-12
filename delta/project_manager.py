"""
Менеджер проекта — чистая бизнес-логика без Qt-зависимостей.

Используется:
- ProjectController (Qt-обёртка для GUI)
- Diagram API (headless-фасад для скриптов)
"""

import copy
from contextlib import contextmanager
from typing import Optional, List, Dict, Callable, Iterator
from pydantic import ValidationError as PydanticValidationError

from delta.models import (
    ProjectData, NamedComposition, TieLine, CurveLine, GuidePoint, Composition,
    CompositionUpdate, StyleUpdate, ArrowSettings, IntersectionResult, IntersectionStatus,
    TextAnnotation, HatchRegion, BoundarySegment, LineRefSegment, CurveRefSegment,
    FigureMargins,
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
        self._curve_map: Dict[str, CurveLine] = {}
        self._annotation_map: Dict[str, TextAnnotation] = {}
        self._hatch_map: Dict[str, HatchRegion] = {}
        
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

    def get_all_curve_lines(self) -> List[CurveLine]:
        return self._project.curve_lines

    def get_curve_line_count(self) -> int:
        return len(self._project.curve_lines)

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

    def get_curve_line(self, uid: str) -> CurveLine:
        cline = self._curve_map.get(uid)
        if cline is None:
            raise EntityNotFoundError("CurveLine", uid)
        return cline

    def find_curve_line(self, uid: str) -> Optional[CurveLine]:
        return self._curve_map.get(uid)

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
        
        with self._transact():
            self._project.compositions.append(comp)
            self._comp_map[comp.uid] = comp
        
        logger.bind(uid=comp.uid).info(f"Created composition '{name}'")
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
        
        with self._transact():
            self._project.lines.append(line)
            self._line_map[line.uid] = line
        
        logger.bind(uid=line.uid).info(f"Created line {start_uid} -> {end_uid}")
        return line.uid

    # =========================================================================
    # ОБНОВЛЕНИЕ
    # =========================================================================

    def update_components(self, names: List[str]) -> None:
        if len(names) == 3:
            with self._transact():
                self._project.components = names

    def update_component_molar_masses(self, masses: List[Optional[float]]) -> None:
        if len(masses) == 3:
            with self._transact():
                self._project.component_molar_masses = list(masses)

    def update_grid(self, visible: bool, step: float) -> None:
        with self._transact():
            self._project.grid.visible = visible
            self._project.grid.step = step

    def update_render_settings(
        self,
        *,
        lock_aspect: Optional[bool] = None,
        figure_margins: Optional[FigureMargins] = None,
        display_region_padding: Optional[float] = None,
    ) -> None:
        settings = self._project.render_settings

        changed = False
        if lock_aspect is not None and settings.lock_aspect != lock_aspect:
            changed = True
        if figure_margins is not None and settings.figure_margins != figure_margins:
            changed = True
        if (
            display_region_padding is not None
            and settings.display_region_padding != display_region_padding
        ):
            changed = True

        if not changed:
            return

        with self._transact():
            if lock_aspect is not None:
                settings.lock_aspect = lock_aspect
            if figure_margins is not None:
                settings.figure_margins = figure_margins
            if display_region_padding is not None:
                settings.display_region_padding = display_region_padding

    def update_lock_aspect(self, locked: bool) -> None:
        """Backward-compatible wrapper."""
        self.update_render_settings(lock_aspect=locked)

    def update_display_region(self, points: List[Composition]) -> None:
        with self._transact():
            self._project.display_region = list(points)

    def update_display_region_enabled(self, enabled: bool) -> None:
        with self._transact():
            self._project.display_region_enabled = enabled

    # =========================================================================
    # АННОТАЦИИ
    # =========================================================================

    def create_annotation(
        self,
        text: str = "Label",
        a: float = 33.0,
        b: float = 33.0,
        c: float = 34.0,
    ) -> str:
        ann = TextAnnotation(text=text, position=Composition(a=a, b=b, c=c))
        with self._transact():
            self._project.annotations.append(ann)
            self._annotation_map[ann.uid] = ann
        return ann.uid

    def get_annotation(self, uid: str) -> TextAnnotation:
        ann = self._annotation_map.get(uid)
        if ann is None:
            raise EntityNotFoundError("Annotation", uid)
        return ann

    def find_annotation(self, uid: str) -> Optional[TextAnnotation]:
        return self._annotation_map.get(uid)

    def update_annotation(self, uid: str, **fields) -> None:
        ann = self.get_annotation(uid)
        with self._transact():
            for k, v in fields.items():
                setattr(ann, k, v)

    def delete_annotation(self, uid: str) -> None:
        ann = self.get_annotation(uid)
        with self._transact():
            self._project.annotations.remove(ann)
            del self._annotation_map[uid]

    # =========================================================================
    # HATCH REGIONS
    # =========================================================================

    def create_hatch_region(
        self,
        segments: List[BoundarySegment],
        *,
        name: str = "Region",
        hatch_pattern: str = "//",
        hatch_color: str = "#000000",
        fill_color: str = "#000000",
        fill_alpha: float = 0.05,
        edge_color: str = "#000000",
        edge_width: float = 1.0,
    ) -> str:
        region = HatchRegion(
            name=name,
            segments=segments,
            hatch_pattern=hatch_pattern,
            hatch_color=hatch_color,
            fill_color=fill_color,
            fill_alpha=fill_alpha,
            edge_color=edge_color,
            edge_width=edge_width,
        )
        with self._transact():
            self._project.hatch_regions.append(region)
            self._hatch_map[region.uid] = region
        return region.uid

    def get_hatch_region(self, uid: str) -> HatchRegion:
        region = self._hatch_map.get(uid)
        if region is None:
            raise EntityNotFoundError("HatchRegion", uid)
        return region

    def update_hatch_region(self, uid: str, **fields: object) -> None:
        region = self.get_hatch_region(uid)
        with self._transact():
            for k, v in fields.items():
                setattr(region, k, v)

    def delete_hatch_region(self, uid: str) -> None:
        self.get_hatch_region(uid)
        with self._transact():
            del self._hatch_map[uid]
            self._project.hatch_regions = [
                h for h in self._project.hatch_regions if h.uid != uid
            ]

    def update_view_mode(self, is_inverted: bool) -> None:
        if self._project.is_inverted == is_inverted:
            return
        
        old_inv = self._project.is_inverted
        with self._transact():
            self._project.is_inverted = is_inverted
            self._convert_label_offsets(old_inv, is_inverted)

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
        
        with self._transact():
            update.apply_to(comp)

    def update_composition_style(self, uid: str, update: StyleUpdate) -> None:
        comp = self.get_composition(uid)
        with self._transact():
            update.apply_to(comp.style)

    def update_line_style(self, uid: str, update: StyleUpdate) -> None:
        line = self.get_line(uid)
        with self._transact():
            update.apply_to(line.style)

    def update_line_arrow(self, uid: str, arrow: ArrowSettings) -> None:
        line = self.get_line(uid)
        with self._transact():
            line.arrow = arrow

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
        with self._transact():
            line.start_uid = start_uid
            line.end_uid = end_uid

    def set_composition_label_pos(self, uid: str, x: float, y: float) -> None:
        comp = self.get_composition(uid)
        is_inv = self._project.is_inverted
        
        try:
            pt = math_utils.bary_to_cart(comp.composition, is_inv)
        except ValueError as e:
            raise ValidationError(f"Invalid coordinates: {e}")
        
        with self._transact():
            comp.label_offset = (float(x - pt[0]), float(y - pt[1]))

    def set_vertex_label_pos(self, index: int, x: float, y: float) -> None:
        with self._transact():
            self._project.vertex_labels_pos[str(index)] = (x, y)

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
        
        self._save_undo_before_change()
        
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

            curves_to_remove = [
                c.uid for c in self._project.curve_lines
                if c.start_uid == uid or c.end_uid == uid
            ]

            for c_uid in curves_to_remove:
                if c_uid in self._curve_map:
                    del self._curve_map[c_uid]

            self._project.curve_lines = [
                c for c in self._project.curve_lines
                if c.uid not in curves_to_remove
            ]
        finally:
            self._batch_mode = False
        
        self._notify_change()

    def delete_line(self, uid: str) -> None:
        self.get_line(uid)  # Проверка существования
        with self._transact():
            del self._line_map[uid]
            self._project.lines = [line for line in self._project.lines if line.uid != uid]

    # =========================================================================
    # CURVE LINE CRUD
    # =========================================================================

    def create_curve_line(self, start_uid: str, end_uid: str) -> str:
        """
        Создаёт кривую линию между двумя составами.

        Returns:
            UID созданной CurveLine

        Raises:
            ValidationError: если start == end
            EntityNotFoundError: если составы не найдены
        """
        if start_uid == end_uid:
            raise ValidationError("Cannot create curve line: start and end must be different")

        self.get_composition(start_uid)
        self.get_composition(end_uid)

        cline = CurveLine(start_uid=start_uid, end_uid=end_uid)

        with self._transact():
            self._project.curve_lines.append(cline)
            self._curve_map[cline.uid] = cline

        logger.bind(uid=cline.uid).info(f"Created curve line {start_uid} -> {end_uid}")
        return cline.uid

    def update_curve_line_endpoints(
        self, uid: str, start_uid: str, end_uid: str
    ) -> None:
        if start_uid == end_uid:
            raise ValidationError("Start and end must be different")
        self.get_composition(start_uid)
        self.get_composition(end_uid)

        cline = self.get_curve_line(uid)
        with self._transact():
            cline.start_uid = start_uid
            cline.end_uid = end_uid

    def update_curve_line_style(self, uid: str, update: StyleUpdate) -> None:
        cline = self.get_curve_line(uid)
        with self._transact():
            update.apply_to(cline.style)

    def update_curve_line_arrow(self, uid: str, arrow: ArrowSettings) -> None:
        cline = self.get_curve_line(uid)
        with self._transact():
            cline.arrow = arrow

    def update_curve_line_guide_markers(
        self, uid: str, show: bool, style: StyleUpdate
    ) -> None:
        cline = self.get_curve_line(uid)
        with self._transact():
            cline.show_guide_markers = show
            style.apply_to(cline.guide_marker_style)

    def update_curve_line_guides(
        self,
        uid: str,
        guides: List[GuidePoint],
        poly_degree: Optional[int] = None,
        curve_mode: Optional[str] = None,
    ) -> None:
        cline = self.get_curve_line(uid)
        with self._transact():
            cline.guide_points = list(guides)
            if poly_degree is not None:
                cline.poly_degree = poly_degree
            if curve_mode is not None:
                cline.curve_mode = curve_mode

    def delete_curve_line(self, uid: str) -> None:
        self.get_curve_line(uid)
        self._check_hatch_dependencies("curve", uid)
        with self._transact():
            del self._curve_map[uid]
            self._project.curve_lines = [
                c for c in self._project.curve_lines if c.uid != uid
            ]

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
        self._notify_change()

    def new_project(self) -> None:
        """Сбрасывает к пустому проекту"""
        self._project = ProjectData()
        self._rebuild_cache()
        self.clear_undo_history()
        self._is_modified = False
        logger.info("Project reset")
        self._notify_change()

    # =========================================================================
    # UNDO / REDO
    # =========================================================================

    def undo(self) -> bool:
        if not self._enable_undo or not self._undo_stack:
            return False
        
        self._redo_stack.append(copy.deepcopy(self._project))
        self._project = self._undo_stack.pop()
        self._rebuild_cache()
        self._notify_change()
        
        logger.info(f"Undo. Stack: {len(self._undo_stack)}")
        return True

    def redo(self) -> bool:
        if not self._enable_undo or not self._redo_stack:
            return False
        
        self._undo_stack.append(copy.deepcopy(self._project))
        self._project = self._redo_stack.pop()
        self._rebuild_cache()
        self._notify_change()
        
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
        self._curve_map = {c.uid: c for c in self._project.curve_lines}
        self._annotation_map = {a.uid: a for a in self._project.annotations}
        self._hatch_map = {
            h.uid: h for h in self._project.hatch_regions
        }

    def _notify_change(self) -> None:
        if self._batch_mode:
            return
        
        self._is_modified = True
        
        if self._on_change:
            self._on_change()

    def _save_undo_before_change(self) -> None:
        """
        Сохраняет текущее состояние в undo-стек ПЕРЕД мутацией.
        Используется внутри _transact(). Не вызывайте напрямую.
        """
        if not self._enable_undo:
            return
        
        self._undo_stack.append(copy.deepcopy(self._project))
        self._redo_stack.clear()
        
        if len(self._undo_stack) > self._max_undo_size:
            self._undo_stack.pop(0)

    @contextmanager
    def _transact(self) -> Iterator[None]:
        """
        Единый паттерн для мутирующих операций:
        - при входе сохраняет undo snapshot
        - при нормальном выходе уведомляет об изменении
        - при исключении НЕ уведомляет (состояние не изменилось)

        Использование:
            with self._transact():
                self._project.some_field = new_value
        """
        self._save_undo_before_change()
        yield
        self._notify_change()

    def _convert_label_offsets(self, old_inv: bool, new_inv: bool) -> None:
        """
        Пересчитывает label_offset всех составов при смене ориентации.
        
        Offset хранится в декартовых координатах (dx, dy) относительно 
        позиции точки. При смене inverted позиция точки меняется,
        поэтому нужно пересчитать offset, чтобы метка осталась 
        на том же месте в барицентрических координатах.
        """
        for comp in self._project.compositions:
            if comp.label_offset is None:
                continue
            
            try:
                off_x, off_y = comp.label_offset
                
                # Абсолютная позиция метки в старой системе
                old_pt = math_utils.bary_to_cart(comp.composition, old_inv)
                label_x = old_pt[0] + off_x
                label_y = old_pt[1] + off_y
                
                # Новая позиция точки
                new_pt = math_utils.bary_to_cart(comp.composition, new_inv)
                
                # Пересчитанный offset
                comp.label_offset = (label_x - new_pt[0], label_y - new_pt[1])
            except (ValueError, ZeroDivisionError, TypeError):
                logger.warning(f"Failed to convert label offset for {comp.uid}, resetting")
                comp.label_offset = None
        
        # Пересчитываем позиции меток вершин
        new_vertex_pos: Dict[str, tuple[float, float]] = {}
        for key, (lx, ly) in self._project.vertex_labels_pos.items():
            # Позиции вершин — абсолютные координаты, 
            # их нужно полностью пересчитать
            try:
                idx = int(key)
                old_vertices = math_utils.get_vertices(old_inv)
                new_vertices = math_utils.get_vertices(new_inv)
                
                # Смещение метки относительно вершины
                dx = lx - old_vertices[idx][0]
                dy = ly - old_vertices[idx][1]
                
                new_vertex_pos[key] = (
                    new_vertices[idx][0] + dx,
                    new_vertices[idx][1] + dy
                )
            except (ValueError, IndexError):
                pass
        
        self._project.vertex_labels_pos = new_vertex_pos

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

    def _check_hatch_dependencies(self, kind: str, uid: str) -> None:
        """Проверяет, что ни один hatch region не ссылается на удаляемую линию/кривую."""
        for region in self._project.hatch_regions:
            for seg in region.segments:
                if kind == "line" and isinstance(seg, LineRefSegment) and seg.line_uid == uid:
                    raise ValidationError(
                        f"Cannot delete: line is used by hatch region '{region.name}'"
                    )
                if kind == "curve" and isinstance(seg, CurveRefSegment) and seg.curve_uid == uid:
                    raise ValidationError(
                        f"Cannot delete: curve is used by hatch region '{region.name}'"
                    )
