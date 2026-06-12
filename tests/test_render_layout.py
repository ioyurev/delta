import math
from matplotlib.figure import Figure

from delta.models import ProjectData, RenderSettings, FigureMargins
from delta.render_layout import apply_figure_margins


def test_apply_figure_margins():
    fig = Figure()

    project = ProjectData(
        components=["A", "B", "C"],
        render_settings=RenderSettings(
            figure_margins=FigureMargins(
                left=0.10,
                right=0.20,
                top=0.15,
                bottom=0.05,
            )
        ),
    )

    apply_figure_margins(fig, project)

    sp = fig.subplotpars
    assert math.isclose(sp.left, 0.10)
    assert math.isclose(sp.right, 0.80)
    assert math.isclose(sp.top, 0.85)
    assert math.isclose(sp.bottom, 0.05)
