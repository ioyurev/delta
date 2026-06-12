"""
Headless API для построения тройных диаграмм.

Не требует Qt. Использует matplotlib для рендеринга.

Example:
    from delta import Diagram
    
    d = Diagram(["A", "B", "C"])
    p1 = d.add_point("X", 0.5, 0.3, 0.2)
    p2 = d.add_point("Y", 0.2, 0.5, 0.3)
    d.add_line(p1, p2)
    d.save_image("diagram.png")
"""

from __future__ import annotations
from typing import Optional, Literal
from dataclasses import dataclass

from delta.project_manager import ProjectManager
from delta.models import (
    StyleUpdate, CompositionUpdate, IntersectionStatus, FigureMargins,
    StraightSegment, LineRefSegment, CurveRefSegment, BoundarySegment,
    Composition as _Composition,
)
from delta.renderer import ProjectRenderer
from delta.render_layout import apply_figure_margins
from delta.interactive import MapInteractor
from delta.exceptions import ValidationError, EntityNotFoundError
from pydantic import ValidationError as PydanticValidationError


# Типы для аннотаций
MarkerStyle = Literal["o", "s", "^", "v", "D", "*", "x", "P", ".", ","]
LineStyle = Literal["-", "--", ":", "-."]


@dataclass(frozen=True)
class PointInfo:
    """Информация о точке (read-only)"""
    uid: str
    name: str
    a: float
    b: float
    c: float
    color: str
    size: float
    marker: str
    visible: bool
    label_visible: bool


@dataclass(frozen=True)
class LineInfo:
    """Информация о линии (read-only)"""
    uid: str
    start_uid: str
    end_uid: str
    color: str
    width: float
    style: str


@dataclass(frozen=True)
class IntersectionInfo:
    """Результат расчёта пересечения"""
    found: bool
    inside_triangle: bool
    a: Optional[float] = None
    b: Optional[float] = None
    c: Optional[float] = None
    message: str = ""


@dataclass(frozen=True)
class LeverInfo:
    """Результат правила рычага"""
    valid: bool
    fraction_start: float = 0.0
    fraction_end: float = 0.0
    message: str = ""


