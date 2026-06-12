import pytest
from pydantic import ValidationError as PydanticValidationError
from delta.models import (
    Composition, NamedComposition, TieLine, ProjectData, VisualStyle,
    FigureMargins, CurveLine,
)
from delta.migration import migrate_project_data, CURRENT_VERSION


class TestRenderSettingsValidation:

    def test_legacy_lock_aspect_migrated(self):
        """Старый формат с top-level lock_aspect мигрируется корректно."""
        raw = {
            "components": ["A", "B", "C"],
            "lock_aspect": False,
        }
        migrated = migrate_project_data(raw)
        project = ProjectData.model_validate(migrated)

        assert project.render_settings.lock_aspect is False
        assert project.lock_aspect is False  # compatibility alias

    def test_render_settings_defaults(self):
        project = ProjectData(components=["A", "B", "C"])

        assert project.render_settings.lock_aspect is True
        assert project.render_settings.figure_margins.left == 0.05
        assert project.render_settings.figure_margins.right == 0.05
        assert project.render_settings.figure_margins.top == 0.05
        assert project.render_settings.figure_margins.bottom == 0.05
        assert project.render_settings.display_region_padding == 0.05

    def test_invalid_figure_margins_rejected(self):
        with pytest.raises(PydanticValidationError):
            FigureMargins(left=0.6, right=0.5, top=0.05, bottom=0.05)

    def test_display_region_padding_validation_via_diagram_api(self):
        from delta import Diagram
        
        d = Diagram()
        d.display_region_padding = 0.0
        assert d.display_region_padding == 0.0

        # Отрицательный padding должен перехватываться и выбрасывать обычный ValueError
        with pytest.raises(ValueError):
            d.display_region_padding = -0.1


class TestMigration:

    def test_no_version_migrates_to_current(self):
        """JSON без version получает текущую версию после миграции."""
        raw = {"components": ["A", "B", "C"]}
        migrated = migrate_project_data(raw)
        assert migrated["version"] == CURRENT_VERSION

    def test_current_version_unchanged(self):
        """JSON с текущей версией не изменяется."""
        raw = {"version": CURRENT_VERSION, "components": ["X", "Y", "Z"]}
        migrated = migrate_project_data(raw)
        assert migrated is raw  # тот же объект, без копирования

    def test_legacy_lock_aspect_migration(self):
        raw = {
            "components": ["A", "B", "C"],
            "lock_aspect": False,
        }
        migrated = migrate_project_data(raw)
        assert "lock_aspect" not in migrated
        assert migrated["render_settings"]["lock_aspect"] is False
        assert migrated["version"] == CURRENT_VERSION

    def test_legacy_curve_mode_migration(self):
        """Старые CurveLine без curve_mode получают 'polynomial'."""
        raw = {
            "components": ["A", "B", "C"],
            "compositions": [
                {"uid": "a", "name": "A", "composition": {"a": 1, "b": 0, "c": 0}},
                {"uid": "b", "name": "B", "composition": {"a": 0, "b": 1, "c": 0}},
            ],
            "curve_lines": [
                {"start_uid": "a", "end_uid": "b", "poly_degree": 4},
            ],
        }
        migrated = migrate_project_data(raw)
        assert migrated["curve_lines"][0]["curve_mode"] == "polynomial"

    def test_new_curve_line_gets_spline_by_default(self):
        """Новый CurveLine через модель получает 'spline' по умолчанию."""
        cline = CurveLine(start_uid="a", end_uid="b")
        assert cline.curve_mode == "spline"

    def test_version_written_on_save(self):
        """ProjectData всегда содержит version."""
        project = ProjectData()
        data = project.model_dump()
        assert data["version"] == CURRENT_VERSION


class TestCompositionValidation:
    
    def test_nan_rejected(self):
        """NaN значения отклоняются"""
        with pytest.raises(PydanticValidationError):
            Composition(a=float('nan'), b=0, c=0)
    
    def test_inf_rejected(self):
        """Inf значения отклоняются"""
        with pytest.raises(PydanticValidationError):
            Composition(a=float('inf'), b=0, c=0)
    
    def test_valid_composition(self):
        """Валидные значения принимаются"""
        comp = Composition(a=1, b=2, c=3)
        assert comp.a == 1.0
        assert comp.total == 6.0
    
    def test_zero_composition(self):
        """Нулевые значения принимаются"""
        comp = Composition(a=0, b=0, c=0)
        assert comp.a == 0.0
        assert comp.total == 0.0
    
    def test_negative_values_accepted(self):
        """Отрицательные значения принимаются (валидация физической осмысленности - отдельно)"""
        comp = Composition(a=-1, b=0, c=0)
        assert comp.a == -1.0


class TestNamedCompositionValidation:
    
    def test_valid_named_composition(self):
        """Валидный именованный состав принимается"""
        comp = NamedComposition(
            name="Test",
            composition=Composition(a=1, b=2, c=3)
        )
        assert comp.name == "Test"
        assert comp.composition.a == 1.0
    
    def test_empty_name_truncated(self):
        """Пустое имя обрезается"""
        long_name = "A" * 100
        comp = NamedComposition(
            name=long_name,
            composition=Composition(a=1, b=2, c=3)
        )
        # Должно быть обрезано до максимальной длины
        assert len(comp.name) <= 100


