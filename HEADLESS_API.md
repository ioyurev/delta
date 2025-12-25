# Delta Headless API

**Headless API** позволяет создавать, анализировать и экспортировать тройные диаграммы программно, без запуска графического интерфейса.

## Преимущества

- **Не требует Qt** — работает в серверных окружениях и Jupyter notebooks
- **Простой синтаксис** — 4 строки вместо 15+
- **Полная функциональность** — все расчёты доступны через API
- **Интеграция** — легко встраивается в пайплайны обработки данных

---

## Быстрый старт

```python
from delta import Diagram

# Создание диаграммы
d = Diagram(components=["NaCl", "KCl", "H₂O"])

# Добавление точек
e = d.add_point("Eutectic", 0.33, 0.33, 0.34, color="#E74C3C")
s = d.add_point("Salt-rich", 0.6, 0.3, 0.1)

# Добавление линии
d.add_line(e, s, style="--")

# Экспорт
d.save_image("diagram.png", dpi=300)
d.save("project.json")
```

---

## Установка

```bash
# Клонирование репозитория
git clone https://github.com/your-username/delta.git
cd delta

# Только headless API (без Qt)
uv pip install -e .

# С GUI (полная установка)
uv pip install -e ".[gui]"

# Или через стандартный pip
pip install -e .           # headless
pip install -e ".[gui]"    # с GUI
```

---

## API Reference

### Создание диаграммы

```python
Diagram(components=["A", "B", "C"], inverted=False)
```

| Параметр | Тип | По умолчанию | Описание |
|----------|-----|--------------|----------|
| `components` | `list[str]` | `["A", "B", "C"]` | Имена трёх компонентов |
| `inverted` | `bool` | `False` | Ориентация (вершина C внизу) |

### Свойства

```python
d.components         # ["A", "B", "C"] — имена компонентов
d.inverted           # False — ориентация треугольника
d.grid_visible       # True/False — видимость сетки
d.grid_step          # 0.1 — шаг сетки (0.01–0.5)
```

Все свойства поддерживают чтение и запись:

```python
d.components = ["Water", "Ethanol", "Salt"]
d.grid_visible = True
d.grid_step = 0.05
```

---

### Работа с точками

#### Добавление точки

```python
uid = d.add_point(
    name,           # str: отображаемое имя
    a, b, c,        # float: координаты (автоматически нормализуются)
    *,
    color="#000000",    # str: цвет в hex
    size=6.0,           # float: размер маркера
    marker="o",         # str: форма (o, s, ^, v, D, *, x, P)
    show_marker=True,   # bool: показывать маркер
    show_label=True     # bool: показывать подпись
)
```

**Возвращает:** `str` — уникальный идентификатор точки

**Пример:**

```python
# Простое добавление
p1 = d.add_point("Phase A", 0.5, 0.3, 0.2)

# С настройкой стиля
p2 = d.add_point("Eutectic", 0.33, 0.33, 0.34, 
                  color="#E74C3C", size=12, marker="*")

# Нормализация координат
# Ввод (1, 2, 3) автоматически преобразуется в (0.167, 0.333, 0.5)
p3 = d.add_point("Mix", 1, 2, 3)
```

#### Обновление точки

```python
d.update_point(
    uid,              # str: идентификатор
    *,
    name=None,        # новое имя
    a=None, b=None, c=None,  # новые координаты
    color=None, size=None, marker=None,
    show_marker=None, show_label=None
)
```

Передавайте только те параметры, которые нужно изменить:

```python
d.update_point(p1, color="#00FF00")
d.update_point(p1, name="New Name", size=8)
d.update_point(p1, a=0.4, b=0.4, c=0.2)
```

#### Получение информации

```python
info = d.get_point(uid)
# PointInfo(uid, name, a, b, c, color, size, marker, visible, label_visible)

print(info.name)   # "Phase A"
print(info.a)      # 0.5 (нормализованное значение)
```

#### Список всех точек

