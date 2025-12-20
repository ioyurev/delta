from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QSizePolicy
from typing import Optional, Any

from core.models import Composition, RenderOverlay, ProjectData

from .renderer import ProjectRenderer
from .interactor import CanvasInteractor


class PlotCanvas(FigureCanvasQTAgg):
    """
    Главный виджет холста.
    """
    # Проксируем сигналы от Interactor наружу
    mouse_moved = Signal(Composition)
    annotation_dropped = Signal(str, float, float)
    vertex_label_dropped = Signal(int, float, float)

    def __init__(self, parent=None):
        self.fig = Figure()
        self.ax = self.fig.add_subplot(111)
        self.ax.set_aspect('equal')
        self.fig.subplots_adjust(left=0, right=1, top=1, bottom=0)
        
        super().__init__(self.fig)
        self.setParent(parent)
        self.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Ignored)
        
        # Компоненты
        self.project_renderer = ProjectRenderer(self.ax)
        self.interactor = CanvasInteractor(self)
        
        # Состояние
        self.current_project: Optional[ProjectData] = None
        self.highlighted_line_uid: Optional[str] = None
        self._static_background = None
        self._needs_full_redraw = True
        self._cached_overlay_uids: set[str] = set()
        
        # Подключение сигналов
        self._connect_signals()

    def _connect_signals(self) -> None:
        self.mpl_connect('motion_notify_event', self.interactor.on_move)  # type: ignore
        self.mpl_connect('button_press_event', self.interactor.on_press)  # type: ignore
        self.mpl_connect('button_release_event', self.interactor.on_release)  # type: ignore
        
        self.interactor.mouse_moved.connect(self.mouse_moved)
        self.interactor.annotation_dropped.connect(self.annotation_dropped)
        self.interactor.vertex_label_dropped.connect(self.vertex_label_dropped)

    # === Public API ===

    def set_highlight_line(self, uid: Optional[str]) -> None:
        self.highlighted_line_uid = uid
        current_uids = list(self._cached_overlay_uids)
        if uid:
            current_uids.append(uid)
            
        self.project_renderer.apply_highlights(current_uids)
        self.draw_idle()

    def draw_project(
        self, 
        project_data: ProjectData, 
        overlay_data: Optional[RenderOverlay] = None, 
        force_full_redraw: bool = False
    ) -> None:
        if self.interactor._is_dragging:
            return
        
        self.current_project = project_data
        
        new_highlights = overlay_data.highlight_lines_uids if overlay_data else []
        self._cached_overlay_uids = set(new_highlights)
        
        if self.highlighted_line_uid:
            new_highlights = list(new_highlights) + [self.highlighted_line_uid]

        need_redraw = (
            force_full_redraw 
            or self._needs_full_redraw 
            or self._static_background is None
        )

        if need_redraw:
            self.project_renderer.draw_static_project(project_data, highlight_uids=new_highlights)
            self.draw()
            self._save_background()
            self._needs_full_redraw = False
        else:
            self.restore_region(self._static_background)
        
        if overlay_data:
            artists = self.project_renderer.draw_dynamic_overlay(overlay_data, project_data.is_inverted)
            for artist in artists:
                self.ax.draw_artist(artist)
                artist.remove()
        
        if not need_redraw:
            self.blit(self.ax.bbox)

    def export_image(self, filename: str) -> None:
        if self.current_project:
            self.project_renderer.draw_static_project(self.current_project)
            self.fig.savefig(filename, bbox_inches='tight')

    # === Blitting Helpers ===

    def prepare_blitting_background(self) -> None:
        self.draw()
        self._save_background()
        
    def restore_blitting_background(self) -> None:
        if self._static_background:
            self.restore_region(self._static_background)

    def clear_blitting_background(self) -> None:
        self._static_background = None

    def draw_artist_dynamic(self, artist: Any) -> None:
        self.ax.draw_artist(artist)
        self.blit(self.ax.bbox)

    def _save_background(self) -> None:
        if self.ax.bbox.width > 1 and self.ax.bbox.height > 1:
            self._static_background = self.copy_from_bbox(self.ax.bbox)
        else:
            self._static_background = None

    # === Events ===

    def resizeEvent(self, event) -> None:
        super().resizeEvent(event)
        self._static_background = None
        self._needs_full_redraw = True
        if self.current_project:
            self.draw_project(self.current_project, force_full_redraw=True)
