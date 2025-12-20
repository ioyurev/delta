"""
Исключения приложения.

Иерархия:
    DeltaError
    ├── EntityNotFoundError   — сущность не найдена по ID
    ├── DuplicateEntityError  — попытка создать дубликат
    └── ValidationError       — невалидные данные
"""


class DeltaError(Exception):
    """Базовое исключение приложения"""
    pass


class EntityNotFoundError(DeltaError, KeyError):
    """Сущность не найдена по ID"""
    def __init__(self, entity_type: str, uid: str):
        self.entity_type = entity_type
        self.uid = uid
        super().__init__(f"{entity_type} not found: {uid}")


class DuplicateEntityError(DeltaError, ValueError):
    """Попытка создать дубликат"""
    def __init__(self, message: str = "Entity already exists"):
        super().__init__(message)


class ValidationError(DeltaError, ValueError):
    """Невалидные входные данные"""
    def __init__(self, message: str):
        super().__init__(message)