```python
for p in d.list_points():
    print(f"{p.name}: ({p.a:.3f}, {p.b:.3f}, {p.c:.3f})")
```

#### Удаление точки

```python
d.remove_point(uid)  # Также удаляет все связанные линии
```

---

### Работа с линиями

#### Добавление линии

```python
line_uid = d.add_line(
    start_uid,      # str: идентификатор начальной точки
    end_uid,        # str: идентификатор конечной точки
    *,
    color="#000000",    # str: цвет
    width=1.5,          # float: толщина
    style="-"           # str: стиль (-, --, :, -.)
)
```

**Пример:**

```python
line1 = d.add_line(p1, p2)
line2 = d.add_line(p1, p3, color="#3498DB", style="--", width=2.0)
```

#### Обновление линии

```python
d.update_line(line_uid, color="#FF0000", width=2.5)
d.update_line(line_uid, start_uid=new_p1, end_uid=new_p2)
```

#### Получение информации и удаление

```python
info = d.get_line(line_uid)
# LineInfo(uid, start_uid, end_uid, color, width, style)

lines = d.list_lines()
d.remove_line(line_uid)
```

---

### Расчёты

#### Пересечение линий

```python
result = d.intersection(line1_uid, line2_uid)
```

**Возвращает:** `IntersectionInfo`

```python
if result.found:
    print(f"Пересечение: ({result.a:.4f}, {result.b:.4f}, {result.c:.4f})")
    print(f"Внутри треугольника: {result.inside_triangle}")
    
    if result.inside_triangle:
        # Добавить точку пересечения на диаграмму
        d.add_point("X", result.a, result.b, result.c, 
                    color="#27AE60", marker="X")
else:
    print(result.message)  # "Lines are parallel" и т.д.
```

#### Правило рычага

```python
result = d.lever_rule(line_uid, point_uid)
```

**Возвращает:** `LeverInfo`

```python
if result.valid:
    print(f"Доля от начала: {result.fraction_start:.1%}")
    print(f"Доля от конца: {result.fraction_end:.1%}")
    print(result.message)  # "Phase A: 60.0%, Phase B: 40.0%"
else:
    print(result.message)  # "Point is outside the line segment"
```

---

### Сериализация

#### Сохранение и загрузка JSON

```python
# Сохранение
d.save("project.json")

# Загрузка
d = Diagram.load("project.json")
```

#### Работа со словарями

```python
# Для интеграции с API/базами данных
data = d.to_dict()
d = Diagram.from_dict(data)
```

---

### Экспорт изображений

```python
d.save_image(
    filepath,           # str: путь к файлу
    *,
    dpi=150,            # int: разрешение (для PNG/JPG)
    width=8.0,          # float: ширина в дюймах
    height=7.0,         # float: высота в дюймах
    transparent=False   # bool: прозрачный фон
)
```

**Поддерживаемые форматы:** PNG, SVG, PDF, JPG

```python
d.save_image("diagram.png", dpi=300)           # Высокое разрешение
d.save_image("diagram.svg")                     # Векторный формат
d.save_image("diagram.pdf")                     # Для публикаций
d.save_image("diagram.png", transparent=True)   # Прозрачный фон
```

---

### Утилиты

```python
d.clear()      # Удалить все точки и линии
print(d)       # Diagram(components=['A', 'B', 'C'], points=5, lines=3)
```

---

## Примеры

### Минимальный пример

```python
from delta import Diagram

d = Diagram()
d.add_point("Center", 0.33, 0.33, 0.34)
d.save_image("minimal.png")
```

### Фазовая диаграмма с расчётами

