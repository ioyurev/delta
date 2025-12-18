from pathlib import Path
from PySide6.QtWidgets import (QMainWindow, QWidget, QHBoxLayout, 
                               QVBoxLayout, QSplitter, QLabel, QTabWidget, 
                               QFileDialog, QMessageBox)
from PySide6.QtCore import Qt
from PySide6.QtGui import QIcon
from matplotlib.backends.backend_qt import NavigationToolbar2QT
from core.project_controller import ProjectController
from core.utils import resource_path
from core.serializer import ProjectFileError
from core.models import RenderOverlay, Composition, CompositionUpdate
from ui.widgets.canvas import PlotCanvas
from ui.widgets.canvas_view import CanvasView
from ui.widgets.compositions_table import CompositionsTable
from ui.widgets.lines_manager import LinesManager
from ui.widgets.style_dialog import CompositionStyleDialog
from ui.widgets.line_dialog import LineDialog
from ui.widgets.intersection_dialog import IntersectionDialog
from ui.widgets.analysis_panel import AnalysisPanel
from ui.widgets.about_dialog import AboutDialog
from core.version import get_app_version

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()

        # Сохраняем версию в переменную класса для использования в заголовке
        self._app_version = get_app_version()
        
        self._current_filepath: str | None = None
        self._is_modified: bool = False

        self.setWindowTitle(f"Delta v{self._app_version}")
        self.resize(1200, 800)
        
        self.controller = ProjectController()
        self._current_overlay = None
        
        # Устанавливаем SVG как иконку окна
        self.setWindowIcon(QIcon(resource_path("icon.svg")))
        
        self._init_ui()
        self._init_overlay() 
        self._connect_signals()
        
        # Init default
        if not self.controller.has_compositions():
            self.controller.create_composition("A", 1, 0, 0, show_label=False)
            self.controller.create_composition("B", 0, 1, 0, show_label=False)
            self.controller.create_composition("C", 0, 0, 1, show_label=False)
        
        # Устанавливаем целевой размер для CanvasView (1154x1000 пикселей)
        self.canvas_view.set_target_size(1154, 1000)
        
        self.refresh_all()
        
        # Сбрасываем флаг модификации после первоначальной загрузки
        self._set_modified(False)

    def _init_ui(self):
        # Menu
        mb = self.menuBar()
        
        # File Menu
        m_file = mb.addMenu("File")
        m_file.addAction("New", self.new_project, "Ctrl+N")
        m_file.addSeparator()
        m_file.addAction("Open", self.load_project, "Ctrl+O")
        m_file.addAction("Save", self.save_project, "Ctrl+S")
        m_file.addAction("Save As...", self.save_project_as, "Ctrl+Shift+S")
        m_file.addSeparator()
        m_file.addAction("Export Image", self.export_image, "Ctrl+E")
        m_file.addSeparator()
        m_file.addAction("Exit", self.close, "Alt+F4")
        
        # Help Menu (НОВОЕ)
        m_help = mb.addMenu("Help")
        m_help.addAction("About...", self.show_about_dialog, "F1")
        
        # Main Layout
        central = QWidget()
        self.setCentralWidget(central)
        main_lay = QHBoxLayout(central)
        split = QSplitter(Qt.Orientation.Horizontal)
        
        # 1. Canvas Area
        left_w = QWidget()
        left_l = QVBoxLayout(left_w)
        left_l.setContentsMargins(0, 0, 0, 0)
        self.canvas = PlotCanvas()
        self.canvas_view = CanvasView(self.canvas)  # Оборачиваем canvas в view
        
        self.toolbar = NavigationToolbar2QT(self.canvas, self)
        for action in self.toolbar.actions():
            if action.text() in ("Subplots", "Customize", "Save"):
                action.setVisible(False)
        
        left_l.addWidget(self.toolbar)
        left_l.addWidget(self.canvas_view)
        
        # 2. Tools Area
        right_tabs = QTabWidget()
        
        self.table_widget = CompositionsTable()
        right_tabs.addTab(self.table_widget, "Compositions")
        
        self.lines_widget = LinesManager()
        right_tabs.addTab(self.lines_widget, "Lines")
        
        self.analysis_widget = AnalysisPanel()
        right_tabs.addTab(self.analysis_widget, "Analysis")
        
        right_tabs.currentChanged.connect(lambda: self.refresh_all())
        self.analysis_widget.update_needed.connect(self.refresh_all)
        self.analysis_widget.overlay_changed.connect(self._on_overlay_only_update)
        
        split.addWidget(left_w)
        split.addWidget(right_tabs)
        split.setStretchFactor(0, 1)
        
        main_lay.addWidget(split)

    def _init_overlay(self):
        self.coord_overlay = QLabel(self.canvas)
        self.coord_overlay.setStyleSheet("""
            QLabel {
                background-color: rgba(255, 255, 255, 0.85); 
                border: 1px solid #aaa; 
                border-radius: 4px;
                padding: 6px;
                font-family: monospace;
                font-weight: bold;
                font-size: 12px;
                color: #333;
            }
        """)
        self.coord_overlay.hide()

    def _connect_signals(self):
        # Canvas
        self.canvas.mouse_moved.connect(self._on_mouse_hover)
        self.canvas.annotation_dropped.connect(self._on_label_drop)
        self.canvas.vertex_label_dropped.connect(self.controller.set_vertex_label_pos)
        
        # Compositions Table
        self.table_widget.composition_added.connect(
            lambda: (self.controller.create_composition(), self.refresh_all())
        )
        self.table_widget.data_changed.connect(self._on_comp_edited)
        self.table_widget.components_changed.connect(self._on_comps_changed)
        self.table_widget.grid_changed.connect(self._on_grid_changed)
        self.table_widget.view_mode_changed.connect(self._on_view_changed)
        self.table_widget.style_request.connect(self._on_comp_style_req)
        self.table_widget.composition_deleted.connect(self._on_comp_delete_req)
        
        # Lines Manager
        self.lines_widget.request_add_line.connect(self._on_line_add_req)
        self.lines_widget.request_edit_line.connect(self._on_line_edit_req)
        self.lines_widget.request_delete_line.connect(self._on_line_del_req)
        self.lines_widget.request_calc_dialog.connect(self._open_calc_dialog)

    # === Intersection Dialog ===
    
    def _open_calc_dialog(self):
        # 1. Используем публичное свойство project_data
        if self.controller.get_line_count() < 2:
            QMessageBox.warning(self, "Info", "Need at least 2 lines.")
            return
        
        # 2. Передаем КОНТРОЛЛЕР, а не self.controller._project
        dlg = IntersectionDialog(self.controller, parent=self)
        dlg.overlay_changed.connect(self._on_overlay_changed)
        dlg.intersection_found.connect(self._on_intersection_found)
        dlg.exec()
        
        self._current_overlay = None
        self.refresh_all()
    
    def _on_overlay_changed(self, overlay: RenderOverlay):
        self._current_overlay = overlay
        self._redraw_canvas()
    
    def _on_intersection_found(self, composition: Composition):
        self.controller.create_composition("Intersection", 
                                     composition.a, composition.b, composition.c)
    
    def _redraw_canvas(self):
        overlay = self._current_overlay or RenderOverlay()
        # 3. Используем публичное свойство project_data
        self.canvas.draw_project(self.controller.project_data, overlay_data=overlay)

    # === Line Handlers ===

    def _on_line_add_req(self):
        # 4. Используем get_all_compositions() вместо прямого доступа к списку
        dlg = LineDialog(self.controller.get_all_compositions(), parent=self)
        if dlg.exec():
            data = dlg.get_data()
            if data.start_uid != data.end_uid:
                line = self.controller.create_line(data.start_uid, data.end_uid)
                if line:
                    self.controller.update_line_style(
                        line.uid, data.color, data.line_style, data.width
                    )
                    self.refresh_all()

    def _on_line_edit_req(self, uid: str):
        line_obj = None
        for line in self.controller._project.lines:
            if line.uid == uid:
                line_obj = line
                break
        if not line_obj:
            return

        self.canvas.set_highlight_line(uid)
        dlg = LineDialog(self.controller.get_all_compositions(), 
                        current_line=line_obj, parent=self)
        if dlg.exec():
            data = dlg.get_data()
            # 1. Обновляем координаты
            self.controller.update_line_endpoints(uid, data.start_uid, data.end_uid)
            # 2. Обновляем стиль
            self.controller.update_line_style(uid, data.color, data.line_style, data.width)
        
        self.canvas.set_highlight_line(None)
        self.refresh_all()

    def _on_line_del_req(self, uid: str):
        self.controller.delete_line(uid)
        self.refresh_all()

    # === Composition Handlers ===

    def _on_comp_style_req(self, uid: str):
        comp = None
        for p in self.controller._project.compositions:
            if p.uid == uid:
                comp = p
                break
        
        if not comp:
            return
        
        # Создаем временный объект для диалога (или передаем напрямую данные)
        dlg = CompositionStyleDialog(comp, self)
        if dlg.exec():
            data = dlg.get_data()
            self.controller.update_composition_style(
                uid, data.color, data.size, data.symbol,
                data.show_label, data.show_marker
            )
            self.refresh_all()

    def _on_comp_delete_req(self, uid: str):
        self.controller.delete_composition(uid)
        self.refresh_all()

    def _on_comp_edited(self, uid: str, update: CompositionUpdate) -> None:
        """
        Принимает готовый DTO из таблицы и передает в контроллер.
        Больше никаких if field == 'name'!
        """
        self.controller.update_composition(uid, update)
        self.refresh_all()

    def _on_label_drop(self, uid: str, x: float, y: float):
        self.controller.set_composition_label_pos(uid=uid, x=x, y=y)
        self.refresh_all()

    # === Settings Handlers ===

    def _on_comps_changed(self, names: list[str]):
        self.controller.update_components(names=names)
        self.refresh_all()

    def _on_grid_changed(self, visible: bool, step: float):
        self.controller.update_grid(visible=visible, step=step)
        self.refresh_all()

    def _on_view_changed(self, inverted: bool):
        self.controller.update_view_mode(is_inverted=inverted)
        self.refresh_all()

    # === Main Refresh ===

    def refresh_all(self):
        # Любое обновление интерфейса (кроме загрузки) считаем изменением
        self._set_modified(True)
        
        # 4. Используем публичное свойство
        project_data = self.controller.project_data
        overlay = self.analysis_widget.get_overlay_data()
        # ЯВНО говорим: данные изменились, перерисуй всё
        self.canvas.draw_project(project_data, overlay_data=overlay, force_full_redraw=True) 
        
        self.table_widget.update_view(project_data)
        self.lines_widget.update_view(project_data)
        self.analysis_widget.update_view(project_data)

    def _on_overlay_only_update(self):
        overlay = self.analysis_widget.get_overlay_data()
        # 4. Используем публичное свойство project_data
        self.canvas.draw_project(self.controller.project_data, overlay_data=overlay)

    def _on_mouse_hover(self, comp: Composition):
        if comp.a < -0.01 or comp.b < -0.01 or comp.c < -0.01:
            self.coord_overlay.hide()
            return

        names = self.controller.get_components()
        text = f"{names[0]}: {comp.a:.4f}\n{names[1]}: {comp.b:.4f}\n{names[2]}: {comp.c:.4f}"
        
        self.coord_overlay.setText(text)
        self.coord_overlay.adjustSize()
        self.coord_overlay.move(10, 10)
        self.coord_overlay.show()
        self.coord_overlay.raise_()
        self.analysis_widget.on_cursor_move(comp)

    # === Window State Helpers ===

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

    # === File Operations ===

    def export_image(self):
        """Экспорт текущего вида графика в файл"""
        filters = "Images (*.png *.jpg *.jpeg *.svg *.pdf);;PNG (*.png);;JPEG (*.jpg *.jpeg);;SVG (*.svg);;PDF (*.pdf)"
        fn, _ = QFileDialog.getSaveFileName(self, "Export Image", "", filters)
        
        if fn:
            try:
                # Вызываем метод экспорта у Canvas
                self.canvas.export_image(fn)
                self.statusBar().showMessage(f"Image exported: {fn}", 3000)
            except Exception as e:
                QMessageBox.critical(self, "Export Error", f"Failed to save image:\n{str(e)}")

    def save_project(self):
        """Сохраняет в текущий файл или вызывает Save As"""
        if self._current_filepath:
            self._perform_save(self._current_filepath)
        else:
            self.save_project_as()

    def save_project_as(self):
        """Диалог 'Сохранить как'"""
        fn, _ = QFileDialog.getSaveFileName(self, "Save Project As", "", "JSON (*.json)")
        if fn:
            self._perform_save(fn)

    def _perform_save(self, filepath: str):
        """Внутренняя логика сохранения"""
        try:
            self.controller.save_project(filepath)
            
            # Обновляем состояние
            self._current_filepath = filepath
            self._set_modified(False)
            
            self.statusBar().showMessage(f"Saved: {filepath}", 3000)
        except ProjectFileError as e:
            QMessageBox.critical(self, "Save Error", str(e))

    def _check_unsaved_changes(self) -> bool:
        """
        Возвращает True, если можно продолжать (нет изменений или пользователь выбрал действие).
        Возвращает False, если пользователь нажал Cancel.
        """
        if self._is_modified:
            res = QMessageBox.question(
                self, "Unsaved Changes", 
                "Project has unsaved changes. Save them?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No | QMessageBox.StandardButton.Cancel
            )
            
            if res == QMessageBox.StandardButton.Cancel:
                return False
            if res == QMessageBox.StandardButton.Yes:
                self.save_project()
                # Если после попытки сохранения всё еще modified (например, отменил диалог сохранения), прерываем
                if self._is_modified: 
                    return False
        return True

    def load_project(self):
        if not self._check_unsaved_changes():
            return

        fn, _ = QFileDialog.getOpenFileName(self, "Load Project", "", "JSON (*.json)")
        if fn:
            try:
                self.controller.load_project(fn)
                self.refresh_all()
                
                # Обновляем состояние ПОСЛЕ refresh_all, чтобы сбросить флаг modified
                self._current_filepath = fn
                self._set_modified(False) 
                
                self.statusBar().showMessage(f"Loaded: {fn}", 3000)
            except ProjectFileError as e:
                QMessageBox.critical(self, "Load Error", str(e))

    def new_project(self):
        """Создает новый проект"""
        if not self._check_unsaved_changes():
            return
            
        # 1. Сброс данных в контроллере
        self.controller.new_project()
        
        # 2. Инициализация дефолтных значений (как в __init__)
        self.controller.create_composition("A", 1, 0, 0, show_label=False)
        self.controller.create_composition("B", 0, 1, 0, show_label=False)
        self.controller.create_composition("C", 0, 0, 1, show_label=False)
        
        # 3. Обновление UI
        self.refresh_all()
        
        # 4. Сброс состояния окна (важно делать ПОСЛЕ refresh_all, т.к. он ставит modified=True)
        self._current_filepath = None
        self._set_modified(False)
        self.statusBar().showMessage("New project created", 3000)

    def show_about_dialog(self):
        dlg = AboutDialog(self)
        dlg.exec()
