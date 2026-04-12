"""Вспомогательные функции и виджеты для UI"""

from dataclasses import dataclass
from functools import wraps
from contextlib import contextmanager

from PySide6.QtWidgets import (
    QDoubleSpinBox, QFormLayout, QMenu, QComboBox, QPushButton, QColorDialog,
    QApplication, QTableWidget, QHBoxLayout, QLabel, QWidget,
)
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QColor, QCursor, QPalette, QKeyEvent
from typing import Callable, Optional, TypeVar, ParamSpec, Sequence
from delta.constants import (
    MARKER_SIZE_MIN,
    MARKER_SIZE_MAX,
    MARKER_SIZE_DEFAULT,
    LINE_WIDTH_MIN,
    LINE_WIDTH_MAX,
    LINE_WIDTH_DEFAULT
)
from delta.exceptions import EntityNotFoundError

P = ParamSpec('P')
T = TypeVar('T')


# =============================================================================
# MATHTEXT → UNICODE (подстрочные/надстрочные символы, греческий алфавит)
# =============================================================================

_SUBSCRIPT: dict[str, str] = {
    "0": "₀", "1": "₁", "2": "₂", "3": "₃", "4": "₄",
    "5": "₅", "6": "₆", "7": "₇", "8": "₈", "9": "₉",
    "+": "₊", "-": "₋", "=": "₌", "(": "₍", ")": "₎",
    "a": "ₐ", "e": "ₑ", "o": "ₒ", "x": "ₓ",
    "h": "ₕ", "k": "ₖ", "l": "ₗ", "m": "ₘ", "n": "ₙ",
    "p": "ₚ", "s": "ₛ", "t": "ₜ", "i": "ᵢ", "r": "ᵣ",
    "u": "ᵤ", "v": "ᵥ",
}

_SUPERSCRIPT: dict[str, str] = {
    "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴",
    "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹",
    "+": "⁺", "-": "⁻", "=": "⁼", "(": "⁽", ")": "⁾",
    "a": "ᵃ", "b": "ᵇ", "c": "ᶜ", "d": "ᵈ", "e": "ᵉ",
    "f": "ᶠ", "g": "ᵍ", "h": "ʰ", "i": "ⁱ", "j": "ʲ",
    "k": "ᵏ", "l": "ˡ", "m": "ᵐ", "n": "ⁿ", "o": "ᵒ",
    "p": "ᵖ", "r": "ʳ", "s": "ˢ", "t": "ᵗ", "u": "ᵘ",
    "v": "ᵛ", "w": "ʷ", "x": "ˣ", "y": "ʸ", "z": "ᶻ",
}

_GREEK: dict[str, str] = {
    "alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ",
    "epsilon": "ε", "zeta": "ζ", "eta": "η", "theta": "θ",
    "iota": "ι", "kappa": "κ", "lambda": "λ", "mu": "μ",
    "nu": "ν", "xi": "ξ", "pi": "π", "rho": "ρ",
    "sigma": "σ", "tau": "τ", "upsilon": "υ", "phi": "φ",
    "chi": "χ", "psi": "ψ", "omega": "ω",
    "Alpha": "Α", "Beta": "Β", "Gamma": "Γ", "Delta": "Δ",
    "Epsilon": "Ε", "Zeta": "Ζ", "Eta": "Η", "Theta": "Θ",
    "Iota": "Ι", "Kappa": "Κ", "Lambda": "Λ", "Mu": "Μ",
    "Nu": "Ν", "Xi": "Ξ", "Pi": "Π", "Rho": "Ρ",
    "Sigma": "Σ", "Tau": "Τ", "Upsilon": "Υ", "Phi": "Φ",
    "Chi": "Χ", "Psi": "Ψ", "Omega": "Ω",
    "cdot": "·", "times": "×", "pm": "±", "infty": "∞",
}


def _apply_script(chars: str, table: dict[str, str]) -> str:
    """Применяет таблицу sub/superscript к каждому символу (fallback — оригинал)."""
    return "".join(table.get(c, c) for c in chars)


