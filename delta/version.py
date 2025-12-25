from importlib.metadata import version, PackageNotFoundError

def get_app_version() -> str:
    """
    Получает версию пакета через importlib.metadata.
    Работает, если пакет установлен в текущее окружение.
    """
    try:
        # ВАЖНО: Имя здесь должно совпадать с name в pyproject.toml
        return version("delta")
    except PackageNotFoundError:
        return "Unknown (Package not found)"