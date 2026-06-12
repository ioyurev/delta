"""
Модели данных приложения на базе Pydantic.

Обеспечивает:
- Автоматическую валидацию при создании
- Сериализацию в JSON
- Чёткие сообщения об ошибках
"""

import math
import uuid
from typing import Annotated, List, Literal, Tuple, Optional, Dict, Union
from pydantic import Discriminator
from pydantic import BaseModel, Field, field_validator, model_validator, ConfigDict
from enum import Enum, auto
from dataclasses import dataclass, field
from delta.constants import (
    EPSILON_ZERO,
    EPSILON_BOUNDARY,
    COMPOSITION_COMPARISON_ATOL,
    COORD_INPUT_MIN,
    COORD_INPUT_MAX,
    MARKER_SIZE_DEFAULT,
    MARKER_SIZE_MIN,
    MARKER_SIZE_MAX,
    LINE_WIDTH_DEFAULT,
    GRID_STEP_DEFAULT,
    GRID_STEP_MIN,
    GRID_STEP_MAX,
    ARROW_COUNT_DEFAULT,
    ARROW_COUNT_MIN,
    ARROW_COUNT_MAX,
)


# =============================================================================
# ИСКЛЮЧЕНИЯ
# =============================================================================

class CompositionError(ValueError):
    """Ошибки связанные с композицией"""
    pass


# =============================================================================
# COMPOSITION (Immutable)
# =============================================================================

class Composition(BaseModel):
    """
    Барицентрические координаты точки в треугольнике Гиббса.
    
    Хранит СЫРЫЕ значения (a, b, c). Нормализация — отдельный метод.
    
    Инварианты:
    - Значения конечны (не NaN, не Inf)
    - Для валидной точки: a,b,c >= 0 и a+b+c > 0
    """
    model_config = ConfigDict(frozen=True)
    
    a: float = 0.0
    b: float = 0.0
    c: float = 0.0
    
    @field_validator('a', 'b', 'c', mode='before')
    @classmethod
    def validate_finite(cls, v: float, info) -> float:
        """Проверка на NaN/Inf"""
        val = float(v)
        if math.isnan(val) or math.isinf(val):
            raise ValueError(f"Coordinate '{info.field_name}' must be finite, got: {val}")
        return val
    
    # ==================== СВОЙСТВА ====================
    
    @property
    def total(self) -> float:
        """Сумма компонент (точное суммирование)"""
        return math.fsum([self.a, self.b, self.c])
    
    @property
    def is_valid(self) -> bool:
        """Проверяет, можно ли нормализовать (sum > 0)"""
        return self.total > EPSILON_ZERO
    
    @property
    def is_physically_valid(self) -> bool:
        """
        Проверяет физическую осмысленность состава.
        Все нормализованные координаты должны быть >= 0.
        """
        if not self.is_valid:
            return False
        a, b, c = self.normalized
        return a >= -EPSILON_BOUNDARY and b >= -EPSILON_BOUNDARY and c >= -EPSILON_BOUNDARY
    
    @property
    def normalized(self) -> Tuple[float, float, float]:
        """
        Нормализованные координаты (сумма = 1).
        
        Raises:
            CompositionError: если total ≈ 0
        """
        total = self.total
        if abs(total) < EPSILON_ZERO:
            raise CompositionError(
                f"Cannot normalize composition with zero total: ({self.a}, {self.b}, {self.c})"
            )
        return (self.a / total, self.b / total, self.c / total)
    
    # ==================== ФАБРИЧНЫЕ МЕТОДЫ ====================
    
    @classmethod
    def vertex_a(cls) -> 'Composition':
        return cls(a=1.0, b=0.0, c=0.0)
    
    @classmethod
    def vertex_b(cls) -> 'Composition':
        return cls(a=0.0, b=1.0, c=0.0)
    
    @classmethod
    def vertex_c(cls) -> 'Composition':
        return cls(a=0.0, b=0.0, c=1.0)
    
    @classmethod
    def from_user_input(cls, a: float, b: float, c: float) -> 'Composition':
        """Создаёт Composition с clamping для UI ввода"""
        def clamp(val: float) -> float:
            if math.isnan(val) or math.isinf(val):
                return 0.0
            return max(COORD_INPUT_MIN, min(COORD_INPUT_MAX, val))
        return cls(a=clamp(a), b=clamp(b), c=clamp(c))
    
    # ==================== СРАВНЕНИЕ ====================
    
    def normalized_is_close(self, other: 'Composition', atol: float | None = None) -> bool:
        """Сравнивает составы с абсолютным допуском"""
        if atol is None:
            atol = COMPOSITION_COMPARISON_ATOL
        try:
            n1 = self.normalized
            n2 = other.normalized
            return all(abs(n1[i] - n2[i]) < atol for i in range(3))
        except CompositionError:
            return False


