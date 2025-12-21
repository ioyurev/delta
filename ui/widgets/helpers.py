"""Вспомогательные функции и виджеты для UI"""

from PySide6.QtWidgets import QDoubleSpinBox, QMenu, QComboBox, QPushButton, QColorDialog, QApplication
from PySide6.QtCore import Signal, Qt
from PySide6.QtGui import QColor, QCursor, QPalette
from typing import Callable, Optional, TypeVar, ParamSpec, Sequence
from functools import wraps
from contextlib import contextmanager
from core.constants import (
    MARKER_SIZE_MIN,
    MARKER_SIZE_MAX,
    MARKER_SIZE_DEFAULT,
    LINE_WIDTH_MIN,
    LINE_WIDTH_MAX,
    LINE_WIDTH_DEFAULT
)
from core.exceptions import EntityNotFoundError

P = ParamSpec('P')
T = TypeVar('T')


# =============================================================================
# ВИДЖЕТЫ
# =============================================================================

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
