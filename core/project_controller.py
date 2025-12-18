from typing import Optional, List, Dict
from core.models import ProjectData, NamedComposition, TieLine, Composition, CompositionUpdate
from core import math_utils
from core.serializer import ProjectSerializer
from loguru import logger

class ProjectController:
    def __init__(self):
        self._project = ProjectData()  # ← Приватный атрибут
        
        # --- КЭШИ ДЛЯ O(1) ДОСТУПА ---
        # Синхронизируются со списками в _project
        self._comp_map: Dict[str, NamedComposition] = {}
        self._line_map: Dict[str, TieLine] = {}

    def _rebuild_cache(self):
        """Пересоздает карты быстрого доступа на основе списков"""
        self._comp_map = {comp.uid: comp for comp in self._project.compositions}
        self._line_map = {line.uid: line for line in self._project.lines}

    # ========== ПУБЛИЧНЫЙ API (только методы) ==========
    
    def has_compositions(self) -> bool:
        """Проверка наличия составов (вместо прямого доступа к списку)"""
        return len(self._project.compositions) > 0
    
    def get_composition_count(self) -> int:
        """Количество составов"""
        return len(self._project.compositions)
    
    def get_line_count(self) -> int:
        """Количество линий"""
        return len(self._project.lines)
    
    def get_components(self) -> List[str]:
        """Возвращает КОПИЮ списка компонентов"""
        return list(self._project.components)
    
    def is_inverted(self) -> bool:
        """Режим треугольника"""
        return self._project.is_inverted

    # --- 1. Публичное свойство для "Чтения" состояния (для Canvas и Table) ---
    @property
    def project_data(self) -> ProjectData:
        """
        Возвращает данные проекта только для чтения/отрисовки.
        НЕ изменяйте данные в полученном объекте вручную.
        Используйте методы контроллера для изменений.
        """
        return self._project

    # --- 2. Методы поиска (Lookups) ---
    
    def get_composition(self, uid: str) -> Optional[NamedComposition]:
        """Безопасный поиск состава по UID"""
        return self._comp_map.get(uid)

    def get_line(self, uid: str) -> Optional[TieLine]:
        """Безопасный поиск линии по UID"""
        return self._line_map.get(uid)
        
    def get_line_endpoints(self, line_uid: str) -> tuple[Optional[NamedComposition], Optional[NamedComposition]]:
        """
        Возвращает объекты составов (начало, конец) для линии.
        Убирает логику поиска из UI.
        """
        line = self.get_line(line_uid)
        if not line:
            return None, None
            
        start_comp = self.get_composition(line.start_uid)
        end_comp = self.get_composition(line.end_uid)
        return start_comp, end_comp

    def get_all_compositions(self) -> List[NamedComposition]:
        """Возвращает список всех составов"""
        return self._project.compositions

    def get_all_lines(self) -> List[TieLine]:
        """Возвращает список всех линий"""
        return self._project.lines
    
    # ========== МУТАЦИИ (изменения только здесь) ==========
    
    def create_composition(self, name: str = "New", a: float = 0.0, b: float = 0.0, c: float = 0.0, show_label: bool = True) -> str:
        """
        Создаёт состав и возвращает его UID.
        Не возвращает сам объект NamedComposition!
        """
        comp = NamedComposition(
            name=name,
            composition=Composition(a, b, c)
        )
        # Применяем настройку видимости метки
        comp.style.show_label = show_label
        
        # 1. Добавляем в список (для порядка и сохранения)
        self._project.compositions.append(comp)
        # 2. Добавляем в кэш (для скорости)
        self._comp_map[comp.uid] = comp
        # bind добавляет контекст к логу (удобно для фильтрации)
        logger.bind(uid=comp.uid).info(f"Created composition '{name}'")
        return comp.uid  # ← Возвращаем только ID

    def update_components(self, names: List[str]):
        if len(names) == 3:
            self._project.components = names

    def update_grid(self, visible: bool, step: float):
        self._project.grid.visible = visible
        self._project.grid.step = step

    def update_composition_style(self, uid: str, color: str, size: float, symbol: str, 
                                 show_label: bool, show_marker: bool): # <--- Новые аргументы
        """Обновляет визуальный стиль конкретного состава"""
        comp = self._get_comp_internal(uid)
        if comp:
            comp.style.color = color
            comp.style.size = size
            comp.style.marker_symbol = symbol
            comp.style.show_label = show_label   # <--- Обновляем
            comp.style.show_marker = show_marker # <--- Обновляем

    def update_view_mode(self, is_inverted: bool):
        """
        Переключает режим треугольника.
        Смещения меток (label_offset) не зависят от инверсии, они относительны.
        """
        if self._project.is_inverted == is_inverted:
            return
        self._project.is_inverted = is_inverted

    def update_composition(self, uid: str, update: CompositionUpdate):
        """
        Обновляет состав, используя DTO.
        Принимает только те поля, которые не None.
        """
        # Используем наш новый быстрый lookup (если вы применили шаг 2)
        comp = self.get_composition(uid)
        if not comp:
            return
        
        # 1. Обновление имени
        if update.name is not None:
            comp.name = update.name

        # 2. Обновление координат (если хоть одна изменилась)
        # Нам нужно проверить, меняется ли химия, чтобы пересоздать Immutable Composition
        if update.a is not None or update.b is not None or update.c is not None:
            new_a = update.a if update.a is not None else comp.composition.a
            new_b = update.b if update.b is not None else comp.composition.b
            new_c = update.c if update.c is not None else comp.composition.c
            
            comp.composition = Composition(new_a, new_b, new_c)

    def delete_composition(self, uid: str):
        logger.info(f"Deleting composition: {uid}")
        # 1. Удаляем из кэша O(1)
        if uid in self._comp_map:
            del self._comp_map[uid]
            
        # 2. Удаляем из списка O(N) - это неизбежно для списка, но происходит редко
        self._project.compositions = [p for p in self._project.compositions if p.uid != uid]
        
        # Каскадное удаление линий
        lines_to_remove = [line for line in self._project.lines 
                           if line.start_uid == uid or line.end_uid == uid]
        
        for line in lines_to_remove:
            self.delete_line(line.uid) # Переиспользуем логику удаления линий

    # ========== ПРИВАТНЫЕ МЕТОДЫ ==========
    
    def _get_comp_internal(self, uid: str) -> Optional[NamedComposition]:
        """Внутренний метод для доступа к NamedComposition"""
        return self.get_composition(uid)
    
    def set_composition_label_pos(self, uid: str, x: float, y: float):
        """
        Принимает абсолютные координаты (x, y), куда пользователь перетащил метку.
        Вычисляет и сохраняет смещение (offset) относительно точки состава.
        """
        comp = self.get_composition(uid)
        if not comp:
            return

        is_inv = self._project.is_inverted
        
        # Используем bary_to_cart (с нормализацией), а не raw!
        # Это гарантирует, что мы считаем отступ от той точки, которая реально на экране.
        try:
            pt = math_utils.bary_to_cart(comp.composition, is_inv)
        except ValueError:
            return

        # Приводим к float (важно для JSON сериализации и стабильности)
        dx = float(x - pt[0])
        dy = float(y - pt[1])
        
        comp.label_offset = (dx, dy)

    # --- CRUD для Линий ---
    def create_line(self, uid1: str, uid2: str) -> Optional[TieLine]:
        # Проверка на дубликаты
        for line in self._project.lines:
            if {line.start_uid, line.end_uid} == {uid1, uid2}:
                return None
        
        line = TieLine(start_uid=uid1, end_uid=uid2)
        self._project.lines.append(line)
        self._line_map[line.uid] = line  # <--- Добавляем в кэш
        return line

    def update_line_style(self, uid: str, color: str, style: str, width: float):
        for line in self._project.lines:
            if line.uid == uid:
                line.style.color = color
                line.style.line_style = style
                line.style.size = width
                return

    def delete_line(self, uid: str):
        if uid in self._line_map:
            del self._line_map[uid]
            
        self._project.lines = [line for line in self._project.lines if line.uid != uid]

    def update_line_endpoints(self, line_uid: str, start_uid: str, end_uid: str) -> bool:
        """Обновляет конечные точки существующей линии, не меняя её UID"""
        # Проверка на петлю
        if start_uid == end_uid:
            return False
            
        # Проверка на дубликаты (существует ли уже другая линия с такими концами)
        for line in self._project.lines:
            if line.uid != line_uid: # Пропускаем саму себя
                if {line.start_uid, line.end_uid} == {start_uid, end_uid}:
                    return False
        
        # Поиск и обновление
        for line in self._project.lines:
            if line.uid == line_uid:
                line.start_uid = start_uid
                line.end_uid = end_uid
                return True
        return False

    def set_vertex_label_pos(self, index: int, x: float, y: float):
        """Сохраняет позицию метки вершины (0=A, 1=B, 2=C)"""
        self._project.vertex_labels_pos[str(index)] = (x, y)

    # --- Сериализация ---
    def save_project(self, filepath: str) -> None:
        """
        Сохраняет проект.
        Raises: ProjectFileError если что-то пошло не так.
        """
        # Делегируем работу сериализатору
        ProjectSerializer.save_to_file(self._project, filepath)

    def new_project(self):
        """Сбрасывает проект к начальному состоянию"""
        self._project = ProjectData()
        self._rebuild_cache()
        logger.info("Project reset to new state")

    def load_project(self, filepath: str) -> None:
        """
        Загружает проект.
        Raises: ProjectFileError если что-то пошло не так.
        """
        # 1. Загружаем "чистые" данные
        new_project = ProjectSerializer.load_from_file(filepath)
        
        # 2. Применяем их
        self._project = new_project
        
        # 3. ВАЖНО: Перестраиваем кэш!
        # Без этой строки поиск по UID не будет работать для загруженных проектов
        self._rebuild_cache()
