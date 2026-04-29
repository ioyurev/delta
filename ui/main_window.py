from pathlib import Path
from PySide6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, 
                               QVBoxLayout, QSplitter, QLabel, QTabWidget, 
                               QFileDialog, QMessageBox)
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from matplotlib.backends.backend_qt import NavigationToolbar2QT

from delta.project_controller import ProjectController
from delta.utils import resource_path
from delta.serializer import ProjectFileError
from delta.exceptions import DuplicateEntityError, ValidationError, EntityNotFoundError
from delta.models import RenderOverlay, Composition, CompositionUpdate, StyleUpdate
from delta.constants import DISPLAY_DECIMALS_CURSOR
from delta.version import get_app_version

from ui.canvas import PlotCanvas
from ui.widgets.canvas_view import CanvasView
from ui.widgets.compositions_table import CompositionsTable
from ui.widgets.lines_manager import LinesManager
from ui.widgets.style_dialog import CompositionStyleDialog
from ui.widgets.line_dialog import LineDialog
from ui.widgets.curve_line_dialog import CurveLineDialog
from ui.widgets.intersection_dialog import IntersectionDialog
from ui.widgets.analysis_panel import AnalysisPanel
from ui.widgets.about_dialog import AboutDialog
from ui.widgets.docs_viewer import DocsViewer
from ui.widgets.display_region_widget import DisplayRegionWidget
from ui.widgets.annotation_widget import AnnotationWidget
from ui.widgets.helpers import handle_entity_errors, build_menu, wait_cursor, get_overlay_style
from delta import math_utils


