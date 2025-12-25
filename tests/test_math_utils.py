import math
from delta import math_utils
from delta.models import Composition

# Вспомогательная функция для создания "идеальных" входных данных
def make_ratios(*args):
    total = sum(args)
    return [x / total for x in args]

class TestFindIntegerRatio:
    
    # =========================================================================
    # 1. ТЕСТЫ СТЕХИОМЕТРИИ
    # =========================================================================
    
    def test_simple_ratios(self):
        """Проверка базовых соотношений (1:1, 1:2, 2:3)"""
        assert math_utils.find_integer_ratio([0.5, 0.5]) == [1, 1]
        assert math_utils.find_integer_ratio([1/3, 2/3]) == [1, 2]
        assert math_utils.find_integer_ratio([0.4, 0.6]) == [2, 3]
        assert math_utils.find_integer_ratio([1/3, 1/3, 1/3]) == [1, 1, 1]

    def test_complex_stoichiometry(self):
        """Проверка сложных интерметаллидов"""
        # Mg17 Al12
        inputs = make_ratios(17, 12)
        assert math_utils.find_integer_ratio(inputs) == [17, 12]

    def test_large_integers_success(self):
        """
        Проверка: мы убрали лимит <= 100.
        Теперь A200 B1 должно определяться точно, а не как fallback.
        """
        inputs = make_ratios(200, 1)
        # Раньше это уходило в fallback, теперь это точный расчет
        assert math_utils.find_integer_ratio(inputs) == [200, 1]

    def test_binary_system_in_ternary(self):
        """Проверка, когда один компонент равен 0"""
        assert math_utils.find_integer_ratio([0.5, 0.5, 0.0]) == [1, 1, 0]
        inputs = make_ratios(2, 3, 0) 
        assert math_utils.find_integer_ratio(inputs) == [2, 3, 0]

    # =========================================================================
    # 2. ТЕСТЫ ТОЧНОСТИ (Precision & Tolerance)
    # =========================================================================

    def test_tolerance_pass(self):
        """Тест внутри допуска 5e-5"""
        # Идеал: 0.5. Шум: 0.5e-5
        val1 = 0.5 + 0.000005 
        val2 = 0.5 - 0.000005
        assert math_utils.find_integer_ratio([val1, val2]) == [1, 1]

    def test_tolerance_fail_fallback(self):
        """Тест выхода за пределы допуска 5e-5 -> Fallback"""
        # Шум: 6e-5 (превышает новый допуск 5e-5)
        val1 = 0.50006
        val2 = 0.49994

        result = math_utils.find_integer_ratio([val1, val2])

        # Не должно быть [1, 1]
        assert result != [1, 1]
        
        # Ступенчатый поиск находит более простое соотношение
        # Результат зависит от уровня сложности, на котором проходит валидация
        assert len(result) == 2
        assert all(isinstance(x, int) for x in result)
        assert result[0] > 0 and result[1] > 0

    # =========================================================================
    # 3. ТЕСТЫ МАТЕМАТИЧЕСКОГО ЯДРА
    # =========================================================================

    def test_bary_cart_round_trip(self):
        """
        Проверка, что аналитическая геометрия работает корректно в обе стороны.
        """
        # Тест: Центр
        comp = Composition(a=1/3, b=1/3, c=1/3)
        cart = math_utils.bary_to_cart(comp, is_inverted=False)
        back = math_utils.cart_to_bary(cart[0], cart[1], is_inverted=False)
        
        assert comp.normalized_is_close(back, atol=1e-9)

        # Тест: Вершина A (левый нижний угол)
        comp_a = Composition(a=1, b=0, c=0)
        cart_a = math_utils.bary_to_cart(comp_a, is_inverted=False)
        # (0, 0)
        assert math.isclose(cart_a[0], 0.0, abs_tol=1e-9)
        assert math.isclose(cart_a[1], 0.0, abs_tol=1e-9)

    def test_clamping(self):
        """Проверка отсечения микро-шума (отрицательных нулей)"""
        # Симулируем результат вычислений, дающий -1e-17
        neg_zero = -1e-17
        
        # Прямой вызов приватной функции (если нужно) или через cart_to_bary
        # Предположим точку чуть ниже оси X
        comp = math_utils.cart_to_bary(0.5, neg_zero, is_inverted=False)
        
        # Координата C (y/h) должна стать ровно 0.0, а не отрицательной
        assert comp.c == 0.0
        # И не должна быть None или NaN
        assert isinstance(comp.c, float)

    def test_intersection_analytical(self):
        """Проверка нового аналитического решателя пересечений"""
        # Две медианы в равностороннем треугольнике
        # A -> Mid(BC)
        p1 = Composition(a=1, b=0, c=0)
        p2 = Composition(a=0, b=1, c=1)
        # B -> Mid(AC)
        p3 = Composition(a=0, b=1, c=0)
        p4 = Composition(a=1, b=0, c=1)
        
        inter = math_utils.solve_intersection(p1, p2, p3, p4)
        
        assert inter is not None
        # Должно быть (1/3, 1/3, 1/3)
        expected = Composition(a=1/3, b=1/3, c=1/3)
        assert inter.normalized_is_close(expected, atol=1e-9)