class Diagram:
    """
    Тройная диаграмма состояния (треугольник Гиббса).
    
    Headless API для создания, редактирования и экспорта диаграмм
    без графического интерфейса.
    
    Attributes:
        components: Имена трёх компонентов системы
        inverted: Ориентация треугольника (вершина C внизу)
    
    Example:
        >>> d = Diagram(["Water", "Ethanol", "Salt"])
        >>> p1 = d.add_point("Mix1", 0.4, 0.4, 0.2)
        >>> d.save_image("output.png")
    """
    
    def __init__(
        self,
        components: Optional[list[str]] = None,
        inverted: bool = False
    ):
        """
        Создаёт новую диаграмму.
        
        Args:
            components: Имена компонентов [A, B, C]. По умолчанию ["A", "B", "C"].
            inverted: Если True, вершина C внизу треугольника.
        """
        self._manager = ProjectManager(on_change=None, enable_undo=False)
        
        if components:
            if len(components) != 3:
                raise ValueError("Exactly 3 component names required")
            self._manager.update_components(list(components))
        
        if inverted:
            self._manager.update_view_mode(True)
    
    # =========================================================================
    # СВОЙСТВА
    # =========================================================================
    
    @property
    def components(self) -> list[str]:
        """Имена компонентов [A, B, C]"""
        return self._manager.get_components()
    
    @components.setter
    def components(self, names: list[str]) -> None:
        if len(names) != 3:
            raise ValueError("Exactly 3 component names required")
        self._manager.update_components(list(names))
    
    @property
    def inverted(self) -> bool:
        """Ориентация треугольника"""
        return self._manager.is_inverted()
    
    @inverted.setter
    def inverted(self, value: bool) -> None:
        self._manager.update_view_mode(value)
    
    @property
    def grid_visible(self) -> bool:
        """Видимость сетки"""
        return self._manager.project_data.grid.visible
    
    @grid_visible.setter
    def grid_visible(self, value: bool) -> None:
        step = self._manager.project_data.grid.step
        self._manager.update_grid(value, step)
    
    @property
    def grid_step(self) -> float:
        """Шаг сетки"""
        return self._manager.project_data.grid.step
    
    @grid_step.setter
    def grid_step(self, value: float) -> None:
        visible = self._manager.project_data.grid.visible
        self._manager.update_grid(visible, value)
    
    @property
    def lock_aspect(self) -> bool:
        """Фиксация пропорций осей."""
        return self._manager.project_data.render_settings.lock_aspect

    @lock_aspect.setter
    def lock_aspect(self, value: bool) -> None:
        self._manager.update_render_settings(lock_aspect=value)

    @property
    def figure_margins(self) -> list[float]:
        """Отступы figure: [left, right, top, bottom]."""
        m = self._manager.project_data.render_settings.figure_margins
        return [m.left, m.right, m.top, m.bottom]

    @figure_margins.setter
    def figure_margins(self, value: list[float]) -> None:
        if len(value) != 4:
            raise ValueError(
                "figure_margins must contain exactly 4 values: "
                "[left, right, top, bottom]"
            )

        try:
            margins = FigureMargins(
                left=float(value[0]),
                right=float(value[1]),
                top=float(value[2]),
                bottom=float(value[3]),
            )
        except PydanticValidationError as e:
            raise ValueError(str(e)) from e

        self._manager.update_render_settings(figure_margins=margins)

    @property
    def display_region_padding(self) -> float:
        """Отступ вокруг области отображения (Display Region)."""
        return self._manager.project_data.render_settings.display_region_padding

    @display_region_padding.setter
    def display_region_padding(self, value: float) -> None:
        try:
            self._manager.update_render_settings(display_region_padding=float(value))
        except PydanticValidationError as e:
            raise ValueError(str(e)) from e

    def draw(
        self,
        ax,
        *,
        hide_axes: bool = True,
        apply_margins: bool = True,
        interactive: bool = False,
    ) -> None:
        """
        Отрисовывает диаграмму на переданных осях matplotlib.

        Args:
            ax: Объект matplotlib.axes.Axes
            hide_axes: Скрыть рамку осей (по умолчанию True)
            apply_margins: Применить отступы figure_margins к фигуре (по умолчанию True)
            interactive: Подключить интерактивность (координаты, drag меток)
        """
        renderer = ProjectRenderer(ax)
        renderer.draw_static_project(self._manager.project_data, show_hints=False)

        if hide_axes:
            ax.set_axis_off()

        if apply_margins:
            fig = ax.get_figure()
            if fig:
                apply_figure_margins(fig, self._manager.project_data)

        if interactive:
            # Сохраняем ссылку, чтобы GC не собрал интерактор
            self._interactor = MapInteractor(
                ax, self._manager.project_data, manager=self._manager
            )

    def show(
        self,
        *,
        figsize: tuple[float, float] = (8.0, 7.0),
        hide_axes: bool = True,
        interactive: bool = True,
        save_on_close: Optional[str] = None,
    ) -> None:
        """
        Создаёт окно matplotlib, отрисовывает диаграмму и показывает.

        Поддерживает интерактивность:
        - координатный overlay при движении мыши
        - перетаскивание текстовых меток (позиции сохраняются в модель)

        Args:
            figsize: Размер окна (ширина, высота) в дюймах
            hide_axes: Скрыть рамку осей
            interactive: Включить интерактивность (overlay, drag)
            save_on_close: Путь к файлу для автосохранения при закрытии окна.
                           Если None — не сохраняет автоматически.

        Example:
            >>> d = Diagram.load("project.json")
            >>> d.show()  # просто показать
            
            >>> d.show(save_on_close="project.json")  # сохранить изменения при закрытии
        """
        import matplotlib.pyplot as plt

        fig, ax = plt.subplots(figsize=figsize)
        self.draw(ax, hide_axes=hide_axes, apply_margins=True, interactive=interactive)

        if save_on_close is not None:
            filepath = save_on_close

            def _on_close(event: object) -> None:
                if self._manager.is_modified:
                    self._manager.save_to_file(filepath)

            fig.canvas.mpl_connect("close_event", _on_close)

        plt.show()
    
    # =========================================================================
    # ТОЧКИ
    # =========================================================================
    
    def add_point(
        self,
        name: str,
        a: float,
        b: float,
        c: float,
        *,
        color: str = "#000000",
        size: float = 6.0,
        marker: MarkerStyle = "o",
        show_marker: bool = True,
        show_label: bool = True,
        id: Optional[str] = None
    ) -> str:
        """
        Добавляет точку состава на диаграмму.
        
        Координаты автоматически нормализуются (a + b + c = 1).
        
        Args:
            name: Отображаемое имя точки
            a, b, c: Мольные доли компонентов (будут нормализованы)
            color: Цвет в hex-формате (#RRGGBB)
            size: Размер маркера в пунктах
            marker: Форма маркера (o, s, ^, v, D, *, x, P)
            show_marker: Показывать маркер
            show_label: Показывать текстовую метку
            id: Пользовательский идентификатор (опционально)
        
        Returns:
            Идентификатор созданной точки (uid)
        
        Raises:
            ValueError: Если координаты невалидны (все нули, отрицательные)
        
        Example:
            >>> uid = diagram.add_point("Eutectic", 0.33, 0.33, 0.34, color="red")
        """
        try:
            uid = self._manager.create_composition(
                name=name,
                a=a, b=b, c=c,
                show_label=show_label,
                show_marker=show_marker,
                validate=True
            )
        except ValidationError as e:
            raise ValueError(str(e)) from e
        
        # Применяем стиль
        self._manager.update_composition_style(uid, StyleUpdate(
            color=color,
            size=size,
            marker_symbol=marker
        ))
        
        return uid
    
    def update_point(
        self,
        point_id: str,
        *,
        name: Optional[str] = None,
        a: Optional[float] = None,
        b: Optional[float] = None,
        c: Optional[float] = None,
        color: Optional[str] = None,
        size: Optional[float] = None,
        marker: Optional[MarkerStyle] = None,
        show_marker: Optional[bool] = None,
        show_label: Optional[bool] = None
    ) -> None:
        """
        Обновляет параметры существующей точки.
        
        Передавайте только те параметры, которые хотите изменить.
        
        Args:
            point_id: Идентификатор точки
            name: Новое имя
            a, b, c: Новые координаты (если переданы, будут нормализованы)
            color, size, marker: Параметры стиля
            show_marker, show_label: Видимость
        
        Raises:
            KeyError: Если точка не найдена
            ValueError: Если координаты невалидны
        """
        try:
            # Обновляем данные
            if name is not None or a is not None or b is not None or c is not None:
                update = CompositionUpdate(name=name, a=a, b=b, c=c)
                self._manager.update_composition(point_id, update, validate=True)
            
            # Обновляем стиль
            style_update = StyleUpdate(
                color=color,
                size=size,
                marker_symbol=marker,
                show_marker=show_marker,
                show_label=show_label
            )
            # Проверяем, есть ли что обновлять
            if any(v is not None for v in [color, size, marker, show_marker, show_label]):
                self._manager.update_composition_style(point_id, style_update)
                
        except EntityNotFoundError:
            raise KeyError(f"Point not found: {point_id}")
        except ValidationError as e:
            raise ValueError(str(e))
    
    def remove_point(self, point_id: str) -> None:
        """
        Удаляет точку и все связанные с ней линии.
        
        Args:
            point_id: Идентификатор точки
        
        Raises:
            KeyError: Если точка не найдена
        """
        try:
            self._manager.delete_composition(point_id)
        except EntityNotFoundError:
            raise KeyError(f"Point not found: {point_id}")
    
    def get_point(self, point_id: str) -> PointInfo:
        """
        Возвращает информацию о точке.
        
        Args:
            point_id: Идентификатор точки
        
        Returns:
            PointInfo с данными точки
        
        Raises:
            KeyError: Если точка не найдена
        """
        try:
            comp = self._manager.get_composition(point_id)
        except EntityNotFoundError:
            raise KeyError(f"Point not found: {point_id}")
        
        a, b, c = comp.composition.normalized
        return PointInfo(
            uid=comp.uid,
            name=comp.name,
            a=a, b=b, c=c,
            color=comp.style.color,
            size=comp.style.size,
            marker=comp.style.marker_symbol,
            visible=comp.style.show_marker,
            label_visible=comp.style.show_label
        )
    
    def list_points(self) -> list[PointInfo]:
        """Возвращает список всех точек"""
        return [
            self.get_point(comp.uid) 
            for comp in self._manager.get_all_compositions()
        ]
    
    # =========================================================================
    # ЛИНИИ
    # =========================================================================
    
    def add_line(
        self,
        start_id: str,
        end_id: str,
        *,
        color: str = "#000000",
        width: float = 1.5,
        style: LineStyle = "-"
    ) -> str:
        """
        Добавляет линию между двумя точками.
        
        Args:
            start_id: Идентификатор начальной точки
            end_id: Идентификатор конечной точки
            color: Цвет линии (#RRGGBB)
            width: Толщина линии в пунктах
            style: Стиль линии (-, --, :, -.)
        
        Returns:
            Идентификатор созданной линии
        
        Raises:
            KeyError: Если одна из точек не найдена
            ValueError: Если точки совпадают или линия уже существует
        """
        try:
            uid = self._manager.create_line(start_id, end_id)
        except EntityNotFoundError as e:
            raise KeyError(str(e))
        except (ValidationError, Exception) as e:
            raise ValueError(str(e))
        
        self._manager.update_line_style(uid, StyleUpdate(
            color=color,
            size=width,
            line_style=style
        ))
        
        return uid
    
    def update_line(
        self,
        line_id: str,
        *,
        start_id: Optional[str] = None,
        end_id: Optional[str] = None,
        color: Optional[str] = None,
        width: Optional[float] = None,
        style: Optional[LineStyle] = None
    ) -> None:
        """
        Обновляет параметры линии.
        
        Args:
            line_id: Идентификатор линии
            start_id, end_id: Новые конечные точки
            color, width, style: Параметры стиля
        
        Raises:
            KeyError: Если линия или точки не найдены
            ValueError: Если параметры невалидны
        """
        try:
            if start_id is not None or end_id is not None:
                line = self._manager.get_line(line_id)
                new_start = start_id if start_id else line.start_uid
                new_end = end_id if end_id else line.end_uid
                self._manager.update_line_endpoints(line_id, new_start, new_end)
            
            if any(v is not None for v in [color, width, style]):
                self._manager.update_line_style(line_id, StyleUpdate(
                    color=color,
                    size=width,
                    line_style=style
                ))
        except EntityNotFoundError as e:
            raise KeyError(str(e))
        except ValidationError as e:
            raise ValueError(str(e))
    
    def remove_line(self, line_id: str) -> None:
        """Удаляет линию"""
        try:
            self._manager.delete_line(line_id)
        except EntityNotFoundError:
            raise KeyError(f"Line not found: {line_id}")
    
    def get_line(self, line_id: str) -> LineInfo:
        """Возвращает информацию о линии"""
        try:
            line = self._manager.get_line(line_id)
        except EntityNotFoundError:
            raise KeyError(f"Line not found: {line_id}")
        
        return LineInfo(
            uid=line.uid,
            start_uid=line.start_uid,
            end_uid=line.end_uid,
            color=line.style.color,
            width=line.style.size,
            style=line.style.line_style
        )
    
    def list_lines(self) -> list[LineInfo]:
        """Возвращает список всех линий"""
        return [self.get_line(line.uid) for line in self._manager.get_all_lines()]

    # =========================================================================
    # HATCH REGIONS
    # =========================================================================

    def add_hatch_region(
        self,
        vertices: Optional[list[tuple[float, float, float]]] = None,
        *,
        segments: Optional[list] = None,
        name: str = "Region",
        hatch: str = "//",
        hatch_color: str = "#000000",
        fill_color: str = "#000000",
        fill_alpha: float = 0.05,
        edge_color: str = "#000000",
        edge_width: float = 1.0,
    ) -> str:
        """
        Добавляет область с hatch-заливкой.

        Два способа задания границы:

        Способ 1 — простой полигон (прямые стороны):
            diagram.add_hatch_region(
                [(0.5, 0.3, 0.2), (0.2, 0.5, 0.3), (0.3, 0.2, 0.5)],
                hatch="//",
            )

        Способ 2 — segment-based контур (границы вдоль линий/кривых):
            diagram.add_hatch_region(
                segments=[
                    ("line", line_uid),
                    ("curve", curve_uid, True),  # reverse=True
                    ("straight", (0.5, 0.3, 0.2), (0.3, 0.2, 0.5)),
                ],
            )

        Args:
            vertices: Список координат (a, b, c) для простого полигона
            segments: Список сегментов для сложного контура
            name: Имя региона
            hatch: Паттерн штриховки (/, \\, //, x, +, o, ...)
            hatch_color: Цвет штриховки
            fill_color: Цвет заливки
            fill_alpha: Прозрачность заливки (0.0–1.0)
            edge_color: Цвет границы
            edge_width: Толщина границы

        Returns:
            UID созданного региона
        """
        if vertices is not None and segments is not None:
            raise ValueError("Specify either 'vertices' or 'segments', not both")

        if vertices is not None:
            boundary = self._vertices_to_segments(vertices)
        elif segments is not None:
            boundary = self._parse_segments(segments)
        else:
            raise ValueError("Either 'vertices' or 'segments' must be provided")

        return self._manager.create_hatch_region(
            segments=boundary,
            name=name,
            hatch_pattern=hatch,
            hatch_color=hatch_color,
            fill_color=fill_color,
            fill_alpha=fill_alpha,
            edge_color=edge_color,
            edge_width=edge_width,
        )

    def remove_hatch_region(self, uid: str) -> None:
        """Удаляет hatch-регион."""
        try:
            self._manager.delete_hatch_region(uid)
        except EntityNotFoundError:
            raise KeyError(f"Hatch region not found: {uid}")

    def list_hatch_regions(self) -> list[str]:
        """Возвращает список UID всех hatch-регионов."""
        return [h.uid for h in self._manager.project_data.hatch_regions]

    @staticmethod
    def _vertices_to_segments(
        vertices: list[tuple[float, float, float]],
    ) -> list[BoundarySegment]:
        """Преобразует список вершин в замкнутый контур из StraightSegment."""
        if len(vertices) < 3:
            raise ValueError("At least 3 vertices required for a polygon")

        segs: list[BoundarySegment] = []
        for i in range(len(vertices)):
            a1, b1, c1 = vertices[i]
            a2, b2, c2 = vertices[(i + 1) % len(vertices)]
            segs.append(StraightSegment(
                start=_Composition(a=a1, b=b1, c=c1),
                end=_Composition(a=a2, b=b2, c=c2),
            ))
        return segs

    @staticmethod
    def _parse_segments(raw: list) -> list[BoundarySegment]:
        """Парсит пользовательский формат сегментов в модели."""
        segs: list[BoundarySegment] = []
        for item in raw:
            if not isinstance(item, (list, tuple)) or len(item) < 2:
                raise ValueError(f"Invalid segment: {item}")

            kind = item[0]

            if kind == "straight":
                if len(item) != 3:
                    raise ValueError(f"Straight segment needs (kind, start, end): {item}")
                a1, b1, c1 = item[1]
                a2, b2, c2 = item[2]
                segs.append(StraightSegment(
                    start=_Composition(a=a1, b=b1, c=c1),
                    end=_Composition(a=a2, b=b2, c=c2),
                ))

            elif kind == "line":
                uid = item[1]
                reverse = item[2] if len(item) > 2 else False
                segs.append(LineRefSegment(line_uid=uid, reverse=bool(reverse)))

            elif kind == "curve":
                uid = item[1]
                reverse = item[2] if len(item) > 2 else False
                segs.append(CurveRefSegment(curve_uid=uid, reverse=bool(reverse)))

            else:
                raise ValueError(f"Unknown segment kind: {kind}")

        return segs

    # =========================================================================
    # АННОТАЦИИ
    # =========================================================================

    def add_annotation(
        self,
        text: str,
        a: float,
        b: float,
        c: float,
        *,
        font_size: float = 10.0,
        color: str = "#000000",
        bold: bool = False,
        italic: bool = False,
        ha: str = "center",
        va: str = "center",
        box: bool = False,
        box_facecolor: str = "#ffffff",
        box_edgecolor: str = "#000000",
        box_alpha: float = 0.8,
        box_pad: float = 0.3,
        arrow_target: Optional[tuple[float, float, float]] = None,
        arrow_color: str = "#000000",
        visible: bool = True,
    ) -> str:
        """
        Добавляет текстовую аннотацию на диаграмму.

        Args:
            text: Текст аннотации (поддерживает MathText: $Al_2O_3$)
            a, b, c: Барицентрические координаты позиции текста
            font_size: Размер шрифта (4–72)
            color: Цвет текста (#RRGGBB)
            bold: Жирный шрифт
            italic: Курсив
            ha: Горизонтальное выравнивание (left, center, right)
            va: Вертикальное выравнивание (top, center, bottom, baseline)
            box: Включить фоновую рамку
            box_facecolor: Цвет заливки рамки
            box_edgecolor: Цвет границы рамки
            box_alpha: Прозрачность рамки (0.0–1.0)
            box_pad: Отступ внутри рамки
            arrow_target: Координаты (a, b, c) цели стрелки, или None
            arrow_color: Цвет стрелки
            visible: Видимость аннотации

        Returns:
            UID созданной аннотации

        Example:
            >>> uid = d.add_annotation("Eutectic", 0.33, 0.33, 0.34, font_size=12)

            >>> uid = d.add_annotation(
            ...     "$\\\\alpha$-phase", 0.7, 0.2, 0.1,
            ...     bold=True, color="#E74C3C",
            ...     arrow_target=(0.5, 0.3, 0.2),
            ...     box=True,
            ... )
        """
        uid = self._manager.create_annotation(text=text, a=a, b=b, c=c)

        fields: dict[str, object] = {
            "font_size": font_size,
            "color": color,
            "bold": bold,
            "italic": italic,
            "ha": ha,
            "va": va,
            "box_enabled": box,
            "box_facecolor": box_facecolor,
            "box_edgecolor": box_edgecolor,
            "box_alpha": box_alpha,
            "box_pad": box_pad,
            "arrow_color": arrow_color,
            "visible": visible,
        }

        if arrow_target is not None:
            ta, tb, tc = arrow_target
            fields["arrow_enabled"] = True
            fields["arrow_target"] = _Composition(a=ta, b=tb, c=tc)
        else:
            fields["arrow_enabled"] = False

        self._manager.update_annotation(uid, **fields)
        return uid

    def update_annotation(
        self,
        uid: str,
        *,
        text: Optional[str] = None,
        a: Optional[float] = None,
        b: Optional[float] = None,
        c: Optional[float] = None,
        font_size: Optional[float] = None,
        color: Optional[str] = None,
        bold: Optional[bool] = None,
        italic: Optional[bool] = None,
        ha: Optional[str] = None,
        va: Optional[str] = None,
        box: Optional[bool] = None,
        box_facecolor: Optional[str] = None,
        box_edgecolor: Optional[str] = None,
        box_alpha: Optional[float] = None,
        box_pad: Optional[float] = None,
        arrow_target: Optional[tuple[float, float, float]] = None,
        arrow_enabled: Optional[bool] = None,
        arrow_color: Optional[str] = None,
        visible: Optional[bool] = None,
    ) -> None:
        """
        Обновляет параметры аннотации. Передавайте только изменяемые поля.

        Args:
            uid: Идентификатор аннотации
            text: Новый текст
            a, b, c: Новые координаты позиции
            (остальные параметры — аналогично add_annotation)

        Raises:
            KeyError: Если аннотация не найдена
        """
        try:
            self._manager.get_annotation(uid)
        except EntityNotFoundError:
            raise KeyError(f"Annotation not found: {uid}")

        fields: dict[str, object] = {}

        if text is not None:
            fields["text"] = text
        if a is not None or b is not None or c is not None:
            ann = self._manager.get_annotation(uid)
            pos = ann.position
            new_a = a if a is not None else pos.a
            new_b = b if b is not None else pos.b
            new_c = c if c is not None else pos.c
            fields["position"] = _Composition(a=new_a, b=new_b, c=new_c)
        if font_size is not None:
            fields["font_size"] = font_size
        if color is not None:
            fields["color"] = color
        if bold is not None:
            fields["bold"] = bold
        if italic is not None:
            fields["italic"] = italic
        if ha is not None:
            fields["ha"] = ha
        if va is not None:
            fields["va"] = va
        if box is not None:
            fields["box_enabled"] = box
        if box_facecolor is not None:
            fields["box_facecolor"] = box_facecolor
        if box_edgecolor is not None:
            fields["box_edgecolor"] = box_edgecolor
        if box_alpha is not None:
            fields["box_alpha"] = box_alpha
        if box_pad is not None:
            fields["box_pad"] = box_pad
        if arrow_target is not None:
            ta, tb, tc = arrow_target
            fields["arrow_target"] = _Composition(a=ta, b=tb, c=tc)
            fields["arrow_enabled"] = True
        if arrow_enabled is not None:
            fields["arrow_enabled"] = arrow_enabled
        if arrow_color is not None:
            fields["arrow_color"] = arrow_color
        if visible is not None:
            fields["visible"] = visible

        if fields:
            self._manager.update_annotation(uid, **fields)

    def remove_annotation(self, uid: str) -> None:
        """
        Удаляет аннотацию.

        Raises:
            KeyError: Если аннотация не найдена
        """
        try:
            self._manager.delete_annotation(uid)
        except EntityNotFoundError:
            raise KeyError(f"Annotation not found: {uid}")

    def list_annotations(self) -> list[str]:
        """Возвращает список UID всех аннотаций."""
        return [a.uid for a in self._manager.project_data.annotations]

    # =========================================================================
    # РАСЧЁТЫ
    # =========================================================================
    
    def intersection(self, line1_id: str, line2_id: str) -> IntersectionInfo:
        """
        Рассчитывает точку пересечения двух линий.
        
        Args:
            line1_id: Идентификатор первой линии
            line2_id: Идентификатор второй линии
        
        Returns:
            IntersectionInfo с результатом расчёта
        
        Raises:
            KeyError: Если линия не найдена
            ValueError: Если переданы одинаковые линии
        """
        try:
            result = self._manager.calculate_intersection(line1_id, line2_id)
        except EntityNotFoundError as e:
            raise KeyError(str(e))
        except ValidationError as e:
            raise ValueError(str(e))
        
        # Общая проверка для FOUND и OUTSIDE
        if result.status in (IntersectionStatus.FOUND, IntersectionStatus.OUTSIDE):
            if result.intersection is None:
                return IntersectionInfo(
                    found=False,
                    inside_triangle=False,
                    message="Calculation error"
                )
            
            a, b, c = result.intersection.normalized
            inside = result.status == IntersectionStatus.FOUND
            
            return IntersectionInfo(
                found=True,
                inside_triangle=inside,
                a=a, b=b, c=c,
                message="Intersection found " + ("inside" if inside else "outside") + " triangle"
            )
        
        elif result.status == IntersectionStatus.PARALLEL:
            return IntersectionInfo(
                found=False,
                inside_triangle=False,
                message="Lines are parallel"
            )
        
        else:
            return IntersectionInfo(
                found=False,
                inside_triangle=False,
                message="Invalid input"
            )
    
    def lever_rule(self, line_id: str, point_id: str) -> LeverInfo:
        """
        Применяет правило рычага: определяет положение точки на линии.
        
        Args:
            line_id: Идентификатор линии (конода)
            point_id: Идентификатор точки
        
        Returns:
            LeverInfo с долями от начала и конца линии
        
        Raises:
            KeyError: Если линия или точка не найдены
        """
        from delta import math_utils
        from delta.exceptions import DegenerateBasisError
        
        try:
            start, end = self._manager.get_line_endpoints(line_id)
            point = self._manager.get_composition(point_id)
        except EntityNotFoundError as e:
            raise KeyError(str(e))
        
        try:
            t = math_utils.get_lever_fraction(
                start.composition,
                end.composition,
                point.composition
            )
        except DegenerateBasisError as e:
            return LeverInfo(valid=False, message=str(e))
        
        # Проверяем, лежит ли точка на отрезке
        if t < -0.001 or t > 1.001:
            return LeverInfo(
                valid=False,
                fraction_start=1.0 - t,
                fraction_end=t,
                message="Point is outside the line segment"
            )
        
        return LeverInfo(
            valid=True,
            fraction_start=1.0 - t,
            fraction_end=t,
            message=f"{start.name}: {(1-t)*100:.1f}%, {end.name}: {t*100:.1f}%"
        )
    
    # =========================================================================
    # СЕРИАЛИЗАЦИЯ
    # =========================================================================
    
    def save(self, filepath: str) -> None:
        """
        Сохраняет диаграмму в JSON-файл.
        
        Args:
            filepath: Путь к файлу (.json)
        """
        self._manager.save_to_file(filepath)
    
    @classmethod
    def load(cls, filepath: str) -> Diagram:
        """
        Загружает диаграмму из JSON-файла.
        
        Args:
            filepath: Путь к файлу
        
        Returns:
            Новый объект Diagram
        """
        diagram = cls()
        diagram._manager.load_from_file(filepath)
        return diagram
    
    def to_dict(self) -> dict:
        """Возвращает диаграмму как словарь (для интеграции)"""
        return self._manager.project_data.model_dump()
    
    @classmethod
    def from_dict(cls, data: dict) -> Diagram:
        """Создаёт диаграмму из словаря"""
        from delta.models import ProjectData
        
        diagram = cls()
        project = ProjectData.model_validate(data)
        diagram._manager._project = project
        diagram._manager._rebuild_cache()
        return diagram
    
    # =========================================================================
    # ЭКСПОРТ ИЗОБРАЖЕНИЙ
    # =========================================================================
    
    def save_image(
        self,
        filepath: str,
        *,
        dpi: int = 150,
        width: float = 8.0,
        height: float = 7.0,
        transparent: bool = False
    ) -> None:
        """
        Экспортирует диаграмму в изображение.
        
        Поддерживаемые форматы: PNG, SVG, PDF, JPG
        
        Args:
            filepath: Путь к файлу (расширение определяет формат)
            dpi: Разрешение для растровых форматов
            width: Ширина в дюймах
            height: Высота в дюймах
            transparent: Прозрачный фон (для PNG)
        """
        from delta.export import render_to_file
        
        render_to_file(
            project_data=self._manager.project_data,
            filepath=filepath,
            dpi=dpi,
            figsize=(width, height),
            transparent=transparent
        )
    
    # =========================================================================
    # УТИЛИТЫ
    # =========================================================================
    
    def clear(self) -> None:
        """Удаляет все точки и линии"""
        self._manager.new_project()
    
    def __repr__(self) -> str:
        n_points = self._manager.get_composition_count()
        n_lines = self._manager.get_line_count()
        return f"Diagram(components={self.components}, points={n_points}, lines={n_lines})"
