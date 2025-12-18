"""Вспомогательные функции для создания виджетов"""

from PySide6.QtWidgets import QDoubleSpinBox
from typing import Callable, Optional
from core.constants import (
    MARKER_SIZE_MIN,
    MARKER_SIZE_MAX,
    MARKER_SIZE_DEFAULT,
    LINE_WIDTH_MIN,
    LINE_WIDTH_MAX,
    LINE_WIDTH_DEFAULT
)


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


def create_marker_size_spin(value: float = MARKER_SIZE_DEFAULT, on_change: Optional[Callable[[float], None]] = None) -> QDoubleSpinBox:
    """SpinBox для размера маркера"""
    return create_double_spin(
        min_val=MARKER_SIZE_MIN,
        max_val=MARKER_SIZE_MAX,
        value=value,
        step=0.5,
        decimals=1,
        on_change=on_change
    )


def create_line_width_spin(value: float = LINE_WIDTH_DEFAULT, on_change: Optional[Callable[[float], None]] = None) -> QDoubleSpinBox:
    """SpinBox для толщины линии"""
    return create_double_spin(
        min_val=LINE_WIDTH_MIN,
        max_val=LINE_WIDTH_MAX,
        value=value,
        step=0.5,
        decimals=1,
        on_change=on_change
    )


def create_composition_spin(value: float = 0.0, on_change: Optional[Callable[[float], None]] = None) -> QDoubleSpinBox:
    """SpinBox для компонента композиции (0-1)"""
    return create_double_spin(
        min_val=0.0,
        max_val=1.0,
        value=value,
        step=0.05,
        decimals=3,
        on_change=on_change
    )