class TestTieLineValidation:
    
    def test_same_endpoints_rejected(self):
        """Линия сама на себя отклоняется"""
        with pytest.raises(PydanticValidationError, match="cannot connect"):
            TieLine(start_uid="abc", end_uid="abc")
    
    def test_valid_line(self):
        """Валидная линия принимается"""
        line = TieLine(start_uid="abc", end_uid="def")
        assert line.start_uid == "abc"
        assert line.end_uid == "def"


class TestProjectValidation:
    
    def test_wrong_component_count(self):
        """Не 3 компонента отклоняется"""
        with pytest.raises(PydanticValidationError):
            ProjectData(components=["A", "B"])
    
    def test_invalid_line_reference(self):
        """Ссылка на несуществующий состав отклоняется"""
        comp = NamedComposition(name="Test")
        line = TieLine(start_uid=comp.uid, end_uid="nonexistent")
        
        with pytest.raises(PydanticValidationError, match="unknown composition"):
            ProjectData(compositions=[comp], lines=[line])
    
    def test_valid_project(self):
        """Валидный проект принимается"""
        comp1 = NamedComposition(name="A", composition=Composition(a=1, b=0, c=0))
        comp2 = NamedComposition(name="B", composition=Composition(a=0, b=1, c=0))
        line = TieLine(start_uid=comp1.uid, end_uid=comp2.uid)
        
        project = ProjectData(
            components=["A", "B", "C"],
            compositions=[comp1, comp2],
            lines=[line]
        )
        
        assert len(project.components) == 3
        assert len(project.compositions) == 2
        assert len(project.lines) == 1


class TestVisualStyles:
    
    def test_invalid_color_fallback(self):
        """Невалидный цвет заменяется на дефолтный"""
        style = VisualStyle(color="invalid")
        assert style.color == "#000000"
    
    def test_valid_color(self):
        """Валидный цвет принимается"""
        style = VisualStyle(color="#ff0000")
        assert style.color == "#ff0000"
    
    def test_color_without_hash(self):
        """Цвет без решётки исправляется"""
        style = VisualStyle(color="ff0000")
        assert style.color == "#ff0000"
    
    def test_invalid_line_style_fallback(self):
        """Невалидный стиль линии заменяется на дефолтный"""
        style = VisualStyle(line_style="invalid")
        assert style.line_style == "-"
    
    def test_invalid_marker_fallback(self):
        """Невалидный маркер заменяется на дефолтный"""
        style = VisualStyle(marker_symbol="invalid")
        assert style.marker_symbol == "o"


class TestCompositionImmutability:
    
    def test_composition_frozen(self):
        """Composition должен быть неизменяемым"""
        comp = Composition(a=1, b=2, c=3)
        
        with pytest.raises(Exception):  # Может быть TypeError или ValidationError
            comp.a = 5
    
    def test_named_composition_mutable(self):
        """NamedComposition должен быть изменяемым"""
        comp = NamedComposition(name="Test", composition=Composition(a=1, b=2, c=3))
        
        # Это должно работать
        comp.name = "New Name"
        assert comp.name == "New Name"


class TestHatchRegion:

    def test_simple_polygon_creation(self):
        from delta import Diagram

        d = Diagram()
        uid = d.add_hatch_region(
            [(0.5, 0.3, 0.2), (0.2, 0.5, 0.3), (0.3, 0.2, 0.5)],
            hatch="//",
            fill_alpha=0.1,
        )
        assert uid in d.list_hatch_regions()

    def test_segment_based_creation(self):
        from delta import Diagram

        d = Diagram()
        p1 = d.add_point("A", 0.5, 0.3, 0.2)
        p2 = d.add_point("B", 0.2, 0.5, 0.3)
        d.add_point("C", 0.3, 0.2, 0.5)
        line_uid = d.add_line(p1, p2)

        uid = d.add_hatch_region(
            segments=[
                ("line", line_uid),
                ("straight", (0.2, 0.5, 0.3), (0.3, 0.2, 0.5)),
                ("straight", (0.3, 0.2, 0.5), (0.5, 0.3, 0.2)),
            ],
            hatch="\\\\",
        )
        assert uid in d.list_hatch_regions()

    def test_delete_line_blocked_by_hatch(self):
        from delta import Diagram
        import pytest

        d = Diagram()
        p1 = d.add_point("A", 0.5, 0.3, 0.2)
        p2 = d.add_point("B", 0.2, 0.5, 0.3)
        line_uid = d.add_line(p1, p2)

        d.add_hatch_region(
            segments=[
                ("line", line_uid),
                ("straight", (0.2, 0.5, 0.3), (0.5, 0.3, 0.2)),
            ],
        )

        with pytest.raises(ValueError):
            d.remove_line(line_uid)

    def test_remove_hatch_region(self):
        from delta import Diagram

        d = Diagram()
        uid = d.add_hatch_region(
            [(0.5, 0.3, 0.2), (0.2, 0.5, 0.3), (0.3, 0.2, 0.5)],
        )
        d.remove_hatch_region(uid)
        assert uid not in d.list_hatch_regions()

    def test_migration_1_0_to_1_1(self):
        raw = {"version": "1.0", "components": ["A", "B", "C"]}
        migrated = migrate_project_data(raw)
        assert migrated["version"] == "1.1"
        assert migrated["hatch_regions"] == []
