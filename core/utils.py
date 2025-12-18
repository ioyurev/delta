import sys
from pathlib import Path

def resource_path(relative_path: str) -> str:
    """
    Возвращает абсолютный путь к ресурсу.
    Работает как в IDE, так и в собранном EXE.
    """
    if getattr(sys, 'frozen', False):
        base_path = Path(sys._MEIPASS) # type: ignore
    else:
        base_path = Path(__file__).parent.parent
    return str(base_path / relative_path)
