"""
Сериализация проекта с использованием Pydantic.
"""

import json
from pathlib import Path
from pydantic import ValidationError as PydanticValidationError

from core.models import ProjectData
from loguru import logger


class ProjectFileError(Exception):
    """Ошибка операции с файлом проекта"""
    pass


class ProjectSerializer:
    
    @staticmethod
    def save_to_file(project: ProjectData, filepath: str) -> None:
        """Сохраняет проект в JSON"""
        logger.info(f"Saving project to: {filepath}")
        try:
            # Pydantic v2: model_dump() с mode='json' для сериализации
            data = project.model_dump(mode='json')
            with open(filepath, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=4, ensure_ascii=False)
            logger.success("Project saved successfully")
        except Exception as e:
            logger.exception(f"Save failed: {filepath}")
            raise ProjectFileError(f"Failed to save file: {e}")
    
    @staticmethod
    def load_from_file(filepath: str) -> ProjectData:
        """
        Загружает и валидирует проект из JSON.
        
        Pydantic автоматически:
        - Проверяет типы
        - Применяет дефолты
        - Валидирует ограничения
        - Выбрасывает понятные ошибки
        """
        logger.info(f"Loading project from: {filepath}")
        path = Path(filepath)
        
        if not path.exists():
            raise ProjectFileError(f"File not found: {path.name}")
        
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except json.JSONDecodeError as e:
            raise ProjectFileError(f"Invalid JSON format: {e.msg}")
        except Exception as e:
            raise ProjectFileError(f"Read error: {e}")
        
        try:
            # Pydantic v2: model_validate() для десериализации с валидацией
            project = ProjectData.model_validate(data)
            logger.success("Project loaded and validated successfully")
            return project
            
        except PydanticValidationError as e:
            # Форматируем ошибки Pydantic в читаемый вид
            errors = []
            for err in e.errors():
                loc = " → ".join(str(x) for x in err['loc'])
                msg = err['msg']
                errors.append(f"  • {loc}: {msg}")
            
            error_text = "\n".join(errors)
            logger.error(f"Validation failed:\n{error_text}")
            
            raise ProjectFileError(
                f"Project validation failed:\n{error_text}"
            )