"""Базовые классы для диалогов"""

from PySide6.QtWidgets import QDialog, QVBoxLayout, QHBoxLayout, QPushButton
from PySide6.QtCore import Qt
from typing import TypeVar, Generic
from abc import abstractmethod

T = TypeVar('T')


class BaseFormDialog(QDialog, Generic[T]):
    """
    Базовый диалог с кнопками OK/Cancel.
    
    Наследники должны реализовать:
        - _init_form(): добавление полей формы в self._layout
        - get_data() -> T: возврат результата
    """
    
    def __init__(self, title: str, width: int = 350, parent=None):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.setFixedWidth(width)
        self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowContextHelpButtonHint)
        
        self._layout = QVBoxLayout(self)
        self._init_form()
        self._add_buttons()
    
    @abstractmethod
    def _init_form(self) -> None:
        """Переопределить для добавления полей формы в self._layout"""
        pass
    
    @abstractmethod
    def get_data(self) -> T:
        """Возвращает результат диалога"""
        pass
    
    def _add_buttons(self) -> None:
        """Добавляет стандартные кнопки OK/Cancel"""
        btns = QHBoxLayout()
        
        btn_ok = QPushButton("OK")
        btn_ok.clicked.connect(self.accept)
        
        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        
        btns.addWidget(btn_ok)
        btns.addWidget(btn_cancel)
        self._layout.addLayout(btns)