class TestCompositionComparison:
    
    def test_close_compositions_absolute(self):
        """Проверка абсолютного допуска для близких значений"""
        c1 = Composition(a=0.5, b=0.3, c=0.2)
        c2 = Composition(a=0.50004, b=0.29998, c=0.19998)
        
        # Разница < 5e-5 по каждой координате
        assert c1.normalized_is_close(c2)
    
    def test_small_values_comparison(self):
        """
        Проверка сравнения малых значений.
        С относительным допуском этот тест бы провалился.
        """
        c1 = Composition(a=0.00001, b=0.99998, c=0.00001)
        c2 = Composition(a=0.000015, b=0.99997, c=0.000015)
        
        # Разница 5e-6 < atol 5e-5, должно быть True
        assert c1.normalized_is_close(c2)
    
    def test_not_close_compositions(self):
        """Проверка что разные составы не равны"""
        c1 = Composition(a=0.5, b=0.3, c=0.2)
        c2 = Composition(a=0.5001, b=0.2999, c=0.2)  # Разница 1e-4 > 5e-5
        
        assert not c1.normalized_is_close(c2)
    
    def test_custom_tolerance(self):
        """Проверка кастомного допуска"""
        c1 = Composition(a=0.5, b=0.3, c=0.2)
        c2 = Composition(a=0.501, b=0.299, c=0.2)  # Разница 1e-3
        
        # С дефолтным допуском — не равны
        assert not c1.normalized_is_close(c2)
        
        # С большим допуском — равны
        assert c1.normalized_is_close(c2, atol=0.01)
    
    def test_zero_sum_composition(self):
        """Проверка обработки невалидных составов"""
        c1 = Composition(a=0, b=0, c=0)
        c2 = Composition(a=1, b=1, c=1)
        
        # Не должно падать, должно вернуть False
        assert not c1.normalized_is_close(c2)


class TestFindIntegerRatioEdgeCases:
    
    def test_all_zeros(self):
        """Проверка обработки нулевых входов"""
        assert math_utils.find_integer_ratio([0, 0, 0]) == [0, 0, 0]
        assert math_utils.find_integer_ratio([0.0, 0.0]) == [0, 0]

    def test_near_zero_values(self):
        """Проверка обработки очень малых значений"""
        tiny = 1e-15
        result = math_utils.find_integer_ratio([tiny, tiny, tiny])
        # Должно вернуть нули или [1, 1, 1], но не упасть
        assert len(result) == 3
        assert all(isinstance(x, int) for x in result)

    def test_empty_input(self):
        """Проверка пустого входа"""
        assert math_utils.find_integer_ratio([]) == []

    def test_single_value(self):
        """Проверка одного значения"""
        assert math_utils.find_integer_ratio([1.0]) == [1]
        assert math_utils.find_integer_ratio([0.5]) == [1]

    def test_mixed_zero_nonzero(self):
        """Проверка смешанных значений с нулями"""
        result = math_utils.find_integer_ratio([0.5, 0.0, 0.5])
        assert result == [1, 0, 1]

    def test_very_small_fractions(self):
        """Проверка очень малых дробей"""
        # 0.001 : 0.999 ≈ 1 : 999
        result = math_utils.find_integer_ratio([0.001, 0.999])
        assert result == [1, 999]

    def test_numerical_stability(self):
        """Проверка численной стабильности"""
        # Значения которые могут вызвать проблемы при округлении
        result = math_utils.find_integer_ratio([1e-10, 1.0 - 1e-10])
        assert len(result) == 2
        assert all(isinstance(x, int) for x in result)
        # Не должно упасть с ZeroDivisionError


