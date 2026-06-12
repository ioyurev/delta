# Delta Headless API

**Headless API** позволяет создавать, анализировать и экспортировать тройные диаграммы программно, без запуска графического интерфейса.

## Преимущества

- **Не требует Qt** — работает в серверных окружениях и Jupyter notebooks
- **Простой синтаксис** — 4 строки вместо 15+
- **Интерактивный режим** — координатный overlay и drag меток в окне matplotlib
- **Полная функциональность** — все расчёты доступны через API

---

## Быстрый старт

```python
from delta import Diagram

d = Diagram(components=["NaCl", "KCl", "H\u2082O"])
e = d.add_point("Eutectic", 0.33, 0.33, 0.34, color="#E74C3C")
s = d.add_point("Salt-rich", 0.6, 0.3, 0.1)
d.add_line(e, s, style="--")
d.save_image("diagram.png", dpi=300)
d.save("project.json")
```

### Интерактивный просмотр

```python
from delta import Diagram

d = Diagram.load("project.json")
d.show()  # Интерактивное окно с overlay координат и drag меток
```

---

## Установка

```bash
git clone https://github.com/your-username/delta.git
cd delta
uv pip install -e .           # headless
uv pip install -e ".[gui]"    # с GUI
```

---

## API Reference

### Создание диаграммы

```python
Diagram(components=["A", "B", "C"], inverted=False)
```

### Свойства

```python
d.components                  # ["A", "B", "C"]
d.inverted                    # False
d.grid_visible                # True/False
d.grid_step                   # 0.1
d.lock_aspect                 # True — фиксация пропорций осей
d.figure_margins              # [0.05, 0.05, 0.05, 0.05]
d.display_region_padding      # 0.05
d.component_molar_masses      # [None, None, None] или [150.36, 362.82, ...]
d.display_region_enabled      # True/False
```

Все свойства поддерживают чтение и запись.

---

### Точки (Compositions)

```python
uid = d.add_point("Eutectic", 0.33, 0.33, 0.34,
                  color="#E74C3C", size=12, marker="*")

d.update_point(uid, name="New Name", color="#00FF00")
info = d.get_point(uid)       # PointInfo(uid, name, a, b, c, ...)
points = d.list_points()
d.remove_point(uid)
```

---

### Прямые линии

```python
line_uid = d.add_line(p1, p2, color="#000000", width=1.5, style="--")

d.update_line(line_uid, color="#FF0000")
info = d.get_line(line_uid)   # LineInfo(uid, start_uid, end_uid, ...)
lines = d.list_lines()
d.remove_line(line_uid)
```

---

### Кривые линии

```python
uid = d.add_curve_line(
    p1, p2,
    guide_points=[(0.4, 0.3, 0.3), (0.3, 0.4, 0.3)],
    curve_mode="spline",      # "spline" (B-сплайн) или "polynomial" (МНК)
    degree=3,
    color="#3498DB",
    style="--",
)

d.remove_curve_line(uid)
uids = d.list_curve_lines()
```

---

### Hatch-регионы (штриховка областей)

#### Простой полигон

```python
uid = d.add_hatch_region(
    [(0.5, 0.3, 0.2), (0.2, 0.5, 0.3), (0.3, 0.2, 0.5)],
    hatch="//",
    fill_color="#FF0000",
    fill_alpha=0.1,
)
```

#### Границы вдоль существующих линий/кривых

```python
uid = d.add_hatch_region(
    segments=[
        ("line", line_uid),
        ("curve", curve_uid, True),       # reverse=True
        ("straight", (0.5, 0.3, 0.2), (0.3, 0.2, 0.5)),
    ],
    hatch="\\\\",
)
```

```python
d.remove_hatch_region(uid)
uids = d.list_hatch_regions()
```

> **Важно:** линии и кривые, используемые в hatch-регионах, не могут быть удалены.

---

### Аннотации

