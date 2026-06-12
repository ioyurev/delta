import numpy as np
import numpy.typing as npt
import math
from typing import Tuple, Optional, List, cast, TypeAlias
from fractions import Fraction
from math import gcd
from functools import reduce
from scipy.interpolate import splprep, splev


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


SplineTck2D: TypeAlias = tuple[
    npt.NDArray[np.float64],          # knots
    list[npt.NDArray[np.float64]],    # coeffs for x/y
    int,                              # degree
]


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
    """Очищает микро-шум вблизи 0.0 и 1.0."""
    if abs(val) < EPSILON_ZERO:
        return 0.0
    if abs(val - 1.0) < EPSILON_ZERO:
        return 1.0
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
        # Эквивалентно: перевернуть Y и использовать ту же формулу
        y_flipped = h - y
        c = y_flipped / h
        b = x - (c * 0.5)
        a = 1.0 - b - c

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


def atom_fracs_to_mole_fracs(atom_fracs: List[float], formula_sizes: List[float]) -> List[float]:
    """
    Конвертирует атомные доли в истинные молярные доли соединений.

    В диаграмме Гиббса оси — атомные доли элементов. Параметр t правила рычага
    описывает положение точки вдоль линии в пространстве атомных долей.
    Это НЕ равно молярной доле соединения, если у соединений разное число
    атомов в формульной единице.

    Например, при смешении 50 моль SmS (2 ат./ф.е.) и 50 моль Gd2S3 (5 ат./ф.е.):
    - AtomS от SmS: 100 из 350 → 28.6%   (это выдаёт наивный рычаг)
    - Молярная доля SmS: 50/100 = 50%     (это правильный ответ)

    Args:
        atom_fracs: Атомные доли вклада каждого соединения (сумма ≈ 1)
        formula_sizes: Число атомов в формульной единице для каждого соединения
                       (composition.total)

    Returns:
        Истинные молярные доли (сумма = 1). Если размеры формульных единиц
        одинаковы (например, все нормированы до суммы=1), результат совпадает
        с входными атомными долями.
    """
    moles = [f / n if n > EPSILON_ZERO else 0.0
             for f, n in zip(atom_fracs, formula_sizes)]
    total = math.fsum(moles)
    if total < EPSILON_ZERO:
        return list(atom_fracs)
    return [m / total for m in moles]


def mix_compositions_by_mol_frac(
    c1: 'Composition', mol_frac_1: float, c2: 'Composition'
) -> 'Composition':
    """
    Вычисляет состав смеси двух соединений по молярным долям.

    Правило рычага «в обратную сторону»: зная x мол.% соединения 1 и
    (100-x) мол.% соединения 2, определить состав смеси в координатах
    вершин треугольника.

    Молярные доли → атомные доли → взвешенная сумма нормированных координат.

    Args:
        c1: Состав соединения 1.
        mol_frac_1: Молярная доля соединения 1 (0..1).
        c2: Состав соединения 2.

    Returns:
        Composition с координатами, нормированными к сумме 100.

    Raises:
        ValueError: Если оба состава вырождены (total ≈ 0).
    """
    from delta.models import Composition as _Composition

    mol_frac_2 = 1.0 - mol_frac_1
    n1 = c1.total
    n2 = c2.total

    denom = mol_frac_1 * n1 + mol_frac_2 * n2
    if denom < EPSILON_ZERO:
        raise ValueError("Cannot mix: both compositions have zero total")

    atom1 = mol_frac_1 * n1 / denom
    atom2 = mol_frac_2 * n2 / denom

    a1, b1, c1n = c1.normalized
    a2, b2, c2n = c2.normalized

    ra = atom1 * a1 + atom2 * a2
    rb = atom1 * b1 + atom2 * b2
    rc = atom1 * c1n + atom2 * c2n

    return _Composition(a=ra * 100.0, b=rb * 100.0, c=rc * 100.0)


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


