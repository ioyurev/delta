"""
Миграция проектных файлов между версиями схемы данных.

SSOT для всех миграций. Модели (models.py) занимаются только
валидацией текущей версии, не знают про старые форматы.

Версии схемы:
    None / отсутствует — оригинальный формат (до версионирования)
    "1.0"             — render_settings, curve_mode в CurveLine

Добавление новой версии:
    1. Написать функцию _migrate_X_to_Y(data: dict) -> dict
    2. Добавить её в MIGRATION_CHAIN
    3. Обновить CURRENT_VERSION
"""

from typing import Any
from loguru import logger

CURRENT_VERSION = "1.1"

# =========================================================================
# МИГРАТОРЫ: каждый — чистая функция dict → dict
# =========================================================================


def _migrate_none_to_1_0(data: dict) -> dict:
    """
    Pre-versioned → 1.0

    Изменения:
    - top-level lock_aspect → render_settings.lock_aspect
    - CurveLine без curve_mode → curve_mode = "polynomial"
    """
    # lock_aspect → render_settings
    legacy_lock_aspect = data.pop("lock_aspect", None)
    if "render_settings" not in data:
        if legacy_lock_aspect is not None:
            data["render_settings"] = {"lock_aspect": legacy_lock_aspect}
    elif legacy_lock_aspect is not None:
        rs = data["render_settings"]
        if isinstance(rs, dict):
            rs.setdefault("lock_aspect", legacy_lock_aspect)

    # CurveLine: добавляем curve_mode = "polynomial" для обратной совместимости
    for cline in data.get("curve_lines", []):
        if isinstance(cline, dict) and "curve_mode" not in cline:
            cline["curve_mode"] = "polynomial"

    data["version"] = "1.0"
    return data


def _migrate_1_0_to_1_1(data: dict) -> dict:
    """
    1.0 → 1.1

    Изменения:
    - Добавлено поле hatch_regions (пустой список по умолчанию)
    """
    data.setdefault("hatch_regions", [])
    data["version"] = "1.1"
    return data


# =========================================================================
# ЦЕПОЧКА МИГРАЦИЙ (порядок важен)
# =========================================================================

# Формат: (from_version, to_version, migrator_function)
MIGRATION_CHAIN: list[tuple[str | None, str, Any]] = [
    (None, "1.0", _migrate_none_to_1_0),
    ("1.0", "1.1", _migrate_1_0_to_1_1),
]


# =========================================================================
# ПУБЛИЧНЫЙ API
# =========================================================================


def migrate_project_data(data: dict) -> dict:
    """
    Применяет все необходимые миграции к raw dict проекта.

    Вызывается ПЕРЕД ProjectData.model_validate(data).
    Не модифицирует файл на диске — только данные в памяти.

    Args:
        data: Сырой словарь, загруженный из JSON

    Returns:
        Мигрированный словарь с актуальной версией
    """
    current = data.get("version")

    if current == CURRENT_VERSION:
        return data

    for from_ver, to_ver, migrator in MIGRATION_CHAIN:
        if current == from_ver:
            logger.info(f"Migrating project: {from_ver!r} → {to_ver!r}")
            data = migrator(data)
            current = data.get("version")

    if current != CURRENT_VERSION:
        logger.warning(
            f"Unknown project version: {current!r}. "
            f"Expected {CURRENT_VERSION!r}. Loading as-is."
        )

    return data
