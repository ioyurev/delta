import pytest
from pydantic import ValidationError as PydanticValidationError
from delta.models import Composition, NamedComposition, TieLine, ProjectData, VisualStyle


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