def _parse_math(s: str) -> str:
    """Разбирает строку в math-режиме matplotlib MathText → unicode."""
    out: list[str] = []
    i = 0
    n = len(s)
    while i < n:
        c = s[i]
        if c == "\\":
            # Команда: читаем буквы до конца
            j = i + 1
            while j < n and s[j].isalpha():
                j += 1
            cmd = s[i + 1 : j]
            out.append(_GREEK.get(cmd, cmd))
            i = j
        elif c in ("_", "^"):
            table = _SUBSCRIPT if c == "_" else _SUPERSCRIPT
            i += 1
            if i >= n:
                break
            if s[i] == "{":
                # Ищем закрывающую }
                depth, j = 1, i + 1
                while j < n and depth:
                    if s[j] == "{":
                        depth += 1
                    elif s[j] == "}":
                        depth -= 1
                    j += 1
                group = _parse_math(s[i + 1 : j - 1])
                out.append(_apply_script(group, table))
                i = j
            else:
                out.append(table.get(s[i], s[i]))
                i += 1
        elif c in ("{", "}"):
            i += 1  # скобки группировки — просто пропускаем
        else:
            out.append(c)
            i += 1
    return "".join(out)


def mathtext_to_plain(text: str) -> str:
    """
    Преобразует matplotlib MathText-строку в читаемый unicode-текст.

    Поддерживает:
    - подстрочные ``$_2$``, ``$_{3-x}$``
    - надстрочные ``$^2$``, ``$^{n+1}$``
    - греческие буквы ``$\\alpha$``, ``$\\Omega$``
    - смешанные имена ``Th$_3$P$_4$``, ``$Gd_{2}S_3$``

    Символы без unicode-аналога остаются как есть.
    Строки без ``$`` возвращаются без изменений.
    """
    if "$" not in text:
        return text
    parts = text.split("$")
    result: list[str] = []
    for idx, part in enumerate(parts):
        result.append(_parse_math(part) if idx % 2 else part)
    return "".join(result)


# =============================================================================
# МАРКЕРЫ — общие константы и данные
# =============================================================================

MARKER_SYMBOLS: dict[str, str] = {
    "Circle (●)": "o",
    "Square (■)": "s",
    "Triangle Up (▲)": "^",
    "Triangle Down (▼)": "v",
    "Diamond (◆)": "D",
    "Star (★)": "*",
    "Cross (x)": "x",
    "Plus (+)": "P",
}


@dataclass
class MarkerStyleData:
    """Параметры стиля маркера."""
    color: str
    symbol: str
    size: float


# =============================================================================
# ВИДЖЕТЫ
# =============================================================================

class MarkerStyleWidget(QWidget):
    """
    Переиспользуемый виджет параметров стиля маркера.

    Показывает три строки: Color / Size / Shape.
    Испускает ``style_changed(MarkerStyleData)`` при любом изменении.
    """

    style_changed = Signal(object)   # MarkerStyleData

    def __init__(
        self,
        color: str = "#000000",
        symbol: str = "o",
        size: float = MARKER_SIZE_DEFAULT,
        parent: Optional[QWidget] = None,
    ) -> None:
        super().__init__(parent)
        form = QFormLayout(self)
        form.setContentsMargins(0, 0, 0, 0)
        form.setSpacing(6)

        self._btn_color = ColorPickerButton(color)
        self._btn_color.setToolTip("Marker color")
        form.addRow("Color:", self._btn_color)

        self._spin_size = create_marker_size_spin(value=size)
        self._spin_size.setToolTip("Marker size in points")
        form.addRow("Size:", self._spin_size)

        self._cb_symbol = QComboBox()
        for name, code in MARKER_SYMBOLS.items():
            self._cb_symbol.addItem(name, code)
        idx = self._cb_symbol.findData(symbol)
        if idx >= 0:
            self._cb_symbol.setCurrentIndex(idx)
        self._cb_symbol.setToolTip("Marker shape")
        form.addRow("Shape:", self._cb_symbol)

        self._btn_color.color_changed.connect(self._emit)
        self._spin_size.valueChanged.connect(self._emit)
        self._cb_symbol.currentIndexChanged.connect(self._emit)

    def get_data(self) -> MarkerStyleData:
        return MarkerStyleData(
            color=self._btn_color.color(),
            symbol=self._cb_symbol.currentData(),
            size=self._spin_size.value(),
        )

    def set_data(self, data: MarkerStyleData) -> None:
        self._btn_color.set_color(data.color)
        self._spin_size.setValue(data.size)
        idx = self._cb_symbol.findData(data.symbol)
        if idx >= 0:
            self._cb_symbol.setCurrentIndex(idx)

    def _emit(self, *_: object) -> None:
        self.style_changed.emit(self.get_data())


