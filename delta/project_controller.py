"""
Qt-обёртка над ProjectManager для интеграции с GUI.

Делегирует всю логику в ProjectManager, добавляя Qt-сигналы.
"""

from typing import List
from PySide6.QtCore import QObject, Signal

from delta.project_manager import ProjectManager
from delta.models import (
    ProjectData, NamedComposition, TieLine,
    CompositionUpdate, StyleUpdate, IntersectionResult
)


class ProjectController(QObject):
    """
    Qt-совместимый контроллер проекта.
    
    Тонкая обёртка над ProjectManager:
    - Делегирует все методы в manager
    - Преобразует callback в Qt Signal
    """
    
    data_changed = Signal()
    
    def __init__(self):
        super().__init__()
        self._manager = ProjectManager(
            on_change=self._on_manager_changed,
            enable_undo=True
        )
    
    def _on_manager_changed(self) -> None:
        """Callback от ProjectManager → Qt Signal"""
        self.data_changed.emit()

    # =========================================================================
    # ДЕЛЕГИРОВАНИЕ СВОЙСТВ
    # =========================================================================

    @property
    def project_data(self) -> ProjectData:
        return self._manager.project_data

    # =========================================================================
    # ДЕЛЕГИРОВАНИЕ ГЕТТЕРОВ
    # =========================================================================

    def has_compositions(self) -> bool:
        return self._manager.has_compositions()

    def get_composition_count(self) -> int:
        return self._manager.get_composition_count()

    def get_line_count(self) -> int:
        return self._manager.get_line_count()

    def get_components(self) -> List[str]:
        return self._manager.get_components()

    def is_inverted(self) -> bool:
        return self._manager.is_inverted()

    def get_all_compositions(self) -> List[NamedComposition]:
        return self._manager.get_all_compositions()

    def get_all_lines(self) -> List[TieLine]:
        return self._manager.get_all_lines()

    # =========================================================================
    # ДЕЛЕГИРОВАНИЕ ПОИСКА
    # =========================================================================

    def get_composition(self, uid: str) -> NamedComposition:
        return self._manager.get_composition(uid)

    def find_composition(self, uid: str):
        return self._manager.find_composition(uid)

    def get_line(self, uid: str) -> TieLine:
        return self._manager.get_line(uid)

    def find_line(self, uid: str):
        return self._manager.find_line(uid)

    def get_line_endpoints(self, line_uid: str):
        return self._manager.get_line_endpoints(line_uid)

    # =========================================================================
    # ДЕЛЕГИРОВАНИЕ CRUD
    # =========================================================================

    def create_composition(self, name: str = "New", a: float = 0.0, 
                           b: float = 0.0, c: float = 0.0,
                           show_label: bool = True, show_marker: bool = True,
                           validate: bool = True) -> str:
        return self._manager.create_composition(
            name, a, b, c, show_label, show_marker, validate
        )

    def create_line(self, start_uid: str, end_uid: str) -> str:
        return self._manager.create_line(start_uid, end_uid)

    def update_components(self, names: List[str]) -> None:
        self._manager.update_components(names)

    def update_grid(self, visible: bool, step: float) -> None:
        self._manager.update_grid(visible, step)

    def update_view_mode(self, is_inverted: bool) -> None:
        self._manager.update_view_mode(is_inverted)

    def update_composition(self, uid: str, update: CompositionUpdate, 
                           validate: bool = True) -> None:
        self._manager.update_composition(uid, update, validate)

    def update_composition_style(self, uid: str, update: StyleUpdate) -> None:
        self._manager.update_composition_style(uid, update)

    def update_line_style(self, uid: str, update: StyleUpdate) -> None:
        self._manager.update_line_style(uid, update)

    def update_line_endpoints(self, line_uid: str, start_uid: str, 
                              end_uid: str) -> None:
        self._manager.update_line_endpoints(line_uid, start_uid, end_uid)

    def set_composition_label_pos(self, uid: str, x: float, y: float) -> None:
        self._manager.set_composition_label_pos(uid, x, y)

    def set_vertex_label_pos(self, index: int, x: float, y: float) -> None:
        self._manager.set_vertex_label_pos(index, x, y)

    def delete_composition(self, uid: str) -> None:
        self._manager.delete_composition(uid)

    def delete_line(self, uid: str) -> None:
        self._manager.delete_line(uid)

    # =========================================================================
    # ДЕЛЕГИРОВАНИЕ РАСЧЁТОВ
    # =========================================================================

    def calculate_intersection(self, line1_uid: str, 
                               line2_uid: str) -> IntersectionResult:
        return self._manager.calculate_intersection(line1_uid, line2_uid)

    # =========================================================================
    # ДЕЛЕГИРОВАНИЕ СЕРИАЛИЗАЦИИ
    # =========================================================================

    def save_project(self, filepath: str) -> None:
        self._manager.save_to_file(filepath)

    def load_project(self, filepath: str) -> None:
        self._manager.load_from_file(filepath)

    def new_project(self) -> None:
        self._manager.new_project()

    # =========================================================================
    # ДЕЛЕГИРОВАНИЕ UNDO/REDO
    # =========================================================================

    def undo(self) -> bool:
        return self._manager.undo()

    def redo(self) -> bool:
        return self._manager.redo()

    def can_undo(self) -> bool:
        return self._manager.can_undo()

    def can_redo(self) -> bool:
        return self._manager.can_redo()

    def clear_undo_history(self) -> None:
        self._manager.clear_undo_history()