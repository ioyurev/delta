import pytest
from core.project_controller import ProjectController
from core.exceptions import ValidationError

class TestDegenerateLines:
    
    def setup_method(self):
        self.controller = ProjectController()
    
    def test_create_line_same_coordinates_fails(self):
        """Нельзя создать линию между составами с одинаковыми координатами"""
        uid1 = self.controller.create_composition("A", 0.5, 0.3, 0.2)
        uid2 = self.controller.create_composition("B", 0.5, 0.3, 0.2)  # Те же координаты!
        
        with pytest.raises(ValidationError, match="identical coordinates"):
            self.controller.create_line(uid1, uid2)
    
    def test_create_line_close_coordinates_fails(self):
        """Нельзя создать линию между составами с почти одинаковыми координатами"""
        uid1 = self.controller.create_composition("A", 0.5, 0.3, 0.2)
        uid2 = self.controller.create_composition("B", 0.50001, 0.29999, 0.2)  # В пределах допуска
        
        with pytest.raises(ValidationError, match="identical coordinates"):
            self.controller.create_line(uid1, uid2)
    
    def test_create_line_different_coordinates_ok(self):
        """Можно создать линию между составами с разными координатами"""
        uid1 = self.controller.create_composition("A", 0.5, 0.3, 0.2)
        uid2 = self.controller.create_composition("B", 0.3, 0.5, 0.2)
        
        line_uid = self.controller.create_line(uid1, uid2)
        assert line_uid is not None
    
    def test_update_composition_creates_degenerate_line_fails(self):
        """Нельзя изменить координаты так, чтобы создать вырожденную линию"""
        uid1 = self.controller.create_composition("A", 0.5, 0.3, 0.2)
        uid2 = self.controller.create_composition("B", 0.3, 0.5, 0.2)
        self.controller.create_line(uid1, uid2)
        
        # Пытаемся изменить B чтобы координаты совпали с A
        from core.models import CompositionUpdate
        update = CompositionUpdate(a=0.5, b=0.3, c=0.2)
        
        with pytest.raises(ValidationError, match="zero-length line"):
            self.controller.update_composition(uid2, update)
    
    def test_update_line_endpoints_to_same_coordinates_fails(self):
        """Нельзя изменить концы линии на составы с одинаковыми координатами"""
        uid1 = self.controller.create_composition("A", 0.5, 0.3, 0.2)
        uid2 = self.controller.create_composition("B", 0.3, 0.5, 0.2)
        uid3 = self.controller.create_composition("C", 0.5, 0.3, 0.2)  # Как A
        
        line_uid = self.controller.create_line(uid1, uid2)
        
        with pytest.raises(ValidationError, match="identical coordinates"):
            self.controller.update_line_endpoints(line_uid, uid1, uid3)
    
    def test_update_line_endpoints_different_coordinates_ok(self):
        """Можно изменить концы линии на составы с разными координатами"""
        uid1 = self.controller.create_composition("A", 0.5, 0.3, 0.2)
        uid2 = self.controller.create_composition("B", 0.3, 0.5, 0.2)
        uid3 = self.controller.create_composition("C", 0.2, 0.3, 0.5)
        
        line_uid = self.controller.create_line(uid1, uid2)
        
        # Меняем конец линии на другой состав
        self.controller.update_line_endpoints(line_uid, uid1, uid3)
        
        # Проверяем что линия обновилась
        line = self.controller.get_line(line_uid)
        assert line.start_uid == uid1
        assert line.end_uid == uid3
    
    def test_update_composition_no_coordinate_changes_ok(self):
        """Можно изменить состав без изменения координат (например, имя)"""
        uid1 = self.controller.create_composition("A", 0.5, 0.3, 0.2)
        uid2 = self.controller.create_composition("B", 0.3, 0.5, 0.2)
        self.controller.create_line(uid1, uid2)
        
        # Меняем только имя
        from core.models import CompositionUpdate
        update = CompositionUpdate(name="A_new")
        
        # Это должно пройти без ошибок
        self.controller.update_composition(uid1, update)
        
        # Проверяем что имя изменилось
        comp = self.controller.get_composition(uid1)
        assert comp.name == "A_new"
    
    def test_create_line_same_uid_fails(self):
        """Нельзя создать линию с одинаковыми UID"""
        uid1 = self.controller.create_composition("A", 0.5, 0.3, 0.2)
        
        with pytest.raises(ValidationError, match="start and end must be different"):
            self.controller.create_line(uid1, uid1)
    
    def test_update_line_endpoints_same_uid_fails(self):
        """Нельзя изменить концы линии на одинаковые UID"""
        uid1 = self.controller.create_composition("A", 0.5, 0.3, 0.2)
        uid2 = self.controller.create_composition("B", 0.3, 0.5, 0.2)
        line_uid = self.controller.create_line(uid1, uid2)
        
        with pytest.raises(ValidationError, match="Start and end must be different"):
            self.controller.update_line_endpoints(line_uid, uid1, uid1)