class CopyableTableWidget(QTableWidget):
    """
    QTableWidget с поддержкой Ctrl+C: копирует все выделенные ячейки
    в буфер обмена в виде TSV-таблицы (Tab-separated values).
    """

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if (event.key() == Qt.Key.Key_C
                and event.modifiers() == Qt.KeyboardModifier.ControlModifier):
            self._copy_selection()
        else:
            super().keyPressEvent(event)

    def _copy_selection(self) -> None:
        ranges = self.selectedRanges()
        if not ranges:
            return

        min_row = min(r.topRow() for r in ranges)
        max_row = max(r.bottomRow() for r in ranges)
        min_col = min(r.leftColumn() for r in ranges)
        max_col = max(r.rightColumn() for r in ranges)

        lines: list[str] = []
        for row in range(min_row, max_row + 1):
            cells: list[str] = []
            for col in range(min_col, max_col + 1):
                item = self.item(row, col)
                cells.append(item.text() if item else "")
            lines.append("\t".join(cells))

        QApplication.clipboard().setText("\n".join(lines))


class ColorPickerButton(QPushButton):
    """
    Кнопка выбора цвета с превью.
    
    Отображает текущий цвет как фон кнопки и открывает QColorDialog по клику.
    
    Signals:
        color_changed(str): Испускается при выборе нового цвета (hex формат)
    
    Example:
        btn = ColorPickerButton("#FF0000")
        btn.color_changed.connect(lambda c: print(f"New color: {c}"))
        
        # Получить текущий цвет
        current = btn.color()  # "#FF0000"
        
        # Установить программно
        btn.set_color("#00FF00")
    """
    
    color_changed = Signal(str)
    
    def __init__(self, initial_color: str = "#000000", parent=None):
        super().__init__(parent)
        self._color = initial_color
        self._update_appearance()
        self.clicked.connect(self._on_clicked)
        
        # Минимальная ширина для читаемости hex-кода
        self.setMinimumWidth(100)
        
        # Добавляем tooltip для кнопки выбора цвета
        self.setToolTip("Click to choose color")
    
    def color(self) -> str:
        """Возвращает текущий цвет в hex формате"""
        return self._color
    
    def set_color(self, hex_color: str) -> None:
        """Устанавливает цвет программно (без испускания сигнала)"""
        self._color = hex_color
        self._update_appearance()
    
    def _update_appearance(self) -> None:
        """Обновляет внешний вид кнопки"""
        # Определяем контрастный цвет текста
        qcolor = QColor(self._color)
        # Простая формула яркости: если светлый фон — тёмный текст
        luminance = 0.299 * qcolor.red() + 0.587 * qcolor.green() + 0.114 * qcolor.blue()
        text_color = "#000000" if luminance > 128 else "#FFFFFF"
        
        self.setStyleSheet(f"""
            QPushButton {{
                background-color: {self._color};
                color: {text_color};
                border: 1px solid #555;
                border-radius: 3px;
                padding: 5px 10px;
                font-family: monospace;
            }}
            QPushButton:hover {{
                border: 2px solid #333;
            }}
        """)
        self.setText(self._color.upper())
    
    def _on_clicked(self) -> None:
        """Открывает диалог выбора цвета"""
        dialog = QColorDialog(QColor(self._color), self)
        
        if dialog.exec():
            new_color = dialog.selectedColor().name()
            if new_color != self._color:
                self._color = new_color
                self._update_appearance()
                self.color_changed.emit(self._color)


# =============================================================================
# PICKABLE COORD WIDGET
# =============================================================================

