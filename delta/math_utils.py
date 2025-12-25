import numpy as np
import math
from typing import Tuple, Optional, List
from fractions import Fraction
from math import gcd
from functools import reduce
from delta.models import Composition, CompositionError
from delta.exceptions import DegenerateBasisError, DegenerateTriangleError
from delta.constants import (
    EPSILON_ZERO,
    EPSILON_BOUNDARY,
    RATIO_MAX_DENOMINATOR,
    RATIO_TOLERANCE,
    TOLERANCE_ON_LINE_STRICT,
)
from delta.constants import TRIANGLE_HEIGHT as H
from loguru import logger  # <--- Импорт

def _check_finite(value: float, name: str) -> None:
    """
    Проверка на NaN/Inf для входных параметров функций.
    
    Note:
        Composition уже проверяет свои координаты в __post_init__.
        Эта функция для проверки "сырых" float параметров (x, y координаты).
    """
    if math.isnan(value) or math.isinf(value):
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

def _clamp_barycentric(val: float) -> float:
    """Очищает микро-шум (например -1e-17 -> 0.0)"""
    if abs(val) < EPSILON_ZERO:
        return 0.0
    # Опционально: можно прижимать 1.00000000000001 к 1.0, 
    # но normalize() это и так сделает. Главное убрать отрицательные нули.
    return val

def cart_to_bary(x: float, y: float, is_inverted: bool) -> Composition:
    """
    Перевод из декартовых (x,y) обратно в барицентрические.
    
    Использует строгие АНАЛИТИЧЕСКИЕ формулы для равностороннего треугольника.
    Это точнее, чем матричный метод (np.linalg.solve).
    """
    _check_finite(x, "x")
    _check_finite(y, "y")

    # Высота треугольника
    h = H # np.sqrt(3) / 2
    
    # Аналитический вывод:
    # Для обычного треугольника (C вверху):
    # y = c * h  =>  c = y / h
    # x = b + c * 0.5  =>  b = x - c * 0.5
    # a = 1 - b - c
    
    if not is_inverted:
        # Вершина C вверху (y=h), A(0,0), B(1,0)
        c = y / h
        b = x - (c * 0.5)
        a = 1.0 - b - c
    else:
        # Вершина C внизу (y=0), A(0,h), B(1,h)
        # Координата Y "перевернута" относительно высоты
        # y_inv = h - y
        # Тогда c = (h - y) / h = 1 - y/h
        c = 1.0 - (y / h)
        # x работает так же, но нужно учесть смещение базы
        # Геометрия перевернутого: A(0,h), B(1,h), C(0.5, 0)
        # Это сложнее вывести, проще использовать симметрию:
        # Если перевернуть Y (y' = h - y), это станет обычным треугольником
        
        y_prime = h - y
        c_prime = y_prime / h # Это реальное c
        b_prime = x - (c_prime * 0.5)
        a_prime = 1.0 - b_prime - c_prime
        
        a, b, c = a_prime, b_prime, c_prime

    # Очистка шума (Clamping)
    # Это критически важно для научной точности, чтобы 0.0 не становился -1e-17
    a = _clamp_barycentric(a)
    b = _clamp_barycentric(b)
    c = _clamp_barycentric(c)

    return Composition(a=a, b=b, c=c)

