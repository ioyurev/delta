"""
Модели данных приложения на базе Pydantic.

Обеспечивает:
- Автоматическую валидацию при создании
- Сериализацию в JSON
- Чёткие сообщения об ошибках
"""

import math
import uuid
from typing import List, Tuple, Optional, Dict
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
# TIE LINE
# =============================================================================

class TieLine(BaseModel):
    """Линия связи между составами"""
    model_config = ConfigDict(validate_assignment=True)
    
    uid: str = Field(default_factory=lambda: str(uuid.uuid4()))
    start_uid: str = ""
    end_uid: str = ""
    style: VisualStyle = Field(default_factory=lambda: VisualStyle(size=LINE_WIDTH_DEFAULT))
    
    @model_validator(mode='after')
    def validate_different_endpoints(self) -> 'TieLine':
        """Start и End должны быть разными"""
        if self.start_uid and self.end_uid and self.start_uid == self.end_uid:
            raise ValueError("Line cannot connect composition to itself")
        return self


# =============================================================================
# GRID SETTINGS
# =============================================================================

class GridSettings(BaseModel):
    """Настройки сетки"""
    visible: bool = False
    step: float = Field(default=GRID_STEP_DEFAULT, ge=GRID_STEP_MIN, le=GRID_STEP_MAX)


# =============================================================================
# PROJECT DATA
# =============================================================================

class ProjectData(BaseModel):
    """Корневой объект проекта"""
    model_config = ConfigDict(validate_assignment=True)
    
    components: List[str] = Field(default_factory=lambda: ["A", "B", "C"])
    compositions: List[NamedComposition] = Field(default_factory=list)
    lines: List[TieLine] = Field(default_factory=list)
    grid: GridSettings = Field(default_factory=GridSettings)
    is_inverted: bool = False
    vertex_labels_pos: Dict[str, Tuple[float, float]] = Field(default_factory=dict)
    
    @field_validator('components')
    @classmethod
    def validate_components(cls, v: List[str]) -> List[str]:
        """Должно быть ровно 3 компонента"""
        if len(v) != 3:
            raise ValueError(f"Expected 3 components, got {len(v)}")
        return [str(c) if c else f"C{i+1}" for i, c in enumerate(v)]
    
    @model_validator(mode='after')
    def validate_line_references(self) -> 'ProjectData':
        """Проверка целостности ссылок в линиях"""
        comp_uids = {c.uid for c in self.compositions}
        
        for line in self.lines:
            if line.start_uid and line.start_uid not in comp_uids:
                raise ValueError(f"Line references unknown composition: {line.start_uid}")
            if line.end_uid and line.end_uid not in comp_uids:
                raise ValueError(f"Line references unknown composition: {line.end_uid}")
        
        return self


# =============================================================================
# OVERLAY & RENDER (остаются dataclass для простоты)
# =============================================================================

@dataclass
class OverlayLine:
    """Линия для временной отрисовки"""
    start: Composition
    end: Composition
    color: str = "gray"
    style: str = "--"
    highlight: bool = False


@dataclass
class RenderOverlay:
    """Контейнер для временных объектов на холсте"""
    highlight_lines_uids: List[str] = field(default_factory=list)
    extrap_lines: List[OverlayLine] = field(default_factory=list)
    projection_point: Optional[Composition] = None
    intersect_point: Optional[Composition] = None
    triangle_overlay: List[Composition] = field(default_factory=list)


# =============================================================================
# DTOs (остаются dataclass)
# =============================================================================

@dataclass
class CompositionUpdate:
    """DTO для частичного обновления состава"""
    name: Optional[str] = None
    a: Optional[float] = None
    b: Optional[float] = None
    c: Optional[float] = None
    
    def has_coordinate_changes(self) -> bool:
        return self.a is not None or self.b is not None or self.c is not None
    
    def apply_to(self, comp: NamedComposition) -> None:
        if self.name is not None:
            comp.name = self.name
        if self.has_coordinate_changes():
            comp.composition = Composition(
                a=self.a if self.a is not None else comp.composition.a,
                b=self.b if self.b is not None else comp.composition.b,
                c=self.c if self.c is not None else comp.composition.c,
            )
    
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