class PickableCoordWidget(QWidget):
    """
    Ввод одной барицентрической точки: три спинбокса A/B/C + кнопка выбора на холсте.

    Signals:
        value_changed(Composition): испускается при изменении любого спинбокса
        pick_requested():           испускается при нажатии кнопки «📍 Pick»
    """

    value_changed = Signal(object)   # Composition
    pick_requested = Signal()

    def __init__(
        self,
        label_a: str = "A",
        label_b: str = "B",
        label_c: str = "C",
        parent: QWidget | None = None,
    ) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        self._spin_a = create_coord_spin()
        self._spin_b = create_coord_spin()
        self._spin_c = create_coord_spin()

        for lbl, spin in [
            (label_a, self._spin_a),
            (label_b, self._spin_b),
            (label_c, self._spin_c),
        ]:
            layout.addWidget(QLabel(lbl))
            layout.addWidget(spin)
            spin.valueChanged.connect(self._on_spin_changed)

        self._btn_pick = QPushButton("📍")
        self._btn_pick.setToolTip("Pick position from canvas by clicking on diagram")
        self._btn_pick.setFixedWidth(30)
        self._btn_pick.clicked.connect(self.pick_requested)
        layout.addWidget(self._btn_pick)

        self._block = False

    def value(self) -> 'object':
        from delta.models import Composition
        return Composition(
            a=self._spin_a.value(),
            b=self._spin_b.value(),
            c=self._spin_c.value(),
        )

    def set_value(self, comp: 'object') -> None:
        self._block = True
        self._spin_a.setValue(getattr(comp, 'a', 0.0))
        self._spin_b.setValue(getattr(comp, 'b', 0.0))
        self._spin_c.setValue(getattr(comp, 'c', 0.0))
        self._block = False

    def _on_spin_changed(self) -> None:
        if not self._block:
            self.value_changed.emit(self.value())


# =============================================================================
# ФАБРИКИ SPINBOX
# =============================================================================

def create_double_spin(
    min_val: float = 0.0,
    max_val: float = 1.0,
    value: float = 0.0,
    step: float = 0.1,
    decimals: int = 2,
    on_change: Optional[Callable[[float], None]] = None
) -> QDoubleSpinBox:
    """Создаёт настроенный QDoubleSpinBox"""
    spin = QDoubleSpinBox()
    spin.setRange(min_val, max_val)
    spin.setValue(value)
    spin.setSingleStep(step)
    spin.setDecimals(decimals)
    
    if on_change:
        spin.valueChanged.connect(on_change)
    
    return spin


def create_marker_size_spin(
    value: float = MARKER_SIZE_DEFAULT, 
    on_change: Optional[Callable[[float], None]] = None
) -> QDoubleSpinBox:
    """SpinBox для размера маркера"""
    return create_double_spin(
        min_val=MARKER_SIZE_MIN,
        max_val=MARKER_SIZE_MAX,
        value=value,
        step=0.5,
        decimals=1,
        on_change=on_change
    )


def create_line_width_spin(
    value: float = LINE_WIDTH_DEFAULT, 
    on_change: Optional[Callable[[float], None]] = None
) -> QDoubleSpinBox:
    """SpinBox для толщины линии"""
    return create_double_spin(
        min_val=LINE_WIDTH_MIN,
        max_val=LINE_WIDTH_MAX,
        value=value,
        step=0.5,
        decimals=1,
        on_change=on_change
    )


def create_composition_spin(
    value: float = 0.0,
    on_change: Optional[Callable[[float], None]] = None
) -> QDoubleSpinBox:
    """SpinBox для компонента композиции (0-1)"""
    return create_double_spin(
        min_val=0.0,
        max_val=1.0,
        value=value,
        step=0.05,
        decimals=3,
        on_change=on_change
    )


def create_coord_spin(value: float = 0.0) -> QDoubleSpinBox:
    """
    SpinBox для ввода барицентрической координаты.

    Принимает ненормированные значения (0–1000): пользователь может
    ввести, например, 30/20/50 — нормализация выполняется в логике программы.
    Используется в таблице guide-точек и аналогичных таблицах координат.
    """
    spin = create_double_spin(
        min_val=0.0,
        max_val=1000.0,
        value=value,
        step=0.01,
        decimals=4,
    )
    spin.setFrame(False)
    return spin


