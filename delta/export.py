"""
Standalone-рендеринг диаграмм без Qt.

Использует matplotlib напрямую, без PlotCanvas.
"""

from matplotlib.figure import Figure

from delta.models import ProjectData, RenderOverlay
from delta.renderer import ProjectRenderer
from delta.render_layout import apply_figure_margins


def render_to_file(
    project_data: ProjectData,
    filepath: str,
    *,
    dpi: int = 150,
    figsize: tuple[float, float] = (8.0, 7.0),
    transparent: bool = False,
    overlay: RenderOverlay | None = None
) -> None:
    """
    Рендерит диаграмму в файл.
    
    Args:
        project_data: Данные проекта
        filepath: Путь к выходному файлу
        dpi: Разрешение (для растровых форматов)
        figsize: Размер (ширина, высота) в дюймах
        transparent: Прозрачный фон
        overlay: Дополнительные элементы (опционально)
    """
    # Создаём Figure без привязки к GUI
    fig = Figure(figsize=figsize)
    ax = fig.add_subplot(111)
    
    # Используем существующий Renderer
    renderer = ProjectRenderer(ax)
    renderer.draw_static_project(project_data, show_hints=False)
    
    if overlay:
        renderer.draw_dynamic_overlay(overlay, project_data.is_inverted)
    
    apply_figure_margins(fig, project_data)
    
    # Сохранение
    fig.savefig(
        filepath,
        dpi=dpi,
        bbox_inches='tight',
        transparent=transparent,
        facecolor='white' if not transparent else 'none'
    )
    
    # Явно закрываем Figure (освобождаем память)
    import matplotlib.pyplot as plt
    plt.close(fig)


def render_to_bytes(
    project_data: ProjectData,
    format: str = "png",
    **kwargs
) -> bytes:
    """
    Рендерит диаграмму в байты (для API/web).
    
    Args:
        project_data: Данные проекта
        format: Формат изображения (png, svg, pdf)
        **kwargs: Дополнительные параметры (dpi, figsize, и т.д.)
    
    Returns:
        Байты изображения
    """
    import io
    
    buffer = io.BytesIO()
    
    fig = Figure(figsize=kwargs.get('figsize', (8.0, 7.0)))
    ax = fig.add_subplot(111)
    
    renderer = ProjectRenderer(ax)
    renderer.draw_static_project(project_data, show_hints=False)
    
    apply_figure_margins(fig, project_data)
    fig.savefig(buffer, format=format, dpi=kwargs.get('dpi', 150), bbox_inches='tight')
    
    import matplotlib.pyplot as plt
    plt.close(fig)
    
    buffer.seek(0)
    return buffer.read()
