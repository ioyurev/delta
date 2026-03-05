from matplotlib.backends.backend_qtagg import FigureCanvasQTAgg
from matplotlib.figure import Figure
from PySide6.QtCore import Signal
from PySide6.QtWidgets import QSizePolicy
from typing import Optional, Any

from delta.models import Composition, RenderOverlay, ProjectData

from delta.renderer import ProjectRenderer
from ui.canvas.interactor import CanvasInteractor


class PlotCanvas(FigureCanvasQTAgg):
    """
    Главный виджет холста.
    
    Zoom/Pan preservation:
        Toolbar matplotlib изменяет пределы осей напрямую, вызывая draw().
        Переопределение draw() детектирует такие внешние перерисовки и 
        инвалидирует кэш фона. При следующем draw_project() пределы 
        сохраняются и восстанавливаются после draw_static_project().
    """
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
        
        # Состояние отрисовки
        self.current_project: Optional[ProjectData] = None
        self.highlighted_line_uid: Optional[str] = None
        self._static_background = None
        self._needs_full_redraw = True
        self._cached_overlay_uids: set[str] = set()
        
        # Состояние вида (zoom/pan preservation)
        self._in_draw_cycle = False    # True пока мы сами рисуем
        self._initial_draw_done = False  # False до первого рендера
        
        self._connect_signals()

    def _connect_signals(self) -> None:
        self.mpl_connect('motion_notify_event', self.interactor.on_move)  # type: ignore
        self.mpl_connect('button_press_event', self.interactor.on_press)  # type: ignore
        self.mpl_connect('button_release_event', self.interactor.on_release)  # type: ignore
        
        self.interactor.mouse_moved.connect(self.mouse_moved)
        self.interactor.annotation_dropped.connect(self.annotation_dropped)
        self.interactor.vertex_label_dropped.connect(self.vertex_label_dropped)

    # === Перехват внешних перерисовок ===

    def draw(self, *args, **kwargs):
        """
        Перехватывает ВСЕ вызовы draw(), включая от toolbar.
        
        Когда toolbar завершает zoom/pan/home, он вызывает draw_idle() → draw().
        Мы детектируем это (флаг _in_draw_cycle == False) и инвалидируем
        кэшированный фон, чтобы следующий draw_project() использовал
        актуальный вид.
        """
        super().draw(*args, **kwargs)
        if not self._in_draw_cycle:
            # Внешняя перерисовка (toolbar zoom/pan/home)
            self._static_background = None

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
            # ① Сохраняем текущие пределы осей (могут содержать пользовательский зум)
            saved_xlim = self.ax.get_xlim()
            saved_ylim = self.ax.get_ylim()
            
            self._in_draw_cycle = True
            try:
                self.project_renderer.draw_static_project(
                    project_data, highlight_uids=new_highlights
                )
                
                # ② Восстанавливаем пользовательский зум/пан
                # На первом рендере — не восстанавливаем (saved содержит мусор)
                if self._initial_draw_done:
                    self.ax.set_xlim(saved_xlim)
                    self.ax.set_ylim(saved_ylim)
                else:
                    self._initial_draw_done = True
                
                self.draw()
                self._save_background()
                self._needs_full_redraw = False
            finally:
                self._in_draw_cycle = False
        else:
            self.restore_region(self._static_background)
        
        if overlay_data:
            artists = self.project_renderer.draw_dynamic_overlay(
                overlay_data, project_data.is_inverted
            )
            for artist in artists:
                self.ax.draw_artist(artist)
                artist.remove()
        
        if not need_redraw:
            self.blit(self.ax.bbox)

    def reset_view(self) -> None:
        """
        Сброс к виду по умолчанию (полная диаграмма).
        Вызывать при создании нового проекта или загрузке файла.
        """
        self._initial_draw_done = False
        self._static_background = None
        self._needs_full_redraw = True

    def export_image(self, filename: str) -> None:
        """Экспортирует текущее состояние в файл"""
        from delta.export import render_to_file
        
        if self.current_project:
            render_to_file(
                project_data=self.current_project,
                filepath=filename,
                dpi=150,
                figsize=(8, 7)
            )

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