class MainWindow(QMainWindow):
    """
    Главное окно приложения.
    
    Структура:
        - _init_*: Инициализация компонентов
        - _on_*: Обработчики сигналов (сгруппированы по источнику)
        - Публичные методы: Действия меню (new, save, load, export)
    """

    def __init__(self):
        super().__init__()
        
        self._app_version = get_app_version()
        self._current_filepath: str | None = None
        self._is_modified: bool = False

        self.setWindowTitle(f"Delta v{self._app_version}")
        self.resize(1200, 800)
        self.setWindowIcon(QIcon(resource_path("icon.svg")))
        
        # Контроллер — единственный источник правды
        self.controller = ProjectController()

        # Активный диалог кривой (немодальный — может быть открыт параллельно)
        self._active_curve_dlg: CurveLineDialog | None = None
        # Немодальный диалог Lever Mix
        self._lever_mix_dlg = None
        # Кто ожидает результат выбора точки на холсте: "" | "curve" | "annotation:{field}"
        self._pending_pick_requester: str = ""

        # Инициализация UI
        self._init_menu()
        self._init_central_widget()
        self._init_overlay()
        self._init_status_bar()
        self._connect_signals()
        
        # Начальное состояние
        self._init_default_data()
        self._refresh_ui()
        self._set_modified(False)

    # =========================================================================
    # ИНИЦИАЛИЗАЦИЯ
    # =========================================================================

    def _init_menu(self):
        """Создание главного меню"""
        mb = self.menuBar()
        
        # File меню
        file_menu = mb.addMenu("File")
        build_menu(file_menu, [
            ("📄 New", self.new_project, "Ctrl+N"),
            None,
            ("📂 Open...", self.load_project, "Ctrl+O"),
            ("💾 Save", self.save_project, "Ctrl+S"),
            ("💾 Save As...", self.save_project_as, "Ctrl+Shift+S"),
            None,
            ("🖼️ Export Image...", self.export_image, "Ctrl+E"),
            None,
            ("🚪 Exit", self.close, "Alt+F4"),
        ])
        
        # Добавляем tooltips для пунктов меню File
        file_menu.actions()[0].setToolTip("Create a new project")
        file_menu.actions()[2].setToolTip("Open an existing project file")
        file_menu.actions()[3].setToolTip("Save current project")
        file_menu.actions()[4].setToolTip("Save project with a new name")
        file_menu.actions()[6].setToolTip("Export current diagram as image")
        
        # Edit меню
        edit_menu = mb.addMenu("Edit")
        build_menu(edit_menu, [
            ("↩️ Undo", self._on_undo, "Ctrl+Z"),
            ("↪️ Redo", self._on_redo, "Ctrl+Y"),
            None,
            ("🗑️ Delete Selected", self._on_delete_selected, "Delete"),
        ])
        
        # Добавляем tooltips для пунктов меню Edit
        edit_menu.actions()[0].setToolTip("Undo last action")
        edit_menu.actions()[1].setToolTip("Redo last undone action")
        edit_menu.actions()[3].setToolTip("Delete selected composition or line")
        
        # Help меню
        help_menu = mb.addMenu("Help")
        build_menu(help_menu, [
            ("📖 Documentation", self.show_docs, "F1"),
            ("ℹ️ About", self.show_about_dialog, ""),
        ])
        
        # Добавляем tooltips для пунктов меню Help
        help_menu.actions()[0].setToolTip("Open user documentation")
        help_menu.actions()[1].setToolTip("Show application information")

    def _init_central_widget(self):
        """Создание центрального виджета с разделителем"""
        central = QWidget()
        self.setCentralWidget(central)
        
        main_layout = QHBoxLayout(central)
        splitter = QSplitter(Qt.Orientation.Horizontal)
        
        # Левая часть — Canvas
        splitter.addWidget(self._create_canvas_area())
        
        # Правая часть — Tabs
        splitter.addWidget(self._create_tools_tabs())
        
        splitter.setStretchFactor(0, 1)
        main_layout.addWidget(splitter)

    def _create_canvas_area(self) -> QWidget:
        """Создаёт область с холстом и тулбаром"""
        widget = QWidget()
        layout = QVBoxLayout(widget)
        layout.setContentsMargins(0, 0, 0, 0)
        
        # Canvas
        self.canvas = PlotCanvas()
        self.canvas_view = CanvasView(self.canvas)
        self.canvas_view.set_target_size(1154, 1000)
        
        # Toolbar
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        for action in self.toolbar.actions():
            if action.text() in ("Subplots", "Customize", "Save", "Back", "Forward"):
                action.setVisible(False)
        
        # Добавляем tooltip для элементов тулбара
        self.toolbar.setToolTip("Navigation tools: Pan, Zoom, Home")
        
        layout.addWidget(self.toolbar)
        layout.addWidget(self.canvas_view)
        
        return widget

    def _create_tools_tabs(self) -> QTabWidget:
        """Создаёт панель инструментов справа"""
        tabs = QTabWidget()
        
        self.table_widget = CompositionsTable()
        tabs.addTab(self.table_widget, "Compositions")
        tabs.setTabToolTip(0, "Manage compositions and their visual styles")
        
        self.lines_widget = LinesManager()
        tabs.addTab(self.lines_widget, "Lines")
        tabs.setTabToolTip(1, "Create and manage tie lines between compositions")
        
        self.analysis_widget = AnalysisPanel(self.controller)
        tabs.addTab(self.analysis_widget, "Analysis")
        tabs.setTabToolTip(2, "Calculate intersections and analyze phase diagrams")

        self.region_widget = DisplayRegionWidget()
        tabs.addTab(self.region_widget, "Region")
        tabs.setTabToolTip(3, "Restrict diagram display area to a custom polygon")

        self.annotation_widget = AnnotationWidget()
        tabs.addTab(self.annotation_widget, "Annotations")
        tabs.setTabToolTip(4, "Place text annotations on the diagram")

        # Обновление при смене вкладки
        tabs.currentChanged.connect(self._refresh_ui)

        return tabs

    def _init_overlay(self):
        """Создаёт оверлей с координатами"""
        self.coord_overlay = QLabel(self.canvas)
        self.coord_overlay.setStyleSheet(get_overlay_style())
        self.coord_overlay.hide()
        
        # Добавляем tooltip для координатного оверлея
        self.coord_overlay.setToolTip(
            "Cursor position in molar fractions\n"
            "(barycentric coordinates, normalized)"
        )

    def _init_default_data(self):
        """Создаёт дефолтные вершины треугольника"""
        # Отключаем сигналы на время инициализации
        self.controller.data_changed.disconnect(self._on_data_changed)
        
        if not self.controller.has_compositions():
            self.controller.create_composition("A", 1, 0, 0, show_label=False, show_marker=False)
            self.controller.create_composition("B", 0, 1, 0, show_label=False, show_marker=False)
            self.controller.create_composition("C", 0, 0, 1, show_label=False, show_marker=False)
        
        self.controller.data_changed.connect(self._on_data_changed)

    def _connect_signals(self):
        """Связывает все сигналы с обработчиками"""
        # Controller
        self.controller.data_changed.connect(self._on_data_changed)
        
        # Canvas
        self.canvas.mouse_moved.connect(self._on_mouse_hover)
        self.canvas.annotation_dropped.connect(self._on_label_drop)
        self.canvas.vertex_label_dropped.connect(self.controller.set_vertex_label_pos)
        
        # Compositions Table
        self.table_widget.request_add_composition.connect(self._on_composition_added)
        self.table_widget.composition_edited.connect(self._on_comp_edited)
        self.table_widget.components_changed.connect(self._on_comps_changed)
        self.table_widget.molar_masses_changed.connect(self._on_molar_masses_changed)
        self.table_widget.grid_changed.connect(self._on_grid_changed)
        self.table_widget.view_mode_changed.connect(self._on_view_changed)
        self.table_widget.aspect_lock_changed.connect(self._on_aspect_changed)
        self.table_widget.request_edit_style.connect(self._on_comp_style_req)
        self.table_widget.request_delete_composition.connect(self._on_comp_delete_req)
        self.table_widget.validation_error.connect(self._on_validation_error)
        
        # Lines Manager — straight lines
        self.lines_widget.request_add_line.connect(self._on_line_add_req)
        self.lines_widget.request_edit_line.connect(self._on_line_edit_req)
        self.lines_widget.request_delete_line.connect(self._on_line_del_req)
        self.lines_widget.request_calc_dialog.connect(self._open_calc_dialog)

        # Lines Manager — curve lines
        self.lines_widget.request_add_curve_line.connect(self._on_curve_line_add_req)
        self.lines_widget.request_edit_curve_line.connect(self._on_curve_line_edit_req)
        self.lines_widget.request_delete_curve_line.connect(self._on_curve_line_del_req)

        # Canvas interactor — guide point pick
        self.canvas.interactor.guide_point_picked.connect(self._on_guide_point_picked)
        
        # Analysis Panel
        self.analysis_widget.update_needed.connect(self._refresh_ui)
        self.analysis_widget.open_lever_mix_requested.connect(
            self._on_open_lever_mix
        )

        # Display Region
        self.region_widget.region_changed.connect(self._on_region_changed)
        self.region_widget.enabled_changed.connect(self._on_region_enabled_changed)

        # Annotations
        self.annotation_widget.request_add.connect(self._on_annotation_add)
        self.annotation_widget.request_remove.connect(self._on_annotation_remove)
        self.annotation_widget.annotation_changed.connect(self._on_annotation_changed)
        self.annotation_widget.canvas_pick_requested.connect(self._on_annotation_pick_requested)
        self.canvas.text_annotation_dropped.connect(self._on_text_annotation_dropped)

    def _on_validation_error(self, message: str):
        """Показывает ошибку/предупреждение валидации в StatusBar"""
        # Для заметок (Note:) показываем дольше
        timeout = 5000 if message.startswith("Note:") else 4000
        self.statusBar().showMessage(f"⚠ {message}", timeout)

    # =========================================================================
    # ОБРАБОТЧИКИ: ДАННЫЕ И ОТРИСОВКА
    # =========================================================================

    def _on_data_changed(self) -> None:
        """Вызывается при любом изменении данных в контроллере"""
        self._set_modified(True)
        self._refresh_ui()

    def _refresh_ui(self) -> None:
        """Полное обновление UI"""
        project_data = self.controller.project_data
        overlay = self.analysis_widget.get_overlay_data()

        self.canvas.draw_project(project_data, overlay_data=overlay, force_full_redraw=True)
        self.table_widget.update_view(project_data)
        self.lines_widget.update_view(project_data)
        self.region_widget.update_view(project_data)
        self.annotation_widget.update_view(project_data)

        # Применяем lock_aspect из данных проекта
        locked = project_data.lock_aspect
        self.canvas.set_aspect_locked(locked)
        self.canvas_view.set_aspect_locked(locked)

        # Блокируем сигналы чтобы update_view → _on_calc_request
        # не вызвал повторную перерисовку canvas
        self.analysis_widget.blockSignals(True)
        self.analysis_widget.update_view()
        self.analysis_widget.blockSignals(False)


    def _on_mouse_hover(self, comp: Composition):
        """Обновляет оверлей с координатами"""
        if comp.a < -0.01 or comp.b < -0.01 or comp.c < -0.01:
            self.coord_overlay.hide()
            return

        names = self.controller.get_components()
        d = DISPLAY_DECIMALS_CURSOR
        
        # Получаем нормализованные значения
        try:
            a, b, c = comp.normalized
            text = (
                f"Molar fractions:\n"
                f"{'─' * 14}\n"
                f"{names[0]}: {a:.{d}f}\n"
                f"{names[1]}: {b:.{d}f}\n"
                f"{names[2]}: {c:.{d}f}\n"
                f"{'─' * 14}\n"
                f"Σ = 1.0"
            )
        except Exception:
            # Fallback для невалидных составов
            text = (
                f"{names[0]}: {comp.a:.{d}f}\n"
                f"{names[1]}: {comp.b:.{d}f}\n"
                f"{names[2]}: {comp.c:.{d}f}"
            )
        
        self.coord_overlay.setText(text)
        self.coord_overlay.adjustSize()
        self.coord_overlay.move(10, 10)
        self.coord_overlay.show()
        self.coord_overlay.raise_()
        
        # Обновляем analysis только когда вкладка видима
        if self.analysis_widget.isVisible():
            self.analysis_widget.on_cursor_move(comp)
            overlay = self.analysis_widget.get_overlay_data()
            self.canvas.draw_project(
                self.controller.project_data, overlay_data=overlay
            )

    # =========================================================================
    # ОБРАБОТЧИКИ: COMPOSITIONS
    # =========================================================================

    @handle_entity_errors
    def _on_comp_edited(self, uid: str, update: CompositionUpdate) -> None:
        try:
            self.controller.update_composition(uid, update)
        except ValidationError as e:
            self.statusBar().showMessage(f"⚠ {e}", 4000)
            # Перерисовываем таблицу чтобы вернуть старые значения
            self._refresh_ui()

    @handle_entity_errors
    def _on_comp_style_req(self, uid: str):
        comp = self.controller.get_composition(uid)

        # Подсвечиваем маркер на холсте пока диалог открыт
        overlay = self.analysis_widget.get_overlay_data()
        overlay.highlight_comp_uids = [uid]
        self.canvas.draw_project(self.controller.project_data, overlay, force_full_redraw=True)

        dlg = CompositionStyleDialog(comp, self)
        accepted = dlg.exec()

        # Убираем подсветку
        overlay.highlight_comp_uids = []
        if accepted:
            data = dlg.get_data()
            self.controller.update_composition_style(uid, StyleUpdate(
                color=data.color,
                size=data.size,
                marker_symbol=data.symbol,
                show_label=data.show_label,
                show_marker=data.show_marker
            ))
            self.statusBar().showMessage(f"Style updated for '{comp.name}'", 3000)
        self._refresh_ui()

    @handle_entity_errors
    def _on_comp_delete_req(self, uid: str):
        # Получаем имя ДО удаления
        comp = self.controller.get_composition(uid)
        name = comp.name or "Unnamed"
        
        self.controller.delete_composition(uid)
        self.statusBar().showMessage(f"Deleted '{name}'", 3000)

    @handle_entity_errors
    def _on_label_drop(self, uid: str, x: float, y: float):
        self.controller.set_composition_label_pos(uid=uid, x=x, y=y)
        self.statusBar().showMessage("Label position saved", 2000)

    # ------------------------------------------------------------------
    # Lever Mix dialog
    # ------------------------------------------------------------------

    def _on_open_lever_mix(self) -> None:
        """Открывает (или поднимает) немодальный диалог Lever Mix."""
        from ui.widgets.lever_mix_dialog import LeverMixDialog

        if hasattr(self, '_lever_mix_dlg') and self._lever_mix_dlg is not None:
            self._lever_mix_dlg.raise_()
            self._lever_mix_dlg.activateWindow()
            return

        comps = sorted(self.controller.get_all_compositions(), key=lambda p: p.name)
        components = self.controller.get_components()
        dlg = LeverMixDialog(comps, components, parent=self)
        self._lever_mix_dlg = dlg

        dlg.preview_changed.connect(self._on_lever_mix_preview)
        dlg.composition_accepted.connect(self._on_lever_mix_add)
        dlg.finished.connect(self._on_lever_mix_closed)

        dlg.show()

    def _on_lever_mix_preview(self, payload: object) -> None:
        """Обновляет предпросмотр маркера и базовой линии на холсте.

        payload — tuple (result, end_a, end_b, style) либо None при ошибке/закрытии.
        """
        from delta.models import Composition as _Comp, OverlayLine
        from ui.widgets.helpers import MarkerStyleData
        overlay = self.analysis_widget.get_overlay_data()
        if isinstance(payload, tuple) and len(payload) == 4:
            result, end_a, end_b, style = payload
            overlay.mix_preview_point = result if isinstance(result, _Comp) else None
            if isinstance(style, MarkerStyleData):
                overlay.mix_preview_color = style.color
                overlay.mix_preview_symbol = style.symbol
                overlay.mix_preview_size = style.size
            if isinstance(end_a, _Comp) and isinstance(end_b, _Comp):
                baseline_color = style.color if isinstance(style, MarkerStyleData) else "#e67e00"
                overlay.mix_baseline = OverlayLine(
                    start=end_a, end=end_b,
                    color=baseline_color, style="--", highlight=False,
                )
            else:
                overlay.mix_baseline = None
        else:
            overlay.mix_preview_point = None
            overlay.mix_baseline = None
        if self.canvas.current_project:
            self.canvas.draw_project(self.canvas.current_project, overlay)

    def _on_lever_mix_add(self, payload: object) -> None:
        """Добавляет состав, полученный правилом рычага, в проект."""
        from ui.widgets.helpers import MarkerStyleData
        if not isinstance(payload, tuple) or len(payload) != 2:
            return
        composition, style = payload
        if not isinstance(composition, Composition):
            return
        try:
            uid = self.controller.create_composition(
                name="Mix",
                a=float(composition.a),
                b=float(composition.b),
                c=float(composition.c),
            )
            if isinstance(style, MarkerStyleData):
                self.controller.update_composition_style(
                    uid,
                    StyleUpdate(
                        color=style.color,
                        marker_symbol=style.symbol,
                        size=style.size,
                    ),
                )
            self.statusBar().showMessage("Lever mix composition added", 3000)
            self.table_widget.select_composition(uid)
            # Обновляем список составов в диалоге
            if hasattr(self, '_lever_mix_dlg') and self._lever_mix_dlg is not None:
                comps = sorted(
                    self.controller.get_all_compositions(), key=lambda p: p.name
                )
                self._lever_mix_dlg.refresh_compositions(comps)
        except Exception as exc:
            QMessageBox.warning(self, "Creation Error", str(exc))

    def _on_lever_mix_closed(self) -> None:
        """Убирает предпросмотр и освобождает диалог."""
        self._on_lever_mix_preview(None)
        self._lever_mix_dlg = None

    def _on_composition_added(self) -> None:
        """Обработчик добавления нового состава"""
        try:
            # Default coordinates: center of the currently visible canvas region.
            try:
                xlim = self.canvas.ax.get_xlim()
                ylim = self.canvas.ax.get_ylim()
                cx = (xlim[0] + xlim[1]) / 2
                cy = (ylim[0] + ylim[1]) / 2
                is_inv = self.controller.project_data.is_inverted
                center = math_utils.cart_to_bary(cx, cy, is_inv)
                a = max(0.01, float(center.a))
                b = max(0.01, float(center.b))
                c = max(0.01, float(center.c))
                total = a + b + c
                a, b, c = a / total, b / total, c / total
            except Exception:
                a, b, c = 0.33, 0.33, 0.34

            uid = self.controller.create_composition(
                name="New Point",
                a=a, b=b, c=c
            )
            
            # Обратная связь
            self.statusBar().showMessage("New composition added", 3000)
            
            # Выделяем новую строку в таблице
            self.table_widget.select_composition(uid)
            
        except ValidationError as e:
            # На случай, если что-то пойдет не так, показываем ошибку пользователю
            QMessageBox.warning(self, "Creation Error", str(e))

    @handle_entity_errors
    def _on_line_del_req(self, uid: str):
        # Получаем имена ДО удаления
        try:
            start_comp, end_comp = self.controller.get_line_endpoints(uid)
            line_name = f"'{start_comp.name}' — '{end_comp.name}'"
        except EntityNotFoundError:
            line_name = "line"
        
        self.controller.delete_line(uid)
        self.statusBar().showMessage(f"Deleted {line_name}", 3000)

    def _on_intersection_found(self, composition: Composition):
        uid = self.controller.create_composition(
            "Intersection", 
            composition.a, composition.b, composition.c
        )
        self.statusBar().showMessage("Intersection point added as composition", 3000)
        self.table_widget.select_composition(uid)

    # =========================================================================
    # ОБРАБОТЧИКИ: LINES
    # =========================================================================

    def _on_line_add_req(self):
        dlg = LineDialog(self.controller.get_all_compositions(), parent=self)
        if dlg.exec():
            data = dlg.get_data()
            try:
                line_uid = self.controller.create_line(data.start_uid, data.end_uid)
                self.controller.update_line_style(line_uid, StyleUpdate(
                    color=data.color,
                    line_style=data.line_style,
                    size=data.width,
                ))
                self.controller.update_line_arrow(line_uid, data.arrow)
                self.statusBar().showMessage("Line created", 3000)
            except ValidationError as e:
                QMessageBox.warning(self, "Invalid Line", str(e))
            except DuplicateEntityError:
                QMessageBox.information(self, "Duplicate", "This line already exists.")

    @handle_entity_errors
    def _on_line_edit_req(self, uid: str):
        line_obj = self.controller.get_line(uid)
        self.canvas.set_highlight_line(uid)

        dlg = LineDialog(self.controller.get_all_compositions(),
                         current_line=line_obj, parent=self)
        if dlg.exec():
            data = dlg.get_data()
            self.controller.update_line_endpoints(uid, data.start_uid, data.end_uid)
            self.controller.update_line_style(uid, StyleUpdate(
                color=data.color,
                line_style=data.line_style,
                size=data.width,
            ))
            self.controller.update_line_arrow(uid, data.arrow)

        self.canvas.set_highlight_line(None)

    # =========================================================================
    # ОБРАБОТЧИКИ: CURVE LINES
    # =========================================================================

    def _on_curve_line_add_req(self):
        dlg = CurveLineDialog(
            self.controller.get_all_compositions(),
            components=self.controller.get_components(),
            parent=self,
        )
        self._attach_curve_dlg(dlg)
        dlg.show()

    @handle_entity_errors
    def _on_curve_line_edit_req(self, uid: str):
        cline = self.controller.get_curve_line(uid)
        self.canvas.set_highlight_line(uid)
        dlg = CurveLineDialog(
            self.controller.get_all_compositions(),
            current_line=cline,
            components=self.controller.get_components(),
            parent=self,
        )
        self._attach_curve_dlg(dlg)
        dlg.show()

    def _attach_curve_dlg(self, dlg: CurveLineDialog) -> None:
        """Подключает сигналы диалога кривой и сохраняет ссылку."""
        if self._active_curve_dlg is not None:
            self._active_curve_dlg.close()

        self._active_curve_dlg = dlg
        dlg.request_canvas_pick.connect(self._on_curve_dlg_pick_req)
        dlg.accepted.connect(self._on_curve_dlg_accepted)
        dlg.rejected.connect(self._on_curve_dlg_closed)
        dlg.finished.connect(self._on_curve_dlg_closed)

    def _on_curve_dlg_pick_req(self) -> None:
        """Переключает интерактор в режим выбора guide-точки."""
        from ui.canvas.interactor import CanvasInteractor
        self._pending_pick_requester = "curve"
        self.canvas.interactor.set_mode(CanvasInteractor.MODE_GUIDE_PICK)
        self.statusBar().showMessage(
            "Click on the diagram to add a guide point. Esc to cancel.", 0
        )

    def _on_guide_point_picked(self, comp: Composition) -> None:
        """Получает guide-точку от холста и маршрутизирует по _pending_pick_requester."""
        from ui.canvas.interactor import CanvasInteractor
        self.canvas.interactor.set_mode(CanvasInteractor.MODE_NORMAL)
        self.statusBar().clearMessage()

        requester = self._pending_pick_requester
        self._pending_pick_requester = ""

        if requester.startswith("annotation:"):
            field = requester[len("annotation:"):]
            self.annotation_widget.receive_pick(field, comp)
        else:
            # curve dialog
            if self._active_curve_dlg and self._active_curve_dlg.isVisible():
                self._active_curve_dlg.add_guide_point_from_canvas(comp)
                self._active_curve_dlg.raise_()
                self._active_curve_dlg.activateWindow()

    def _on_curve_dlg_accepted(self) -> None:
        dlg = self._active_curve_dlg
        if dlg is None:
            return
        data = dlg.get_data()
        try:
            if data.uid:
                # Редактирование
                self.controller.update_curve_line_endpoints(
                    data.uid, data.start_uid, data.end_uid
                )
                self.controller.update_curve_line_style(data.uid, StyleUpdate(
                    color=data.color,
                    line_style=data.line_style,
                    size=data.width,
                ))
                self.controller.update_curve_line_arrow(data.uid, data.arrow)
                self.controller.update_curve_line_guides(data.uid, data.guide_points, data.poly_degree)
                self.controller.update_curve_line_guide_markers(
                    data.uid, data.show_guide_markers,
                    StyleUpdate(color=data.guide_marker_color,
                                marker_symbol=data.guide_marker_symbol,
                                size=data.guide_marker_size),
                )
                self.statusBar().showMessage("Curve line updated", 3000)
            else:
                # Создание
                uid = self.controller.create_curve_line(data.start_uid, data.end_uid)
                self.controller.update_curve_line_style(uid, StyleUpdate(
                    color=data.color,
                    line_style=data.line_style,
                    size=data.width,
                ))
                self.controller.update_curve_line_arrow(uid, data.arrow)
                self.controller.update_curve_line_guides(uid, data.guide_points, data.poly_degree)
                self.controller.update_curve_line_guide_markers(
                    uid, data.show_guide_markers,
                    StyleUpdate(color=data.guide_marker_color,
                                marker_symbol=data.guide_marker_symbol,
                                size=data.guide_marker_size),
                )
                self.statusBar().showMessage("Curve line created", 3000)
        except (ValidationError, EntityNotFoundError) as e:
            QMessageBox.warning(self, "Error", str(e))
        finally:
            self.canvas.set_highlight_line(None)

    def _on_curve_dlg_closed(self) -> None:
        from ui.canvas.interactor import CanvasInteractor
        self.canvas.interactor.set_mode(CanvasInteractor.MODE_NORMAL)
        self.canvas.set_highlight_line(None)
        self._active_curve_dlg = None
        if self._pending_pick_requester == "curve":
            self._pending_pick_requester = ""
        self.statusBar().clearMessage()

    @handle_entity_errors
    def _on_curve_line_del_req(self, uid: str):
        try:
            cline = self.controller.get_curve_line(uid)
            start = self.controller.find_composition(cline.start_uid)
            end = self.controller.find_composition(cline.end_uid)
            name = f"'{start.name if start else '?'}' — '{end.name if end else '?'}'"
        except EntityNotFoundError:
            name = "curve line"

        self.controller.delete_curve_line(uid)
        self.statusBar().showMessage(f"Deleted {name}", 3000)

    def _open_calc_dialog(self):
        if self.controller.get_line_count() < 2:
            QMessageBox.warning(self, "Info", "Need at least 2 lines.")
            return
        
        dlg = IntersectionDialog(self.controller, parent=self)
        dlg.overlay_changed.connect(self._on_overlay_changed)
        dlg.intersection_found.connect(self._on_intersection_found)
        dlg.exec()
        
        self._refresh_ui()

    def _on_overlay_changed(self, overlay: RenderOverlay):
        self.canvas.draw_project(self.controller.project_data, overlay_data=overlay)

    # =========================================================================
    # ОБРАБОТЧИКИ: SETTINGS
    # =========================================================================

    def _on_comps_changed(self, names: list[str]):
        self.controller.update_components(names=names)
        self.statusBar().showMessage("Component names updated", 3000)

    def _on_molar_masses_changed(self, masses: list) -> None:
        self.controller.update_component_molar_masses(masses)
        n_set = sum(1 for m in masses if m is not None)
        if n_set == 3:
            self.statusBar().showMessage("Molar masses set — naveski calculation available", 3000)
        elif n_set == 0:
            self.statusBar().showMessage("Molar masses cleared", 2000)

    def _on_grid_changed(self, visible: bool, step: float):
        self.controller.update_grid(visible=visible, step=step)
        status = "Grid enabled" if visible else "Grid disabled"
        self.statusBar().showMessage(status, 2000)

    def _on_view_changed(self, inverted: bool):
        self.controller.update_view_mode(is_inverted=inverted)
        mode = "inverted" if inverted else "normal"
        self.statusBar().showMessage(f"Triangle mode: {mode}", 2000)

    def _on_aspect_changed(self, locked: bool):
        """Переключение режима пропорций и сохранение в проект"""
        self.canvas.set_aspect_locked(locked)
        self.canvas_view.set_aspect_locked(locked)
        self.controller.update_lock_aspect(locked)
        mode = "locked (equal)" if locked else "free (stretch)"
        self.statusBar().showMessage(f"Aspect ratio: {mode}", 2000)

    def _on_region_changed(self, points: list) -> None:
        self.controller.update_display_region(points)

    def _on_region_enabled_changed(self, enabled: bool) -> None:
        self.controller.update_display_region_enabled(enabled)

    def _on_annotation_pick_requested(self, field: str) -> None:
        """Annotation widget запрашивает выбор точки на холсте."""
        from ui.canvas.interactor import CanvasInteractor
        self._pending_pick_requester = f"annotation:{field}"
        self.canvas.interactor.set_mode(CanvasInteractor.MODE_GUIDE_PICK)
        label = "position" if field == "position" else "arrow target"
        self.statusBar().showMessage(
            f"Click on the diagram to pick {label}. Esc to cancel.", 0
        )

    def _on_annotation_add(self) -> None:
        uid = self.controller.create_annotation()
        self.statusBar().showMessage("Annotation added", 2000)
        # Select the new item — update_view will be triggered by data_changed
        self._last_added_annotation_uid = uid

    def _on_annotation_remove(self, uid: str) -> None:
        self.controller.delete_annotation(uid)
        self.statusBar().showMessage("Annotation removed", 2000)

    @handle_entity_errors
    def _on_annotation_changed(self, uid: str, fields: dict) -> None:
        self.controller.update_annotation(uid, **fields)

    @handle_entity_errors
    def _on_text_annotation_dropped(self, uid: str, x: float, y: float) -> None:
        """Аннотация перетащена на холсте — конвертируем cart→bary и сохраняем позицию."""
        is_inv = self.controller.project_data.is_inverted
        new_pos = math_utils.cart_to_bary(x, y, is_inv)
        self.controller.update_annotation(uid, position=new_pos)

    # =========================================================================
    # УПРАВЛЕНИЕ СОСТОЯНИЕМ ОКНА
    # =========================================================================

    def _update_window_title(self):
        title = f"Delta v{self._app_version}"
        
        if self._current_filepath:
            filename = Path(self._current_filepath).name
            title += f" — {filename}"
        else:
            title += " — New Project"
            
        if self._is_modified:
            title += "*"
            
        self.setWindowTitle(title)

    def _set_modified(self, modified: bool):
        self._is_modified = modified
        self._update_window_title()

    def _check_unsaved_changes(self) -> bool:
        """Проверяет несохранённые изменения. Возвращает True если можно продолжать."""
        if not self._is_modified:
            return True
            
        res = QMessageBox.question(
            self, "Unsaved Changes", 
            "Project has unsaved changes. Save them?",
            QMessageBox.StandardButton.Yes | 
            QMessageBox.StandardButton.No | 
            QMessageBox.StandardButton.Cancel
        )
        
        if res == QMessageBox.StandardButton.Cancel:
            return False
        if res == QMessageBox.StandardButton.Yes:
            self.save_project()
            return not self._is_modified  # False если пользователь отменил сохранение
            
        return True

    # =========================================================================
    # ПУБЛИЧНЫЕ ДЕЙСТВИЯ (МЕНЮ)
    # =========================================================================

    def new_project(self):
        """Создает новый проект"""
        if not self._check_unsaved_changes():
            return
            
        with wait_cursor():
            self.controller.new_project()
            self._init_default_data()
            self.canvas.reset_view()          # ← ДОБАВЛЕНО
            self._refresh_ui()
        
        self._current_filepath = None
        self._set_modified(False)
        self.statusBar().showMessage("New project created", 3000)

    def save_project(self):
        """Сохраняет в текущий файл или вызывает Save As"""
        if self._current_filepath:
            self._perform_save(self._current_filepath)
        else:
            self.save_project_as()

    def save_project_as(self):
        """Диалог 'Сохранить как'"""
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Save Project As", "", "JSON (*.json)"
        )
        if filepath:
            self._perform_save(filepath)

    def _perform_save(self, filepath: str):
        """Выполняет сохранение"""
        with wait_cursor():
            try:
                self.controller.save_project(filepath)
                self._current_filepath = filepath
                self._set_modified(False)
                self.statusBar().showMessage(f"Saved: {filepath}", 3000)
            except ProjectFileError as e:
                QMessageBox.critical(self, "Save Error", str(e))

    def load_project(self):
        """Загружает проект из файла"""
        if not self._check_unsaved_changes():
            return

        filepath, _ = QFileDialog.getOpenFileName(
            self, "Load Project", "", "JSON (*.json)"
        )
        if filepath:
            with wait_cursor():
                try:
                    self.controller.load_project(filepath)
                    self.canvas.reset_view()  # ← ДОБАВЛЕНО
                    self._refresh_ui()
                    self._current_filepath = filepath
                    self._set_modified(False)
                    self.statusBar().showMessage(f"Loaded: {filepath}", 3000)
                except ProjectFileError as e:
                    QMessageBox.critical(self, "Load Error", str(e))

    def export_image(self):
        """Экспорт текущего вида графика в файл"""
        filters = "Images (*.png *.jpg *.svg *.pdf);;PNG (*.png);;SVG (*.svg);;PDF (*.pdf)"
        filepath, _ = QFileDialog.getSaveFileName(
            self, "Export Image", "", filters
        )
        
        if filepath:
            with wait_cursor():
                try:
                    self.canvas.export_image(filepath)
                    self.statusBar().showMessage(f"Image exported: {filepath}", 3000)
                except Exception as e:
                    QMessageBox.critical(self, "Export Error", f"Failed to save image:\n{e}")

    def show_about_dialog(self):
        AboutDialog(self).exec()

    def show_docs(self):
        DocsViewer(self).exec()

    def _init_status_bar(self):
        """Инициализация StatusBar с tooltip"""
        self.statusBar().setToolTip("Status messages and notifications")

    # =========================================================================
    # ОБРАБОТЧИКИ: EDIT
    # =========================================================================

    def _on_undo(self):
        """Отмена последнего действия"""
        if self.controller.undo():
            self.statusBar().showMessage("Undo", 2000)
        else:
            self.statusBar().showMessage("Nothing to undo", 2000)

    def _on_redo(self):
        """Повтор отменённого действия"""
        if self.controller.redo():
            self.statusBar().showMessage("Redo", 2000)
        else:
            self.statusBar().showMessage("Nothing to redo", 2000)

    def _on_delete_selected(self):
        """Удаляет выбранный элемент (состав или линию)"""
        # 1. Проверяем фокус на таблице Compositions (вкладка 1)
        if self.table_widget.table.hasFocus():
            item = self.table_widget.table.currentItem()
            if item:
                uid = self.table_widget._row_to_uid.get(item.row())
                if uid:
                    self._on_comp_delete_req(uid)
                    return
        
        # 2. Проверяем фокус на списке Lines (вкладка 2)
        if self.lines_widget.list_widget.hasFocus():
            list_item = self.lines_widget.list_widget.currentItem()
            if list_item:
                uid = list_item.data(Qt.ItemDataRole.UserRole)
                if uid:
                    self._on_line_del_req(uid)
                    return

        # 3. (ВАЖНО) Если фокус внутри Analysis Panel (Manual Input Table),
        # мы НЕ должны удалять никаких глобальных сущностей.
        # QTableWidget сам обработает Delete для очистки ячейки.
        if self.analysis_widget.table_manual.hasFocus():
            return
        
        self.statusBar().showMessage("Nothing selected to delete", 2000)