```python
uid = d.add_annotation(
    "$\\alpha$-phase", 0.7, 0.2, 0.1,
    bold=True, color="#E74C3C", font_size=14,
    arrow_target=(0.5, 0.3, 0.2),
    box=True,
)

d.update_annotation(uid, text="New text", font_size=16)
d.remove_annotation(uid)
uids = d.list_annotations()
```

---

### Display Region (ограничение области)

```python
d.set_display_region([
    (0.6, 0.2, 0.2),
    (0.2, 0.6, 0.2),
    (0.2, 0.2, 0.6),
])

d.display_region_enabled = True   # включить/выключить маску
d.display_region_padding = 0.0    # отступ вокруг региона
d.clear_display_region()
```

---

### Расчёты

#### Пересечение линий

```python
result = d.intersection(line1_uid, line2_uid)
if result.found:
    print(f"({result.a:.4f}, {result.b:.4f}, {result.c:.4f})")
```

#### Правило рычага

```python
result = d.lever_rule(line_uid, point_uid)
if result.valid:
    print(result.message)  # "Phase A: 60.0%, Phase B: 40.0%"
```

---

### Визуализация

#### Экспорт в файл

```python
d.save_image("diagram.png", dpi=300)
d.save_image("diagram.svg")
d.save_image("diagram.pdf")
```

#### Интерактивное окно

```python
d.show(figsize=(8, 8))                            # простой просмотр
d.show(save_on_close="project.json")               # автосохранение при закрытии
```

#### Встраивание в matplotlib Figure

```python
import matplotlib.pyplot as plt

fig, ax = plt.subplots(figsize=(8, 8))
d.draw(ax, interactive=True)    # с overlay координат и drag меток
plt.show()
d.save("project.json")          # сохраняет перемещённые метки
```

---

### Render Settings

```python
d.lock_aspect = False               # растягивание диаграммы
d.figure_margins = [0.1, 0.1, 0.1, 0.1]  # отступы [left, right, top, bottom]
d.display_region_padding = 0.0      # без отступов вокруг display region
```

---

### Сериализация

```python
d.save("project.json")
d = Diagram.load("project.json")

data = d.to_dict()
d = Diagram.from_dict(data)
```

---

## Примеры

### Фазовая диаграмма с hatch и кривыми

```python
from delta import Diagram

d = Diagram(components=["Sm", "Gd", "S"])
d.grid_visible = True

L = d.add_point("Liquid", 0.15, 0.15, 0.70, color="#3498DB")
S1 = d.add_point("SmS", 0.50, 0.00, 0.50, color="#E74C3C", marker="s")
S2 = d.add_point("GdS", 0.00, 0.50, 0.50, color="#E74C3C", marker="s")

line1 = d.add_line(L, S1, style="--")
curve1 = d.add_curve_line(L, S2,
    guide_points=[(0.10, 0.25, 0.65), (0.05, 0.35, 0.60)],
    curve_mode="spline")

d.add_hatch_region(
    segments=[
        ("line", line1),
        ("straight", (0.50, 0.00, 0.50), (0.00, 0.50, 0.50)),
        ("curve", curve1, True),
    ],
    hatch="//", hatch_color="#888888", fill_alpha=0.05,
)

d.add_annotation("Eutectic region", 0.20, 0.20, 0.60,
                 font_size=10, italic=True)

d.save_image("phase_diagram.png", dpi=300)
```

### Интерактивная работа с сохранением

```python
from delta import Diagram

d = Diagram.load("Sm-Gd-S.json")
d.lock_aspect = False
d.display_region_padding = 0.0
d.figure_margins = [0.1, 0.1, 0.1, 0.1]

d.show(figsize=(10, 8), save_on_close="Sm-Gd-S.json")
```

---

## См. также

- **[📖 Руководство пользователя GUI](MANUAL.md)**
- **[🏠 Главная страница](README.md)**
