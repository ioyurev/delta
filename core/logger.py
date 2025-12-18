import os
import sys
import ctypes
from pathlib import Path
from loguru import logger

def attach_to_parent_console():
    """
    Пытается подключиться к консоли родительского процесса (cmd/powershell).
    Нужно для GUI-приложений на Windows, чтобы видеть логи при запуске из терминала.
    """
    if sys.platform != "win32":
        return

    # Проверяем, скомпилировано ли приложение (в dev-режиме консоль и так есть)
    if not getattr(sys, 'frozen', False):
        return

    # Магическая константа Windows API
    ATTACH_PARENT_PROCESS = -1
    
    # Пытаемся подключиться к родительской консоли
    if ctypes.windll.kernel32.AttachConsole(ATTACH_PARENT_PROCESS):
        # Если получилось, переоткрываем потоки вывода
        # "CONOUT$" - это специальное имя файла для консоли вывода в Windows
        try:
            sys.stdout = open("CONOUT$", "w", encoding="utf-8")
            sys.stderr = open("CONOUT$", "w", encoding="utf-8")
        except Exception:
            pass

def get_log_dir() -> Path:
    """Определяет правильную папку для логов в зависимости от ОС и режима"""
    app_name = "Delta"
    
    if sys.platform == "win32":
        # Используем %LOCALAPPDATA%/Delta/logs
        # Это стандартный путь для записи данных приложения пользователем
        local_app_data = os.environ.get("LOCALAPPDATA")
        if local_app_data:
            base_dir = Path(local_app_data)
        else:
            base_dir = Path.home() / "AppData" / "Local"
        
        return base_dir / app_name / "logs"
    
    # Для Linux/Mac можно добавить логику XDG или Library/Logs
    # Пока fallback на папку пользователя
    return Path.home() / f".{app_name.lower()}" / "logs"

def setup_logger():
    attach_to_parent_console()
    
    log_dir = get_log_dir()
    try:
        log_dir.mkdir(parents=True, exist_ok=True)
    except Exception:
        # Fallback если совсем нет прав (крайний случай)
        log_dir = Path.cwd() / "logs"
        
    logger.remove()
    
    # Файл
    try:
        logger.add(
            log_dir / "app_{time:YYYY-MM-DD}.log",
            rotation="1 MB",
            retention=3, # Храним меньше файлов
            compression="zip",
            level="INFO",
            encoding="utf-8",
            format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{line} - {message}"
        )
    except Exception as e:
        if sys.stderr:
            print(f"Failed to setup file logger: {e}", file=sys.stderr)

    # Консоль
    if sys.stderr:
        logger.add(
            sys.stderr,
            level="DEBUG",
            format="<green>{time:HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}:{line}</cyan> - <level>{message}</level>"
        )