# =============================================================================
# ДЕКОРАТОРЫ
# =============================================================================

def handle_entity_errors(func: Callable[P, T]) -> Callable[P, T | None]:
    """
    Декоратор для методов UI — перехватывает EntityNotFoundError.
    При ошибке просто возвращает None (операция отменяется молча).
    """
    @wraps(func)
    def wrapper(*args: P.args, **kwargs: P.kwargs) -> T | None:
        try:
            return func(*args, **kwargs)
        except EntityNotFoundError:
            return None
    return wrapper


# =============================================================================
# УТИЛИТЫ МЕНЮ
# =============================================================================

MenuItem = tuple[str, Callable[[], None], str] | tuple[str, Callable[[], bool], str] | None

def build_menu(menu: QMenu, items: list[MenuItem]) -> None:
    """
    Строит меню из декларативного описания.
    
    Args:
        menu: Меню для заполнения
        items: Список элементов. None = разделитель.
    """
    for item in items:
        if item is None:
            menu.addSeparator()
        else:
            label, callback, shortcut = item
            if shortcut:
                menu.addAction(label, callback, shortcut)
            else:
                menu.addAction(label, callback)


# =============================================================================
# УТИЛИТЫ COMBOBOX
# =============================================================================

def populate_combo(
    combo: QComboBox,
    items: Sequence[T],
    get_text: Callable[[T], str],
    get_data: Callable[[T], str],
    preserve_selection: bool = True
) -> None:
    """
    Универсальное заполнение ComboBox.
    
    Args:
        combo: Виджет для заполнения
        items: Список элементов
        get_text: Функция получения текста для отображения
        get_data: Функция получения данных (обычно uid)
        preserve_selection: Сохранять ли текущий выбор
    """
    current = combo.currentData() if preserve_selection else None
    
    combo.blockSignals(True)
    combo.clear()
    
    for item in items:
        combo.addItem(get_text(item), get_data(item))
    
    if current is not None:
        idx = combo.findData(current)
        if idx >= 0:
            combo.setCurrentIndex(idx)
    
    combo.blockSignals(False)


@contextmanager
def wait_cursor():
    """
    Контекстный менеджер для отображения курсора ожидания.
    
    Example:
        with wait_cursor():
            heavy_operation()
    """
    QApplication.setOverrideCursor(QCursor(Qt.CursorShape.WaitCursor))
    try:
        yield
    finally:
        QApplication.restoreOverrideCursor()


# =============================================================================

# Стили для сообщений в Analysis Panel (устаревшие, используются для обратной совместимости)
STYLE_MESSAGE_SUCCESS = "color: green; font-weight: bold; background: #e0f0e0; padding: 10px; border-radius: 4px;"
STYLE_MESSAGE_WARNING = "color: #856404; font-weight: bold; background: #fff3cd; padding: 10px; border-radius: 4px;"
STYLE_MESSAGE_ERROR = "color: #721c24; font-weight: bold; background: #f8d7da; padding: 10px; border-radius: 4px;"
STYLE_MESSAGE_DEFAULT = "font-weight: bold; padding: 10px; background: #f0f0f0; border-radius: 4px;"


# =============================================================================

# Адаптивные цвета для тёмной/светлой темы

def is_dark_theme() -> bool:
    """
    Определяет, используется ли тёмная тема.
    
    Returns:
        True если текущая тема тёмная, False если светлая
    """
    palette = QApplication.palette()
    bg_color = palette.color(QPalette.ColorRole.Window)
    # Если яркость фона < 128, это тёмная тема
    return bg_color.lightness() < 128