# =============================================================================
# VISUAL STYLE
# =============================================================================

class VisualStyle(BaseModel):
    """Стиль отображения (цвет, толщина и т.д.)"""
    model_config = ConfigDict(validate_assignment=True)
    
    color: str = "#000000"
    size: float = Field(default=MARKER_SIZE_DEFAULT, ge=MARKER_SIZE_MIN, le=MARKER_SIZE_MAX)
    line_style: str = "-"
    marker_symbol: str = "o"
    show_label: bool = True
    show_marker: bool = True
    
    @field_validator('color')
    @classmethod
    def validate_color(cls, v: str) -> str:
        """Базовая проверка формата цвета"""
        v = v.strip()
        if not v.startswith('#') or len(v) not in (4, 7):
            # Пытаемся исправить или используем дефолт
            if len(v) == 6 and all(c in '0123456789abcdefABCDEF' for c in v):
                return f"#{v}"
            return "#000000"
        return v
    
    @field_validator('line_style')
    @classmethod
    def validate_line_style(cls, v: str) -> str:
        valid = {'-', '--', ':', '-.'}
        return v if v in valid else '-'
    
    @field_validator('marker_symbol')
    @classmethod
    def validate_marker(cls, v: str) -> str:
        valid = {'o', 's', '^', 'v', 'D', '*', 'x', 'P', '.', ','}
        return v if v in valid else 'o'


# =============================================================================
# NAMED COMPOSITION
# =============================================================================

class NamedComposition(BaseModel):
    """Именованная точка состава"""
    model_config = ConfigDict(validate_assignment=True)
    
    uid: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "New Composition"
    composition: Composition = Field(default_factory=Composition)
    style: VisualStyle = Field(default_factory=VisualStyle)
    label_offset: Optional[Tuple[float, float]] = None
    
    @field_validator('name')
    @classmethod
    def validate_name(cls, v: str) -> str:
        """Ограничение длины имени"""
        from delta.constants import COMP_NAME_MAX_LENGTH
        return v[:COMP_NAME_MAX_LENGTH] if v else "Unnamed"


# =============================================================================
# ARROW SETTINGS
# =============================================================================

class ArrowSettings(BaseModel):
    """Настройки стрелок вдоль линии"""
    model_config = ConfigDict(validate_assignment=True)

    enabled: bool = False
    direction: str = "to_end"  # "to_end" | "to_start"
    count: int = Field(default=ARROW_COUNT_DEFAULT, ge=ARROW_COUNT_MIN, le=ARROW_COUNT_MAX)

    @field_validator('direction')
    @classmethod
    def validate_direction(cls, v: str) -> str:
        if v not in ("to_end", "to_start"):
            return "to_end"
        return v


# =============================================================================
# TIE LINE
# =============================================================================

class TieLine(BaseModel):
    """Прямая линия связи между составами"""
    model_config = ConfigDict(validate_assignment=True)

    uid: str = Field(default_factory=lambda: str(uuid.uuid4()))
    start_uid: str = ""
    end_uid: str = ""
    style: VisualStyle = Field(default_factory=lambda: VisualStyle(size=LINE_WIDTH_DEFAULT))
    arrow: ArrowSettings = Field(default_factory=ArrowSettings)

    @model_validator(mode='after')
    def validate_different_endpoints(self) -> 'TieLine':
        """Start и End должны быть разными"""
        if self.start_uid and self.end_uid and self.start_uid == self.end_uid:
            raise ValueError("Line cannot connect composition to itself")
        return self


# =============================================================================
# CURVE LINE
# =============================================================================

class GuidePoint(BaseModel):
    """Анонимная направляющая точка кривой (не из project.compositions)"""
    model_config = ConfigDict(validate_assignment=True)

    uid: str = Field(default_factory=lambda: str(uuid.uuid4()))
    composition: Composition = Field(default_factory=Composition)


