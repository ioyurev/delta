import uuid
from dataclasses import dataclass, field
from typing import List, Tuple, Optional, Dict
import math

class CompositionError(ValueError):
    """Ошибки связанные с композицией"""
    pass

@dataclass(frozen=True)
class Composition:
    """
    Барицентрические координаты точки в треугольнике Гиббса.
    
    Хранит СЫРЫЕ значения (a, b, c). Нормализация — отдельный метод.
    
    Инварианты:
    - Значения могут быть любыми (для промежуточных расчётов)
    - Для валидной точки внутри треугольника: a,b,c >= 0 и a+b+c > 0
    
    Examples:
        >>> comp = Composition(1, 2, 3)
        >>> comp.raw       # (1.0, 2.0, 3.0)
        >>> comp.normalized  # (0.167, 0.333, 0.5)
        >>> comp.total     # 6.0
    """
    
    a: float = 0.0
    b: float = 0.0
    c: float = 0.0
    
    def __post_init__(self) -> None:
        """Валидация при создании (если нужна строгая проверка)"""
        # Конвертируем в float на случай int
        object.__setattr__(self, 'a', float(self.a))
        object.__setattr__(self, 'b', float(self.b))
        object.__setattr__(self, 'c', float(self.c))
    
    # ==================== СВОЙСТВА ====================
    
    @property
    def total(self) -> float:
        """Сумма компонент"""
        return self.a + self.b + self.c
    
    @property
    def is_valid(self) -> bool:
        """
        Проверяет, является ли композиция валидной точкой в треугольнике.
        Валидная = все компоненты >= 0 и сумма > 0.
        """
        return (
            self.a >= 0 and 
            self.b >= 0 and 
            self.c >= 0 and 
            self.total > 0
        )
    
    # ==================== КОНВЕРТАЦИЯ ====================
    
    @property
    def normalized(self) -> Tuple[float, float, float]:
        """
        Нормализованные координаты (сумма = 1).
        
        Raises:
            CompositionError: если total == 0
        
        Returns:
            Tuple[float, float, float]: (a/total, b/total, c/total)
        """
        total = self.total
        if abs(total) < 1e-12:
            raise CompositionError(
                f"Cannot normalize composition with zero total: ({self.a}, {self.b}, {self.c})"
            )
        return (self.a / total, self.b / total, self.c / total)
    
    # ==================== ФАБРИЧНЫЕ МЕТОДЫ ====================
    
    @classmethod
    def vertex_a(cls) -> 'Composition':
        """Вершина A (100% компонента A)"""
        return cls(1.0, 0.0, 0.0)
    
    @classmethod
    def vertex_b(cls) -> 'Composition':
        """Вершина B (100% компонента B)"""
        return cls(0.0, 1.0, 0.0)
    
    @classmethod
    def vertex_c(cls) -> 'Composition':
        """Вершина C (100% компонента C)"""
        return cls(0.0, 0.0, 1.0)
    
    # ==================== СРАВНЕНИЕ ====================
    
    def normalized_is_close(self, other: 'Composition', rtol: float = 1e-5) -> bool:
        """Проверка на равенство после нормализации"""
        try:
            n1 = self.normalized
            n2 = other.normalized
            return all(
                math.isclose(n1[i], n2[i], rel_tol=rtol) 
                for i in range(3)
            )
        except CompositionError:
            return False
    
    # ==================== ПРЕДСТАВЛЕНИЕ ====================
    
    def __repr__(self) -> str:
        return f"Composition(a={self.a:.4f}, b={self.b:.4f}, c={self.c:.4f})"
    
    
@dataclass
class VisualStyle:
    """Стиль отображения (цвет, толщина и т.д.)"""
    color: str = "#000000"
    size: float = 1.0       # Толщина линии или размер точки
    line_style: str = "-"   # '-', '--', ':', '-.' для линий
    show_label: bool = True # Показывать ли текстовую метку
    marker_symbol: str = "o" # <--- НОВОЕ ПОЛЕ (форма точки: o, s, ^, v, D...)
    show_marker: bool = True


@dataclass
class NamedComposition:
    """Именованная точка состава (пользовательский объект)"""
    uid: str = field(default_factory=lambda: str(uuid.uuid4()))
    name: str = "New Composition"
    composition: Composition = field(default_factory=Composition)
    style: VisualStyle = field(default_factory=lambda: VisualStyle(size=8.0))
    
    # Смещение метки относительно точки состава (dx, dy).
    # Если None, используется авто-позиционирование.
    label_offset: Optional[Tuple[float, float]] = None

@dataclass
class TieLine:
    """Модель коноды (линии связи между составами)"""
    uid: str = field(default_factory=lambda: str(uuid.uuid4()))
    start_uid: str = ""
    end_uid: str = ""
    style: VisualStyle = field(default_factory=VisualStyle)

@dataclass
class GridSettings:
    visible: bool = False
    step: float = 0.1

@dataclass
class OverlayLine:
    """Линия для временной отрисовки (экстраполяция, проекция)"""
    start: Composition
    end: Composition
    color: str = "gray"
    style: str = "--"   # '--', ':', '-'
    highlight: bool = False

@dataclass
class RenderOverlay:
    """Контейнер для всех временных объектов на холсте"""
    highlight_lines_uids: List[str] = field(default_factory=list) # ID линий для подсветки
    extrap_lines: List[OverlayLine] = field(default_factory=list) # Временные линии
    projection_point: Optional[Composition] = None                # Синяя точка на базисе
    intersect_point: Optional[Composition] = None                 # Красный крестик пересечения
    triangle_overlay: List[Composition] = field(default_factory=list) # Зеленый треугольник

@dataclass
class CompositionUpdate:
    """DTO для частичного обновления состава"""
    name: Optional[str] = None
    a: Optional[float] = None
    b: Optional[float] = None
    c: Optional[float] = None
    
    def has_coordinate_changes(self) -> bool:
        """Проверяет, есть ли изменения координат"""
        return self.a is not None or self.b is not None or self.c is not None
    
    def apply_to(self, comp: 'NamedComposition') -> None:
        """Применяет изменения к составу"""
        if self.name is not None:
            comp.name = self.name
        
        if self.has_coordinate_changes():
            comp.composition = Composition(
                self.a if self.a is not None else comp.composition.a,
                self.b if self.b is not None else comp.composition.b,
                self.c if self.c is not None else comp.composition.c,
            )
    
    @classmethod
    def coordinate(cls, field: str, value: float) -> 'CompositionUpdate':
        """
        Фабричный метод для создания обновления одной координаты.
        
        Args:
            field: Имя поля ('a', 'b' или 'c')
            value: Новое значение
            
        Raises:
            ValueError: если field не является координатой
        """
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
    
    def apply_to(self, style: 'VisualStyle') -> None:
        """Применяет ненулевые поля к стилю"""
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

@dataclass
class ProjectData:
    """Корневой объект проекта"""
    components: List[str] = field(default_factory=lambda: ["A", "B", "C"])
    compositions: List[NamedComposition] = field(default_factory=list)
    lines: List[TieLine] = field(default_factory=list)
    grid: GridSettings = field(default_factory=GridSettings)
    is_inverted: bool = False # Перевернутый треугольник или нет
    vertex_labels_pos: Dict[str, Tuple[float, float]] = field(default_factory=dict)

@dataclass
class IntersectionResult:
    intersection: Optional[Composition] = None
    is_inside: bool = False
    overlay: Optional[RenderOverlay] = None
    message: str = ""
    status_style: str = "" # CSS стиль для лейбла (удобно для UI)