class TestIsPointOnLine:
    
    def test_point_exactly_on_line(self):
        """Точка точно на линии"""
        start = Composition(a=1, b=0, c=0)
        end = Composition(a=0, b=1, c=0)
        # Середина линии
        mid = Composition(a=0.5, b=0.5, c=0)
        
        assert math_utils.is_point_on_line(start, end, mid)
    
    def test_point_on_line_with_tolerance(self):
        """Точка на линии в пределах допуска"""
        start = Composition(a=1, b=0, c=0)
        end = Composition(a=0, b=1, c=0)
        # Чуть смещена от линии
        almost_mid = Composition(a=0.5, b=0.5, c=0.00005)
        
        # С дефолтным допуском 1e-4 — на линии
        assert math_utils.is_point_on_line(start, end, almost_mid)
    
    def test_point_off_line(self):
        """Точка не на линии"""
        start = Composition(a=1, b=0, c=0)
        end = Composition(a=0, b=1, c=0)
        # Явно в стороне
        off = Composition(a=0.33, b=0.33, c=0.34)
        
        assert not math_utils.is_point_on_line(start, end, off)
    
    def test_point_off_line_strict_tolerance(self):
        """Строгий допуск отсекает малые отклонения"""
        start = Composition(a=1, b=0, c=0)
        end = Composition(a=0, b=1, c=0)
        # Смещение больше строгого допуска
        almost = Composition(a=0.5, b=0.5, c=0.001)
        
        # С строгим допуском 1e-4 — не на линии
        assert not math_utils.is_point_on_line(start, end, almost, tol=1e-4)
        
        # С UI допуском 1% — на линии
        assert math_utils.is_point_on_line(start, end, almost, tol=0.01)
    
    def test_degenerate_line(self):
        """Вырожденная линия (start = end)"""
        point = Composition(a=0.5, b=0.5, c=0)
        same = Composition(a=0.5, b=0.5, c=0)
        
        # Точка совпадает с базой
        assert math_utils.is_point_on_line(point, same, point)
        
        # Другая точка — не на "линии"
        other = Composition(a=0.3, b=0.3, c=0.4)
        assert not math_utils.is_point_on_line(point, same, other)
    
    def test_short_line_same_absolute_tolerance(self):
        """Короткая линия использует тот же абсолютный допуск"""
        # Очень короткая линия
        start = Composition(a=0.500, b=0.500, c=0)
        end = Composition(a=0.501, b=0.499, c=0)
        
        # Точка рядом с линией
        near = Composition(a=0.5005, b=0.4995, c=0.00005)
        
        # Должна определяться так же, как для длинной линии
        assert math_utils.is_point_on_line(start, end, near, tol=1e-4)
    
    def test_invalid_composition(self):
        """Обработка невалидных составов"""
        start = Composition(a=1, b=0, c=0)
        end = Composition(a=0, b=1, c=0)
        invalid = Composition(a=0, b=0, c=0)  # Сумма = 0
        
        # Не должно падать
        assert not math_utils.is_point_on_line(start, end, invalid)


class TestCollinearity:
    
    def test_collinear_on_edge(self):
        """Три точки на стороне треугольника — коллинеарны"""
        p1 = Composition(a=1, b=0, c=0)      # Вершина A
        p2 = Composition(a=0.5, b=0.5, c=0)  # Середина AB
        p3 = Composition(a=0, b=1, c=0)      # Вершина B
        
        assert math_utils.are_compositions_collinear(p1, p2, p3)
    
    def test_collinear_on_median(self):
        """Три точки на медиане — коллинеарны"""
        p1 = Composition(a=1, b=0, c=0)          # Вершина A
        p2 = Composition(a=1/3, b=1/3, c=1/3)    # Центр
        p3 = Composition(a=0, b=0.5, c=0.5)      # Середина BC
        
        assert math_utils.are_compositions_collinear(p1, p2, p3)
    
    def test_not_collinear_vertices(self):
        """Три вершины — не коллинеарны"""
        p1 = Composition(a=1, b=0, c=0)
        p2 = Composition(a=0, b=1, c=0)
        p3 = Composition(a=0, b=0, c=1)
        
        assert not math_utils.are_compositions_collinear(p1, p2, p3)
    
    def test_not_collinear_general(self):
        """Общий случай — не коллинеарны"""
        p1 = Composition(a=0.5, b=0.3, c=0.2)
        p2 = Composition(a=0.2, b=0.5, c=0.3)
        p3 = Composition(a=0.3, b=0.2, c=0.5)
        
        assert not math_utils.are_compositions_collinear(p1, p2, p3)
    
    def test_nearly_collinear(self):
        """Почти коллинеарные с малым допуском"""
        p1 = Composition(a=1, b=0, c=0)
        p2 = Composition(a=0.5, b=0.5, c=0)
        p3 = Composition(a=0, b=1, c=0.0001)  # Чуть отклонена
        
        # С большим допуском — коллинеарны
        assert math_utils.are_compositions_collinear(p1, p2, p3, tol=0.01)
        
        # С малым допуском — не коллинеарны
        assert not math_utils.are_compositions_collinear(p1, p2, p3, tol=1e-6)
    
    def test_triangle_area_normal(self):
        """Площадь нормального треугольника"""
        p1 = Composition(a=1, b=0, c=0)
        p2 = Composition(a=0, b=1, c=0)
        p3 = Composition(a=0, b=0, c=1)
        
        area = math_utils.get_triangle_area(p1, p2, p3)
        # Площадь равностороннего треугольника в барицентрических
        assert area > 0.4  # Примерно 0.5
    
    def test_triangle_area_degenerate(self):
        """Площадь вырожденного треугольника"""
        p1 = Composition(a=1, b=0, c=0)
        p2 = Composition(a=0.5, b=0.5, c=0)
        p3 = Composition(a=0, b=1, c=0)
        
        area = math_utils.get_triangle_area(p1, p2, p3)
        assert area < 1e-9
    
    def test_invalid_composition(self):
        """Обработка невалидных составов"""
        p1 = Composition(a=0, b=0, c=0)  # Невалидный
        p2 = Composition(a=1, b=0, c=0)
        p3 = Composition(a=0, b=1, c=0)
        
        # Не должно падать
        assert math_utils.are_compositions_collinear(p1, p2, p3)
        assert math_utils.get_triangle_area(p1, p2, p3) == 0.0