def solve_intersection(p1_comp: Composition, p2_comp: Composition, 
                       p3_comp: Composition, p4_comp: Composition) -> Optional[Composition]:
    """
    Находит пересечение двух отрезков.
    
    СТРОГАЯ НАУЧНАЯ ВЕРСИЯ:
    Вместо решения матриц (np.linalg.solve), переводим задачу в Декартовы координаты
    и используем аналитическую формулу через векторное произведение.
    Это исключает ошибки численных методов.
    """
    # 1. Переводим все точки в Декартовы (теперь это точная операция благодаря аналитическому cart_to_bary)
    # Используем is_inverted=False как базис, так как пересечение инвариантно к проекции
    # (нам важно относительное положение).
    try:
        A = bary_to_cart(p1_comp, False)
        B = bary_to_cart(p2_comp, False)
        C = bary_to_cart(p3_comp, False)
        D = bary_to_cart(p4_comp, False)
    except CompositionError:
        return None

    # 2. Формула пересечения прямых через определители (Cross Product)
    # Прямая AB задается P = A + t(B-A)
    # Прямая CD задается Q = C + u(D-C)
    # Пересечение: A + t(B-A) = C + u(D-C)
    # P = A + t*R, Q = C + u*S
    
    R = B - A
    S = D - C
    
    # Знаменатель (векторное произведение направляющих векторов)
    # Аналог определителя матрицы 2x2. Если он 0, прямые параллельны.
    denom = R[0] * S[1] - R[1] * S[0]
    
    if abs(denom) < EPSILON_ZERO:
        logger.warning("Intersection solver: Lines are parallel (denom ~ 0)")
        return None
        
    # Числитель для параметра t (пересечение относительно отрезка AB)
    # t = (C - A) x S / (R x S)
    AC = C - A
    numer_t = AC[0] * S[1] - AC[1] * S[0]
    
    t = numer_t / denom
    
    # 3. Вычисляем точку пересечения в Декартовых
    intersect_cart = A + t * R
    
    # 4. Переводим обратно в Барицентрические
    # (Функция cart_to_bary теперь тоже аналитическая, потерь нет)
    return cart_to_bary(intersect_cart[0], intersect_cart[1], is_inverted=False)

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
    
    Правило рычага: t=0 означает точку Start, t=1 означает точку End.
    
    Returns:
        float: Параметр интерполяции t
        
    Raises:
        DegenerateBasisError: Если Start и End совпадают (нулевая конода)
    """
    # ✅ Явное преобразование
    s = np.array(p_start.normalized)
    e = np.array(p_end.normalized)
    p = np.array(p_point.normalized)
    
    vec_line = e - s
    vec_point = p - s
    
    len_sq = np.dot(vec_line, vec_line)
    if len_sq < EPSILON_ZERO:
        raise DegenerateBasisError("Start and End compositions are identical (zero-length tie-line)")
        
    t = np.dot(vec_point, vec_line) / len_sq
    return float(t)

def get_barycentric_from_cartesian(
    x1: float, y1: float, 
    x2: float, y2: float, 
    x3: float, y3: float, 
    px: float, py: float
) -> tuple[float, float, float]:
    """
    Вычисляет барицентрические координаты (u, v, w) точки (px, py)
    относительно треугольника с вершинами (x1,y1), (x2,y2), (x3,y3).
    
    Returns:
        tuple[float, float, float]: Координаты (u, v, w), сумма = 1.0
        
    Raises:
        DegenerateTriangleError: Если треугольник вырожден (площадь ≈ 0)
    """
    det_T = (y2 - y3) * (x1 - x3) + (x3 - x2) * (y1 - y3)
    
    if abs(det_T) < EPSILON_ZERO:
        raise DegenerateTriangleError(
            "Basis triangle has zero area (three compositions are collinear)"
        )
        
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

def is_point_on_line(
    p_start: Composition, 
    p_end: Composition, 
    p_point: Composition, 
    tol: float | None = None
) -> bool:
    """
    Проверяет, лежит ли точка на прямой в барицентрических координатах.
    
    Использует абсолютный допуск в пространстве нормализованных координат.
    Это обеспечивает одинаковую точность независимо от длины линии.
    
    Args:
        p_start: Начало линии
        p_end: Конец линии  
        p_point: Проверяемая точка
        tol: Абсолютный допуск (default: TOLERANCE_ON_LINE_STRICT = 1e-4)
        
    Returns:
        True если точка лежит на прямой с заданной точностью
        
    Note:
        Для UI-задач (определение hover/click) используйте tol=TOLERANCE_ON_LINE_UI
    """
    if tol is None:
        tol = TOLERANCE_ON_LINE_STRICT
    
    try:
        s = np.array(p_start.normalized)
        e = np.array(p_end.normalized)
        p = np.array(p_point.normalized)
    except CompositionError:
        return False

    # Вектор линии
    vec_line = e - s
    line_len_sq = np.dot(vec_line, vec_line)
    
    # Вырожденный случай: точки базиса совпадают
    if line_len_sq < EPSILON_ZERO:
        # Проверяем совпадение с начальной точкой
        return bool(np.linalg.norm(p - s) < tol)

    # Вектор от начала к проверяемой точке
    vec_point = p - s

    # Расстояние от точки до прямой через векторное произведение
    # В 3D: d = |vec_line × vec_point| / |vec_line|
    cross_prod = np.cross(vec_line, vec_point)
    distance = np.linalg.norm(cross_prod) / np.sqrt(line_len_sq)
    
    return bool(distance < tol)

def _lcm(a: int, b: int) -> int:
    """Наименьшее общее кратное"""
    return abs(a * b) // gcd(a, b) if a and b else max(abs(a), abs(b))


def find_integer_ratio(floats: List[float]) -> List[int]:
    """
    Универсальный поиск целочисленного соотношения.
    
    Принцип:
    Ступенчатый поиск (Tiers):
    1. Сначала пытаемся найти простые дроби (знаменатель до 100).
    2. Если погрешность велика, повышаем лимит до 10,000.
    3. Если и это не подходит, используем максимальный лимит.
    
    Это позволяет для 0.500005 вернуть [1, 1] (упрощение), 
    а для 0.995025 (200:1) вернуть [200, 1] (точность).
    
    Returns:
        Список целых чисел, представляющих соотношение.
        Пустой список для пустого входа.
        Список нулей если все входные значения нулевые.
    """
    if not floats:
        return []
    
    # Проверка: все значения нулевые или близки к нулю
    if all(abs(f) < EPSILON_ZERO for f in floats):
        return [0] * len(floats)
    
    total_val = math.fsum(floats)
    if abs(total_val) < EPSILON_ZERO:
        return [0] * len(floats)
        
    normalized = [f / total_val for f in floats]
    
    # Ступени сложности знаменателя:
    # 100: Классическая химия (отсекает шум типа 0.500005 -> 1/2)
    # 10000: Сложные сплавы (A200 B1)
    # MAX: Высокоточная стехиометрия
    tiers = [100, 10000, RATIO_MAX_DENOMINATOR]
    
    for limit in tiers:
        try:
            # 1. Поиск дробей с текущим лимитом
            fractions = [
                Fraction(abs(f)).limit_denominator(limit) 
                for f in normalized
            ]
            
            # 2. Приведение к целым через НОК знаменателей
            denoms = [fr.denominator for fr in fractions]
            common_denom = reduce(_lcm, denoms, 1)
            
            integers = [
                int(fr.numerator * (common_denom // fr.denominator)) 
                for fr in fractions
            ]
            
            # 3. Сокращение на НОД
            non_zero_ints = [i for i in integers if i != 0]
            if not non_zero_ints:
                # Все дроби дали 0 — переходим к следующему tier
                continue
                
            common_gcd = reduce(gcd, non_zero_ints)
            if common_gcd > 1:
                integers = [i // common_gcd for i in integers]
                
            # 4. ВАЛИДАЦИЯ ТОЧНОСТИ
            sum_int = math.fsum(integers)
            
            # Защита от деления на ноль
            if sum_int < EPSILON_ZERO:
                continue
            
            recalc = [i / sum_int for i in integers]
            
            # Проверка точности для каждого компонента
            is_valid = all(
                abs(orig - calc) <= RATIO_TOLERANCE
                for orig, calc in zip(normalized, recalc)
            )
            
            if is_valid:
                return integers
                    
        except (ValueError, ZeroDivisionError, OverflowError):
            # Переходим к следующему tier при любых численных проблемах
            continue

    # Если ни один уровень не подошел — используем fallback
    return _fallback_scaling(normalized)

def _fallback_scaling(normalized: List[float]) -> List[int]:
    """
    Запасной вариант: масштабирование с округлением.
    
    Используется когда ступенчатый поиск дробей не дал
    результата с требуемой точностью.
    """
    SCALE = 100000
    ints = [int(round(f * SCALE)) for f in normalized]
    
    # Коррекция суммы (округление может дать не ровно SCALE)
    current_sum = sum(ints)
    diff = SCALE - current_sum
    
    if diff != 0 and ints:
        # Находим индекс максимального элемента для коррекции
        max_val = max(ints)
        if max_val > 0:
            max_idx = ints.index(max_val)
            ints[max_idx] += diff
    
    # Сокращение на НОД
    non_zero = [i for i in ints if i != 0]
    if non_zero:
        common = reduce(gcd, non_zero)
        if common > 1:
            ints = [i // common for i in ints]
    
    return ints


def are_compositions_collinear(
    p1: Composition, 
    p2: Composition, 
    p3: Composition, 
    tol: float | None = None
) -> bool:
    """
    Проверяет, лежат ли три точки на одной прямой.
    
    Использует площадь треугольника: если она близка к нулю,
    точки коллинеарны.
    
    Args:
        p1, p2, p3: Три состава для проверки
        tol: Допуск для определения коллинеарности 
             (default: TOLERANCE_ON_LINE_STRICT)
    
    Returns:
        True если точки коллинеарны (лежат на одной прямой)
    """
    if tol is None:
        tol = TOLERANCE_ON_LINE_STRICT
    
    try:
        # Получаем нормализованные координаты
        a1 = np.array(p1.normalized)
        a2 = np.array(p2.normalized)
        a3 = np.array(p3.normalized)
    except CompositionError:
        # Если хотя бы одна точка невалидна — считаем коллинеарными
        # (вырожденный случай)
        return True
    
    # Векторы от первой точки
    v1 = a2 - a1
    v2 = a3 - a1
    
    # Площадь параллелограмма = |v1 × v2|
    # Для коллинеарных точек площадь ≈ 0
    cross = np.cross(v1, v2)
    area = np.linalg.norm(cross)
    
    return bool(area < tol)


def get_triangle_area(p1: Composition, p2: Composition, p3: Composition) -> float:
    """
    Вычисляет площадь треугольника в барицентрических координатах.
    
    Returns:
        Площадь (0 для вырожденного треугольника)
    """
    try:
        a1 = np.array(p1.normalized)
        a2 = np.array(p2.normalized)
        a3 = np.array(p3.normalized)
    except CompositionError:
        return 0.0
    
    v1 = a2 - a1
    v2 = a3 - a1
    
    cross = np.cross(v1, v2)
    # Площадь треугольника = половина площади параллелограмма
    return float(np.linalg.norm(cross) / 2)