def fit_curve_through_points(
    start: np.ndarray,
    guide_pts: List[np.ndarray],
    end: np.ndarray,
    n_samples: int = 300,
    poly_degree: int = 3,
    curve_mode: str = "spline",
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Строит параметрическую кривую через start, guide_pts и end.
    
    Args:
        curve_mode: "spline" — B-сплайн (scipy, интерполяция, без осцилляций)
                    "polynomial" — глобальный полином (МНК-аппроксимация)
        poly_degree: степень сплайна (1–3) или полинома (2–5)
    """
    p0 = np.asarray(start, dtype=float)
    p1 = np.asarray(end, dtype=float)

    if not guide_pts:
        t_eval = np.linspace(0.0, 1.0, n_samples)
        xs = (1.0 - t_eval) * p0[0] + t_eval * p1[0]
        ys = (1.0 - t_eval) * p0[1] + t_eval * p1[1]
        return xs, ys

    if curve_mode == "polynomial":
        return _fit_polynomial(p0, guide_pts, p1, n_samples, poly_degree)
    else:
        return _fit_spline(p0, guide_pts, p1, n_samples, poly_degree)


def _fit_spline(
    p0: np.ndarray,
    guide_pts: List[np.ndarray],
    p1: np.ndarray,
    n_samples: int,
    degree: int,
) -> Tuple[np.ndarray, np.ndarray]:
    """B-сплайн интерполяция (scipy). Проходит строго через все точки."""
    guide_arr = np.array(guide_pts, dtype=float)
    all_pts = np.vstack([p0[np.newaxis], guide_arr, p1[np.newaxis]])

    x = all_pts[:, 0]
    y = all_pts[:, 1]

    # Удаляем совпадающие подряд точки
    diffs = np.diff(all_pts, axis=0)
    seg_lens = np.sqrt((diffs ** 2).sum(axis=1))
    valid_mask = np.ones(len(all_pts), dtype=bool)
    valid_mask[1:] = seg_lens > EPSILON_ZERO
    valid_mask[0] = True
    valid_mask[-1] = True

    x = x[valid_mask]
    y = y[valid_mask]

    num_points = len(x)
    if num_points < 2:
        return np.full(n_samples, p0[0]), np.full(n_samples, p0[1])
    if num_points == 2:
        t = np.linspace(0.0, 1.0, n_samples)
        return (1.0 - t) * x[0] + t * x[1], (1.0 - t) * y[0] + t * y[1]

    k = min(degree, 3, num_points - 1)

    try:
        tck_raw, _u = splprep([x, y], s=0, k=k)
        tck = cast(SplineTck2D, tck_raw)

        u_new = np.linspace(0.0, 1.0, n_samples)
        xy_new = cast(list[npt.NDArray[np.float64]], splev(u_new, tck))
        x_new, y_new = xy_new
        return x_new, y_new
    except (ValueError, np.linalg.LinAlgError):
        t = np.linspace(0.0, 1.0, n_samples)
        return (1.0 - t) * p0[0] + t * p1[0], (1.0 - t) * p0[1] + t * p1[1]


def _fit_polynomial(
    p0: np.ndarray,
    guide_pts: List[np.ndarray],
    p1: np.ndarray,
    n_samples: int,
    poly_degree: int,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Полиномиальная аппроксимация (МНК).
    P(t) = (1-t)*start + t*end + t*(1-t)*Q(t)
    Guide-точки аппроксимируются (не интерполируются).
    """
    t_eval = np.linspace(0.0, 1.0, n_samples)
    guide_arr = np.array(guide_pts, dtype=float)
    all_pts = np.vstack([p0[np.newaxis], guide_arr, p1[np.newaxis]])

    diffs = np.diff(all_pts, axis=0)
    seg_lens = np.sqrt((diffs ** 2).sum(axis=1))
    t_all = np.zeros(len(all_pts))
    t_all[1:] = np.cumsum(seg_lens)
    total = t_all[-1]

    if total < EPSILON_ZERO:
        return np.full(n_samples, p0[0]), np.full(n_samples, p0[1])

    t_all /= total
    t_g = t_all[1:-1]

    linear_g = np.outer(1.0 - t_g, p0) + np.outer(t_g, p1)
    residuals = guide_arr - linear_g

    q_degree = max(0, poly_degree - 2)
    N = len(t_g)
    A = np.zeros((N, q_degree + 1))
    for k in range(q_degree + 1):
        A[:, k] = t_g * (1.0 - t_g) * (t_g ** k)

    coefs, _, _, _ = np.linalg.lstsq(A, residuals, rcond=None)

    linear_eval = np.outer(1.0 - t_eval, p0) + np.outer(t_eval, p1)
    Q_eval = np.zeros((n_samples, 2))
    for k in range(q_degree + 1):
        Q_eval += np.outer(t_eval * (1.0 - t_eval) * (t_eval ** k), coefs[k])

    pts = linear_eval + Q_eval
    return pts[:, 0], pts[:, 1]


def molar_mass_from_vertices(
    comp: Composition,
    vertex_masses: tuple[float, float, float],
) -> float:
    """
    M = (a·M_A + b·M_B + c·M_C) · total

    Корректно различает Gd₂S₃ (total=5) и GdS₁.₅ (total=2.5):
    нормированные координаты одинаковы, но total разный.
    """
    a, b, c = comp.normalized
    M_A, M_B, M_C = vertex_masses
    return (a * M_A + b * M_B + c * M_C) * comp.total


def calculate_naveski(
    *,
    mol_fracs: List[float],
    molar_masses: List[float],
    total_mass_g: float,
) -> List[float]:
    """
    m_i = x_i · M_i / ⟨M⟩ · m_total,  где  ⟨M⟩ = Σ x_j · M_j

    Args:
        mol_fracs:    молярные доли компонентов (сумма ≈ 1)
        molar_masses: молярные массы компонентов [г/моль]
        total_mass_g: желаемая масса образца [г]

    Returns:
        Навески [г] для каждого компонента.

    Raises:
        ValueError: если средняя молярная масса ≈ 0.
    """
    contribs = [x * M for x, M in zip(mol_fracs, molar_masses)]
    avg_M = math.fsum(contribs)
    if avg_M < EPSILON_ZERO:
        raise ValueError("Average molar mass is zero — check component molar masses")
    return [c / avg_M * total_mass_g for c in contribs]


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