def get_adaptive_colors() -> dict[str, str]:
    """
    Возвращает словарь цветов, адаптированных к текущей теме.
    
    Returns:
        Словарь с цветами для различных элементов UI
    """
    if is_dark_theme():
        return {
            # Фоны
            "bg_primary": "#2d2d2d",
            "bg_secondary": "#3d3d3d",
            "bg_success": "#1e3a1e",
            "bg_warning": "#3d3520",
            "bg_error": "#3d1e1e",
            "bg_info": "#1e2d3d",
            
            # Текст
            "text_primary": "#e0e0e0",
            "text_secondary": "#a0a0a0",
            "text_success": "#80c080",
            "text_warning": "#d4a84d",
            "text_error": "#e08080",
            
            # Границы
            "border": "#555555",
        }
    else:
        return {
            # Фоны
            "bg_primary": "#ffffff",
            "bg_secondary": "#f5f5f5",
            "bg_success": "#d4edda",
            "bg_warning": "#fff3cd",
            "bg_error": "#f8d7da",
            "bg_info": "#e7f3ff",
            
            # Текст
            "text_primary": "#333333",
            "text_secondary": "#666666",
            "text_success": "#155724",
            "text_warning": "#856404",
            "text_error": "#721c24",
            
            # Границы
            "border": "#cccccc",
        }


def get_message_style(style_type: str) -> str:
    """
    Возвращает CSS-стиль для сообщений, адаптированный к теме.
    
    Args:
        style_type: "success" | "warning" | "error" | "default"
    
    Returns:
        CSS-строка для стилизации сообщения
    """
    colors = get_adaptive_colors()
    
    base_style = "font-weight: bold; padding: 10px; border-radius: 4px;"
    
    if style_type == "success":
        return f"color: {colors['text_success']}; background: {colors['bg_success']}; {base_style}"
    elif style_type == "warning":
        return f"color: {colors['text_warning']}; background: {colors['bg_warning']}; {base_style}"
    elif style_type == "error":
        return f"color: {colors['text_error']}; background: {colors['bg_error']}; {base_style}"
    else:
        return f"color: {colors['text_primary']}; background: {colors['bg_secondary']}; {base_style}"


def get_overlay_style() -> str:
    """
    Возвращает стиль для координатного overlay.
    
    Returns:
        CSS-строка для стилизации overlay
    """
    colors = get_adaptive_colors()
    return f"""
        QLabel {{
            background-color: {colors['bg_primary']};
            border: 1px solid {colors['border']};
            border-radius: 4px;
            padding: 6px;
            font-family: monospace;
            font-weight: bold;
            font-size: 12px;
            color: {colors['text_primary']};
        }}
    """


def get_table_cell_style(style_type: str) -> str:
    """
    Возвращает стиль для ячейки таблицы, адаптированный к теме.
    
    Args:
        style_type: "success" | "warning" | "error" | "default"
    
    Returns:
        CSS-строка для стилизации ячейки таблицы
    """
    colors = get_adaptive_colors()
    
    base_style = "padding: 4px; border: 1px solid #ccc; text-align: center;"
    
    if style_type == "success":
        return f"background-color: {colors['bg_success']}; color: {colors['text_success']}; {base_style}"
    elif style_type == "warning":
        return f"background-color: {colors['bg_warning']}; color: {colors['text_warning']}; {base_style}"
    elif style_type == "error":
        return f"background-color: {colors['bg_error']}; color: {colors['text_error']}; {base_style}"
    else:
        return f"background-color: {colors['bg_secondary']}; color: {colors['text_primary']}; {base_style}"


def get_normal_cell_color() -> QColor:
    """Возвращает стандартный цвет фона ячейки таблицы (адаптивный)."""
    return QApplication.palette().base().color()


def get_cell_highlight_color(highlight_type: str) -> QColor:
    """
    Возвращает цвет подсветки ячейки таблицы.
    
    Args:
        highlight_type: "error" | "warning" | "invalid"
    
    Returns:
        QColor для подсветки ячейки
    """
    if is_dark_theme():
        if highlight_type == "error":
            return QColor(100, 40, 40)
        elif highlight_type == "warning":
            return QColor(80, 70, 30)
        else:  # invalid
            return QColor(60, 40, 40)
    else:
        if highlight_type == "error":
            return QColor(255, 200, 200)
        elif highlight_type == "warning":
            return QColor(255, 255, 200)
        else:  # invalid
            return QColor(255, 230, 230)
