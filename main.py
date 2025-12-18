import sys
from PySide6.QtWidgets import QApplication
from ui.main_window import MainWindow
from core.logger import setup_logger
from loguru import logger

try:
    import pyi_splash # type: ignore
except ImportError:
    pyi_splash = None

# Функция-перехватчик
def exception_hook(exc_type, exc_value, exc_traceback):
    # opt(exception=...) позволяет гибко настроить формат вывода ошибки
    logger.opt(exception=(exc_type, exc_value, exc_traceback)).critical("Uncaught exception!")
    # Вызываем старый хук, чтобы Qt тоже узнал об ошибке (опционально)
    sys.__excepthook__(exc_type, exc_value, exc_traceback)


if __name__ == "__main__":
    setup_logger()  # Настраиваем loguru
    
    # Подключаем перехватчик
    sys.excepthook = exception_hook
    
    app = QApplication(sys.argv)
    app.setStyle('Fusion')
    
    # ... инициализация окна ...
    w = MainWindow()
    w.show()
    
    # --- ЗАКРЫВАЕМ SPLASH SCREEN ---
    if pyi_splash:
        pyi_splash.close()
    
    # Также можно обернуть запуск в catch на всякий случай
    with logger.catch():
        sys.exit(app.exec())
