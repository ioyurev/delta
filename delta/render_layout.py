from matplotlib.figure import Figure

from delta.models import ProjectData


def apply_figure_margins(fig: Figure, project_data: ProjectData) -> None:
    """
    Применяет отступы figure из project_data.render_settings.figure_margins.

    SSOT:
        Источник истины — только ProjectData.render_settings.figure_margins.
    """
    m = project_data.render_settings.figure_margins
    fig.subplots_adjust(
        left=m.left,
        right=1.0 - m.right,
        top=1.0 - m.top,
        bottom=m.bottom,
    )