```python
from delta import Diagram

# Система NaCl-KCl-H₂O
diagram = Diagram(components=["NaCl", "KCl", "H₂O"])
diagram.grid_visible = True

# Фазовые точки
L = diagram.add_point("Liquid", 0.15, 0.15, 0.70, color="#3498DB")
S1 = diagram.add_point("NaCl(s)", 0.85, 0.10, 0.05, color="#E74C3C", marker="s")
S2 = diagram.add_point("KCl(s)", 0.10, 0.85, 0.05, color="#E74C3C", marker="s")
E = diagram.add_point("Eutectic", 0.28, 0.28, 0.44, color="#9B59B6", marker="*", size=12)

# Коноды
line1 = diagram.add_line(L, S1, style="--", color="#7F8C8D")
line2 = diagram.add_line(L, S2, style="--", color="#7F8C8D")
diagram.add_line(E, S1, color="#2C3E50")
diagram.add_line(E, S2, color="#2C3E50")

# Расчёт пересечения
result = diagram.intersection(line1, line2)
if result.found and result.inside_triangle:
    diagram.add_point("X", result.a, result.b, result.c, 
                       color="#27AE60", marker="X", size=10)
    print(f"Intersection: {result.a:.3f}, {result.b:.3f}, {result.c:.3f}")

# Экспорт
diagram.save_image("phase_diagram.png", dpi=300)
diagram.save_image("phase_diagram.svg")
diagram.save("phase_diagram.json")
```

### Пакетная генерация

```python
from delta import Diagram

systems = [
    {"name": "System_A", "components": ["X", "Y", "Z"], 
     "points": [("P1", 0.5, 0.3, 0.2), ("P2", 0.2, 0.6, 0.2)]},
    {"name": "System_B", "components": ["Fe", "Cr", "Ni"],
     "points": [("Austenite", 0.70, 0.18, 0.12), ("Ferrite", 0.85, 0.10, 0.05)]},
]

for sys in systems:
    d = Diagram(components=sys["components"])
    d.grid_visible = True
    
    uids = []
    for name, a, b, c in sys["points"]:
        uids.append(d.add_point(name, a, b, c))
    
    if len(uids) >= 2:
        d.add_line(uids[0], uids[1])
    
    d.save_image(f"{sys['name']}.png", dpi=200)
    d.save(f"{sys['name']}.json")
    
    print(f"Generated: {sys['name']}")
```

### Интеграция с Jupyter

```python
from delta import Diagram
from IPython.display import Image, display
import tempfile

d = Diagram(["A", "B", "C"])
d.add_point("Sample", 0.4, 0.35, 0.25, color="#E74C3C")
d.grid_visible = True

# Отображение в notebook
with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as f:
    d.save_image(f.name, dpi=150)
    display(Image(f.name))
```

---

## Обработка ошибок

```python
from delta import Diagram

d = Diagram()

# ValueError — невалидные данные
try:
    d.add_point("Invalid", 0, 0, 0)  # Сумма = 0
except ValueError as e:
    print(f"Ошибка: {e}")

# KeyError — сущность не найдена
try:
    d.get_point("nonexistent-uid")
except KeyError as e:
    print(f"Не найдено: {e}")

# ValueError — дубликат или конфликт
try:
    p = d.add_point("A", 0.5, 0.3, 0.2)
    d.add_line(p, p)  # Линия сама в себя
except ValueError as e:
    print(f"Ошибка: {e}")
```

---

## Типы данных

### PointInfo

```python
@dataclass(frozen=True)
class PointInfo:
    uid: str
    name: str
    a: float           # Нормализованные координаты
    b: float
    c: float
    color: str
    size: float
    marker: str
    visible: bool      # show_marker
    label_visible: bool  # show_label
```

### LineInfo

```python
@dataclass(frozen=True)
class LineInfo:
    uid: str
    start_uid: str
    end_uid: str
    color: str
    width: float
    style: str
```

### IntersectionInfo

```python
@dataclass(frozen=True)
class IntersectionInfo:
    found: bool
    inside_triangle: bool
    a: float | None
    b: float | None
    c: float | None
    message: str
```

### LeverInfo

```python
@dataclass(frozen=True)
class LeverInfo:
    valid: bool
    fraction_start: float
    fraction_end: float
    message: str
```

---

## См. также

- **[📖 Руководство пользователя GUI](MANUAL.md)** — работа с графическим интерфейсом
- **[🏠 Главная страница](README.md)** — обзор проекта
