"""
Qt-обёртка над ProjectManager для интеграции с GUI.

Наследует ProjectManager (вся бизнес-логика доступна напрямую),
добавляя только Qt-сигнал data_changed.

SSOT/DRY: методы НЕ дублируются. Новый метод в ProjectManager
автоматически доступен в контроллере.
"""

from typing import List, Optional
from PySide6.QtCore import QObject, Signal

from delta.project_manager import ProjectManager


class ProjectController(QObject, ProjectManager):
    """
    Qt-совместимый контроллер проекта.

    Весь API унаследован от ProjectManager.
    Добавляет:
    - Qt Signal data_changed (вместо callback)
    - алиасы save_project/load_project для совместимости с GUI-кодом
    """

    data_changed = Signal()

    def __init__(self):
        QObject.__init__(self)
        ProjectManager.__init__(
            self,
            on_change=self._emit_data_changed,
            enable_undo=True,
        )

    def _emit_data_changed(self) -> None:
        self.data_changed.emit()

    # =========================================================================
    # АЛИАСЫ (имена, отличающиеся от ProjectManager)
    # =========================================================================

    def save_project(self, filepath: str) -> None:
        self.save_to_file(filepath)

    def load_project(self, filepath: str) -> None:
        self.load_from_file(filepath)

    def get_component_molar_masses(self) -> List[Optional[float]]:
        return list(self.project_data.component_molar_masses)