class CurveLine(BaseModel):
    """Кривая линия: проходит через start/end, интерполирует или аппроксимирует guide_points"""
    model_config = ConfigDict(validate_assignment=True)

    uid: str = Field(default_factory=lambda: str(uuid.uuid4()))
    start_uid: str = ""
    end_uid: str = ""
    guide_points: List[GuidePoint] = Field(default_factory=list)
    curve_mode: str = "spline"  # "spline" | "polynomial"
    poly_degree: int = Field(default=3, ge=1, le=5)
    show_guide_markers: bool = False
    guide_marker_style: VisualStyle = Field(
        default_factory=lambda: VisualStyle(color="#888888")
    )
    style: VisualStyle = Field(default_factory=lambda: VisualStyle(size=LINE_WIDTH_DEFAULT))
    arrow: ArrowSettings = Field(default_factory=ArrowSettings)

    @field_validator('curve_mode')
    @classmethod
    def validate_curve_mode(cls, v: str) -> str:
        if v not in ("spline", "polynomial"):
            return "spline"
        return v

    @model_validator(mode='after')
    def validate_different_endpoints(self) -> 'CurveLine':
        if self.start_uid and self.end_uid and self.start_uid == self.end_uid:
            raise ValueError("Curve line cannot connect composition to itself")
        return self


# =============================================================================
# GRID SETTINGS
# =============================================================================

class GridSettings(BaseModel):
    """Настройки сетки"""
    visible: bool = False
    step: float = Field(default=GRID_STEP_DEFAULT, ge=GRID_STEP_MIN, le=GRID_STEP_MAX)


# =============================================================================
# TEXT ANNOTATION
# =============================================================================

