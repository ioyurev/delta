import numpy as np
from typing import Tuple, Optional, List
from fractions import Fraction
from math import gcd
from functools import reduce
from core.models import Composition, CompositionError
from core.constants import (
    EPSILON_ZERO,
    EPSILON_BOUNDARY,
    RATIO_MAX_DENOMINATOR,
    RATIO_MAX_VALUE,
)
from core.constants import TRIANGLE_HEIGHT as H
from loguru import logger  # <--- Импорт

def _check_finite(value: float, name: str) -> None:
    """Проверка на NaN/Inf"""
    if np.isnan(value) or np.isinf(value):
        raise ValueError(f"{name} cannot be NaN or Infinity: {value}")

def get_vertices(is_inverted: bool) -> Tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Возвращает координаты вершин (A, B, C) в декартовой системе"""
    if is_inverted:
        # C внизу (y=0), A/B сверху (y=H)
        v_a = np.array([0.0, H])
        v_b = np.array([1.0, H])
        v_c = np.array([0.5, 0.0])
    else:
        # A/B снизу (y=0), C сверху (y=H)
        v_a = np.array([0.0, 0.0])
        v_b = np.array([1.0, 0.0])
        v_c = np.array([0.5, H])
    return v_a, v_b, v_c

def bary_to_cart(comp: Composition, is_inverted: bool) -> np.ndarray:
    """Перевод из барицентрических (Composition) в декартовы (x,y)"""
    # ✅ ЯВНО вызываем normalized — читатель понимает, что происходит
    a, b, c = comp.normalized
    
    v_a, v_b, v_c = get_vertices(is_inverted)
    return a * v_a + b * v_b + c * v_c

def cart_to_bary(x: float, y: float, is_inverted: bool) -> Composition:
    """
    Перевод из декартовых (x,y) обратно в барицентрические.
    Использует матричный метод, основанный на реальных координатах вершин.
    """
    # Валидация
    _check_finite(x, "x")
    _check_finite(y, "y")
    
    # 1. Получаем координаты текущих вершин
    # v_a, v_b, v_c - это numpy массивы [x, y]
    v_a, v_b, v_c = get_vertices(is_inverted)
    
    # 2. Формируем векторы сторон треугольника относительно A
    # Вектор AB и Вектор AC
    vec_ab = v_b - v_a
    vec_ac = v_c - v_a
    
    # Вектор от A до точки P(x,y)
    vec_ap = np.array([x - v_a[0], y - v_a[1]])
    
    # 3. Решаем систему линейных уравнений
    # P = A + b * AB + c * AC
    # P - A = b * AB + c * AC
    # Это система: 
    #   b * AB_x + c * AC_x = AP_x
    #   b * AB_y + c * AC_y = AP_y
    
    matrix = np.array([
        [vec_ab[0], vec_ac[0]],
        [vec_ab[1], vec_ac[1]]
    ])
    
    try:
        # Решаем matrix * [b, c] = vec_ap
        solution = np.linalg.solve(matrix, vec_ap)
        b, c = solution[0], solution[1]
        
        # a + b + c = 1
        a = 1.0 - b - c
        
        return Composition(a, b, c)
        
    except np.linalg.LinAlgError:
        # Если матрица вырождена (треугольник схлопнулся в линию), возвращаем 0
        return Composition(0, 0, 0)

def solve_intersection(p1_comp: Composition, p2_comp: Composition, 
                       p3_comp: Composition, p4_comp: Composition) -> Optional[Composition]:
    """Находит пересечение двух отрезков в барицентрических координатах."""
    # ✅ Явно используем normalized
    try:
        A = np.array(p1_comp.normalized[:2])
        B = np.array(p2_comp.normalized[:2])
        C = np.array(p3_comp.normalized[:2])
        D = np.array(p4_comp.normalized[:2])
    except CompositionError:
        return None
    
    # A + t(B-A) = C + u(D-C)
    v1 = B - A
    v2 = C - D 
    rhs = C - A
    
    matrix = np.array([[v1[0], v2[0]], [v1[1], v2[1]]])
    
    try:
        sol = np.linalg.solve(matrix, rhs)
        t = sol[0]
        # Восстанавливаем полную координату (3 компонента)
        full_A = np.array(p1_comp.normalized)
        full_B = np.array(p2_comp.normalized)
        res = full_A + t * (full_B - full_A)
        return Composition(res[0], res[1], res[2])
    except np.linalg.LinAlgError:
        logger.warning("Intersection solver: Matrix is singular (lines parallel?)")
        return None

def get_line_triangle_intersections(p1: Composition, p2: Composition) -> List[Composition]:
    """
    Находит точки пересечения прямой, проходящей через p1 и p2, 
    с границами треугольника Гиббса (a=0, b=0, c=0).
    Возвращает список из 2 точек (вход и выход), если прямая пересекает треугольник.
    """
    # Границы треугольника определяются как линии между вершинами:
    # A(1,0,0), B(0,1,0), C(0,0,1)
    
    # Вершины
    cA = Composition.vertex_a()
    cB = Composition.vertex_b()
    cC = Composition.vertex_c()
    
    # Грани: AB (c=0), BC (a=0), AC (b=0)
    boundaries = [
        (cA, cB), # c=0
        (cB, cC), # a=0
        (cC, cA)  # b=0
    ]
    
    intersections: list[Composition] = []
    
    for b_start, b_end in boundaries:
        # Ищем пересечение нашей линии (p1-p2) с гранью (b_start-b_end)
        res = solve_intersection(p1, p2, b_start, b_end)
        if res:
            # Проверяем, лежит ли точка "внутри" отрезка грани (все компоненты >= -epsilon)
            # solve_intersection возвращает математическое пересечение бесконечных прямых,
            # нам нужно отфильтровать те, что лежат на самом треугольнике.
            try:
                vals = res.normalized
                # Допуск на погрешность float
                if all(v >= -EPSILON_BOUNDARY for v in vals): 
                    # Проверяем дубликаты (чтобы не добавить одну точку дважды, если попали в вершину)
                    is_duplicate = False
                    for existing in intersections:
                        if existing.normalized_is_close(res):
                            is_duplicate = True
                            break
                    if not is_duplicate:
                        intersections.append(res)
            except CompositionError:
                continue
    
    return intersections

def get_lever_fraction(p_start: Composition, p_end: Composition, p_point: Composition) -> float:
    """
    Возвращает параметр t, где Point = Start + t * (End - Start).
    """
    # ✅ Явное преобразование
    s = np.array(p_start.normalized)
    e = np.array(p_end.normalized)
    p = np.array(p_point.normalized)
    
    vec_line = e - s
    vec_point = p - s
    
    len_sq = np.dot(vec_line, vec_line)
    if len_sq < EPSILON_ZERO:
        # Возвращаем 0.0 вместо исключения для совместимости
        return 0.0 
        
    t = np.dot(vec_point, vec_line) / len_sq
    return t

def get_barycentric_from_cartesian(
    x1: float, y1: float, 
    x2: float, y2: float, 
    x3: float, y3: float, 
    px: float, py: float
) -> tuple[float, float, float]:
    """
    Вычисляет барицентрические координаты (u, v, w).
    Возвращает (inf, inf, inf), если треугольник вырожден.
    """
    det_T = (y2 - y3) * (x1 - x3) + (x3 - x2) * (y1 - y3)
    
    # Защита от вырожденных треугольников (площадь ~ 0)
    if abs(det_T) < EPSILON_ZERO:
        return float('inf'), float('inf'), float('inf')
        
    u = ((y2 - y3) * (px - x3) + (x3 - x2) * (py - y3)) / det_T
    v = ((y3 - y1) * (px - x3) + (x1 - x3) * (py - y3)) / det_T
    w = 1.0 - u - v
    
    return u, v, w

def get_closest_composition_on_segment(comp_a: Composition, comp_b: Composition, 
                                       target: Composition, is_inverted: bool) -> Composition:
    """
    Находит проекцию точки target на отрезок AB в декартовом пространстве.
    Возвращает Composition этой проекции.
    """
    # 1. Переводим все в декартовы
    A = bary_to_cart(comp_a, is_inverted)
    B = bary_to_cart(comp_b, is_inverted)
    P = bary_to_cart(target, is_inverted)
    
    # 2. Векторная математика (проекция P на прямую AB с ограничением отрезком)
    vec_ab = B - A
    vec_ap = P - A
    
    len_sq = np.dot(vec_ab, vec_ab)
    
    if len_sq < EPSILON_ZERO:
        # Точки A и B совпадают
        return comp_a
        
    t = np.dot(vec_ap, vec_ab) / len_sq
    
    # Ограничиваем t (clamp), чтобы точка не вылетала за пределы отрезка (экстраполяция)
    # Если нужно разрешить экстраполяцию проекции, уберите clip
    t = np.clip(t, 0.0, 1.0)
    
    # 3. Координаты проекции
    proj_cart = A + t * vec_ab
    
    # 4. Обратно в барицентрические
    return cart_to_bary(proj_cart[0], proj_cart[1], is_inverted)

def is_point_on_line(p_start: Composition, p_end: Composition, p_point: Composition, tol: float = 0.01) -> bool:
    """
    Проверяет, лежит ли точка p_point на прямой, проходящей через p_start и p_end.
    tol: допустимое отклонение (по умолчанию 1%)
    """
    # 1. Получаем векторы
    s = np.array(p_start.normalized)
    e = np.array(p_end.normalized)
    p = np.array(p_point.normalized)

    # 2. Вектор прямой (Start -> End)
    vec_line = e - s
    line_len_sq = np.dot(vec_line, vec_line)
    
    # Защита: если точки базиса совпадают
    if line_len_sq < EPSILON_ZERO:
        # Если базис - это одна точка, проверяем совпадение целевой точки с ней
        return bool(np.linalg.norm(p - s) < tol)

    # 3. Вектор к точке (Start -> Point)
    vec_point = p - s

    # 4. Считаем расстояние от точки до прямой
    # d = |vec_line x vec_point| / |vec_line|
    # Используем векторное произведение (cross product) в 3D
    cross_prod = np.cross(vec_line, vec_point)
    distance = np.linalg.norm(cross_prod) / np.sqrt(line_len_sq)
    
    return bool(distance < tol)

def find_integer_ratio(floats: List[float]) -> Optional[List[int]]:
    """
    Находит целочисленное соотношение для списка долей.
    
    Примеры:
        [0.5, 0.5] → [1, 1]
        [0.333, 0.333, 0.333] → [1, 1, 1]
    
    Returns:
        List[int]: Список целых чисел или None, если соотношение слишком сложное.
    """
    if not floats or all(f == 0 for f in floats):
        return None
    
    try:
        # 1. Конвертируем float в Fraction с ограничением знаменателя
        fractions = []
        for f in floats:
            if f < -1e-9: # Допускаем небольшой минус из-за погрешности float
                return None
            # Ограничиваем знаменатель константой из настроек
            frac = Fraction(abs(f)).limit_denominator(RATIO_MAX_DENOMINATOR)
            fractions.append(frac)
        
        # 2. Находим общий знаменатель (НОК всех знаменателей)
        denominators = [frac.denominator for frac in fractions]
        
        def lcm(a, b):
            return abs(a * b) // gcd(a, b)
            
        common_denom = reduce(lcm, denominators)
        
        # 3. Приводим к общему знаменателю → получаем целые числители
        integers = [int(frac.numerator * (common_denom // frac.denominator)) for frac in fractions]
        
        # 4. Сокращаем на НОД всех чисел
        common_gcd = reduce(gcd, [i for i in integers if i != 0], integers[0] if integers else 1)
        if common_gcd > 1:
            integers = [i // common_gcd for i in integers]
        
        # 5. Проверяем, что числа не превышают разумный предел
        if any(i > RATIO_MAX_VALUE for i in integers):
            return None
            
        return integers
        
    except Exception as e:
        logger.warning(f"Error calculating ratio: {e}")
        return None