class TextAnnotation(BaseModel):
    """Текстовая аннотация на диаграмме."""
    model_config = ConfigDict(validate_assignment=True)

    uid: str = Field(default_factory=lambda: str(uuid.uuid4()))
    text: str = "Label"
    position: Composition = Field(default_factory=lambda: Composition(a=33.0, b=33.0, c=34.0))
    font_size: float = Field(default=10.0, ge=4.0, le=72.0)
    color: str = "#000000"
    italic: bool = False
    bold: bool = False
    ha: str = "center"   # left | center | right
    va: str = "center"   # top | center | bottom | baseline
    box_enabled: bool = False
    box_facecolor: str = "#ffffff"
    box_edgecolor: str = "#000000"
    box_alpha: float = Field(default=0.8, ge=0.0, le=1.0)
    box_pad: float = Field(default=0.3, ge=0.0, le=5.0)
    visible: bool = True
    arrow_enabled: bool = False
    arrow_target: Optional[Composition] = None
    arrow_color: str = "#000000"

    @field_validator('color', 'box_facecolor', 'box_edgecolor', 'arrow_color')
    @classmethod
    def validate_color(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith('#') or len(v) not in (4, 7):
            if len(v) == 6 and all(c in '0123456789abcdefABCDEF' for c in v):
                return f"#{v}"
            return "#000000"
        return v

    @field_validator('ha')
    @classmethod
    def validate_ha(cls, v: str) -> str:
        return v if v in ('left', 'center', 'right') else 'center'

    @field_validator('va')
    @classmethod
    def validate_va(cls, v: str) -> str:
        return v if v in ('top', 'center', 'bottom', 'baseline') else 'center'


# =============================================================================
# HATCH REGION
# =============================================================================

class StraightSegment(BaseModel):
    """Прямой отрезок границы."""
    model_config = ConfigDict(frozen=True)

    kind: Literal["straight"] = "straight"
    start: Composition
    end: Composition


class LineRefSegment(BaseModel):
    """Граница, совпадающая с существующей TieLine."""
    model_config = ConfigDict(frozen=True)

    kind: Literal["line_ref"] = "line_ref"
    line_uid: str
    reverse: bool = False


class CurveRefSegment(BaseModel):
    """Граница, совпадающая с существующей CurveLine."""
    model_config = ConfigDict(frozen=True)

    kind: Literal["curve_ref"] = "curve_ref"
    curve_uid: str
    reverse: bool = False


BoundarySegment = Annotated[
    Union[StraightSegment, LineRefSegment, CurveRefSegment],
    Discriminator("kind"),
]


class HatchRegion(BaseModel):
    """Область с hatch-заливкой, ограниченная замкнутым контуром из сегментов."""
    model_config = ConfigDict(validate_assignment=True)

    uid: str = Field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "Region"
    segments: List[BoundarySegment] = Field(default_factory=list)
    hatch_pattern: str = "//"
    hatch_color: str = "#000000"
    fill_color: str = "#000000"
    fill_alpha: float = Field(default=0.05, ge=0.0, le=1.0)
    edge_color: str = "#000000"
    edge_width: float = Field(default=1.0, ge=0.0, le=10.0)
    visible: bool = True

    @field_validator('hatch_pattern')
    @classmethod
    def validate_hatch(cls, v: str) -> str:
        valid_chars = set("/\\|-+xoO.*")
        if not v or not all(c in valid_chars for c in v):
            return "//"
        return v

    @field_validator('hatch_color', 'fill_color', 'edge_color')
    @classmethod
    def validate_color(cls, v: str) -> str:
        v = v.strip()
        if not v.startswith('#') or len(v) not in (4, 7):
            if len(v) == 6 and all(c in '0123456789abcdefABCDEF' for c in v):
                return f"#{v}"
            return "#000000"
        return v


# =============================================================================
# RENDER SETTINGS
# =============================================================================

class FigureMargins(BaseModel):
    """Отступы figure в долях размера: left/right/top/bottom."""
    model_config = ConfigDict(validate_assignment=True)

    left: float = Field(default=0.05, ge=0.0, lt=1.0)
    right: float = Field(default=0.05, ge=0.0, lt=1.0)
    top: float = Field(default=0.05, ge=0.0, lt=1.0)
    bottom: float = Field(default=0.05, ge=0.0, lt=1.0)

    @model_validator(mode='after')
    def validate_totals(self) -> 'FigureMargins':
        if self.left + self.right >= 1.0:
            raise ValueError("FigureMargins: left + right must be < 1.0")
        if self.top + self.bottom >= 1.0:
            raise ValueError("FigureMargins: top + bottom must be < 1.0")
        return self


class RenderSettings(BaseModel):
    """Настройки рендера, единые для GUI и headless."""
    model_config = ConfigDict(validate_assignment=True)

    lock_aspect: bool = True
    figure_margins: FigureMargins = Field(default_factory=FigureMargins)
    display_region_padding: float = Field(default=0.05, ge=0.0)


# =============================================================================
# PROJECT DATA
# =============================================================================

class ProjectData(BaseModel):
    """Корневой объект проекта"""
    model_config = ConfigDict(validate_assignment=True)

    version: str = "1.1"
    components: List[str] = Field(default_factory=lambda: ["A", "B", "C"])
    component_molar_masses: List[Optional[float]] = Field(
        default_factory=lambda: [None, None, None]  # type: ignore[arg-type]
    )
    compositions: List[NamedComposition] = Field(default_factory=list)
    lines: List[TieLine] = Field(default_factory=list)
    curve_lines: List[CurveLine] = Field(default_factory=list)
    grid: GridSettings = Field(default_factory=GridSettings)
    is_inverted: bool = False
    render_settings: RenderSettings = Field(default_factory=RenderSettings)
    display_region: List[Composition] = Field(default_factory=list)
    display_region_enabled: bool = False
    annotations: List[TextAnnotation] = Field(default_factory=list)
    hatch_regions: List[HatchRegion] = Field(default_factory=list)
    vertex_labels_pos: Dict[str, Tuple[float, float]] = Field(default_factory=dict)

    @property
    def lock_aspect(self) -> bool:
        """
        Совместимость со старым кодом чтения.
        Источник истины: render_settings.lock_aspect
        """
        return self.render_settings.lock_aspect

    @field_validator('components')
    @classmethod
    def validate_components(cls, v: List[str]) -> List[str]:
        """Должно быть ровно 3 компонента"""
        if len(v) != 3:
            raise ValueError(f"Expected 3 components, got {len(v)}")
        return [str(c) if c else f"C{i+1}" for i, c in enumerate(v)]

    @model_validator(mode='after')
    def validate_line_references(self) -> 'ProjectData':
        """Проверка целостности ссылок в линиях и hatch regions"""
        comp_uids = {c.uid for c in self.compositions}
        line_uids = {ln.uid for ln in self.lines}
        curve_uids = {cl.uid for cl in self.curve_lines}

        for line in self.lines:
            if line.start_uid and line.start_uid not in comp_uids:
                raise ValueError(f"Line references unknown composition: {line.start_uid}")
            if line.end_uid and line.end_uid not in comp_uids:
                raise ValueError(f"Line references unknown composition: {line.end_uid}")

        for cline in self.curve_lines:
            if cline.start_uid and cline.start_uid not in comp_uids:
                raise ValueError(f"Curve line references unknown composition: {cline.start_uid}")
            if cline.end_uid and cline.end_uid not in comp_uids:
                raise ValueError(f"Curve line references unknown composition: {cline.end_uid}")

        for region in self.hatch_regions:
            for seg in region.segments:
                if isinstance(seg, LineRefSegment) and seg.line_uid not in line_uids:
                    raise ValueError(f"Hatch region references unknown line: {seg.line_uid}")
                if isinstance(seg, CurveRefSegment) and seg.curve_uid not in curve_uids:
                    raise ValueError(f"Hatch region references unknown curve: {seg.curve_uid}")

        return self


# =============================================================================
# DTOs
# =============================================================================

@dataclass
class CompositionUpdate:
    """DTO для обновления координат и имени состава"""
    name: Optional[str] = None
    a: Optional[float] = None
    b: Optional[float] = None
    c: Optional[float] = None
    
    def has_coordinate_changes(self) -> bool:
        return any(v is not None for v in (self.a, self.b, self.c))
    
    def apply_to(self, comp: NamedComposition) -> None:
        if self.name is not None:
            comp.name = self.name
        
        # Обновляем координаты (модель Pydantic свалидирует их при присваивании)
        new_coords = {
            'a': self.a if self.a is not None else comp.composition.a,
            'b': self.b if self.b is not None else comp.composition.b,
            'c': self.c if self.c is not None else comp.composition.c,
        }
        # Т.к. Composition frozen, создаём новый объект
        object.__setattr__(comp, 'composition', Composition(**new_coords))

    @classmethod
    def coordinate(cls, field: str, value: float) -> 'CompositionUpdate':
        if field == 'a':
            return cls(a=value)
        elif field == 'b':
            return cls(b=value)
        elif field == 'c':
            return cls(c=value)
        raise ValueError(f"Unknown coordinate field: {field}")


@dataclass
class StyleUpdate:
    """DTO для обновления стиля"""
    color: Optional[str] = None
    size: Optional[float] = None
    line_style: Optional[str] = None
    marker_symbol: Optional[str] = None
    show_label: Optional[bool] = None
    show_marker: Optional[bool] = None
    
    def apply_to(self, style: VisualStyle) -> None:
        if self.color is not None:
            style.color = self.color
        if self.size is not None:
            style.size = self.size
        if self.line_style is not None:
            style.line_style = self.line_style
        if self.marker_symbol is not None:
            style.marker_symbol = self.marker_symbol
        if self.show_label is not None:
            style.show_label = self.show_label
        if self.show_marker is not None:
            style.show_marker = self.show_marker


# =============================================================================
# INTERSECTION RESULT
# =============================================================================

class IntersectionStatus(Enum):
    """Статус результата пересечения"""
    INVALID_INPUT = auto()
    PARALLEL = auto()
    OUTSIDE = auto()
    FOUND = auto()


@dataclass
class IntersectionResult:
    """Результат расчёта пересечения"""
    status: IntersectionStatus = IntersectionStatus.INVALID_INPUT
    intersection: Optional[Composition] = None
    line1_endpoints: Optional[tuple[Composition, Composition]] = None
    line2_endpoints: Optional[tuple[Composition, Composition]] = None


# =============================================================================
# RENDER OVERLAY
# =============================================================================

@dataclass
class OverlayLine:
    start: Composition
    end: Composition
    color: str = "gray"
    style: str = "--"
    highlight: bool = False


@dataclass
class RenderOverlay:
    """Временные элементы поверх диаграммы (для интерактива)"""
    # Точки
    projection_point: Optional[Composition] = None
    intersect_point: Optional[Composition] = None
    
    # Линии
    extrap_lines: List[OverlayLine] = field(default_factory=list)
    
    # Треугольник (для выбора области)
    triangle_overlay: Optional[List[Composition]] = None

    # Предпросмотр смеси
    mix_baseline: Optional[OverlayLine] = None
    mix_preview_point: Optional[Composition] = None
    mix_preview_color: str = "red"
    mix_preview_symbol: str = "o"
    mix_preview_size: float = 8.0

    # Подсветка (UID-ы существующих элементов)
    highlight_lines_uids: List[str] = field(default_factory=list)
    highlight_comp_uids: List[str] = field(default_factory=list)
