import sys
import re
from pathlib import Path

from PySide6.QtWidgets import QApplication
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtGui import (QPainter, QImage, QColor, QFont, 
                           QLinearGradient, QBrush)
from PySide6.QtCore import Qt, QRectF

def get_version(root_path: Path) -> str:
    """Парсим версию из pyproject.toml регуляркой"""
    toml_path = root_path / "pyproject.toml"
    if not toml_path.exists():
        return "v1.0"
    
    content = toml_path.read_text(encoding="utf-8")
    match = re.search(r'^version\s*=\s*"(.*?)"', content, re.MULTILINE)
    return f"v{match.group(1)}" if match else "v1.0"

def generate_splash(svg_path: Path, output_path: Path, version: str):
    # Создаем папку build, если надо
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    print(f"Generating Splash ({version}) -> {output_path}...")

    width, height = 600, 300
    img = QImage(width, height, QImage.Format.Format_ARGB32)
    img.fill(Qt.GlobalColor.transparent)
    
    painter = QPainter(img)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setRenderHint(QPainter.RenderHint.TextAntialiasing)

    # Фон
    gradient = QLinearGradient(0, 0, width, height)
    gradient.setColorAt(0.0, QColor("#2C3E50"))
    gradient.setColorAt(1.0, QColor("#4CA1AF"))
    painter.setBrush(QBrush(gradient))
    painter.setPen(Qt.PenStyle.NoPen)
    painter.drawRoundedRect(0, 0, width, height, 15, 15)

    # Иконка
    if svg_path.exists():
        renderer = QSvgRenderer(str(svg_path))
        icon_size = 200
        renderer.render(painter, QRectF(30, (height - icon_size) / 2, icon_size, icon_size))

    # Текст
    text_x = 260
    
    # Заголовки
    painter.setPen(QColor("white"))
    painter.setFont(QFont("Segoe UI", 48, QFont.Weight.Bold))
    painter.drawText(text_x, 130, "Delta")

    painter.setPen(QColor("#BDC3C7"))
    painter.setFont(QFont("Segoe UI", 14))
    painter.drawText(text_x + 5, 160, "Ternary Analysis Tool")

    # [FIX] Версия с выравниванием по правому краю
    painter.setFont(QFont("Consolas", 10))
    # Прямоугольник в правом верхнем углу с отступами
    version_rect = QRectF(width - 150, 30, 130, 30) 
    painter.drawText(version_rect, 
                     Qt.AlignmentFlag.AlignRight | Qt.AlignmentFlag.AlignTop, 
                     version)

    # Статус
    painter.setPen(QColor("white"))
    painter.setFont(QFont("Segoe UI", 10, QFont.Weight.DemiBold))
    painter.drawText(QRectF(0, 0, width - 30, height - 20), 
                     Qt.AlignmentFlag.AlignBottom | Qt.AlignmentFlag.AlignRight, 
                     "Initializing core...")

    painter.end()
    img.save(str(output_path), "PNG") # type: ignore

if __name__ == "__main__":
    app = QApplication.instance() or QApplication(sys.argv)
    root = Path(__file__).parent.parent
    svg = root / "icon.svg"
    out = root / "splash.png"  # Default path
    
    if len(sys.argv) > 1:
        out = Path(sys.argv[1])
    
    ver = get_version(root)
    generate_splash(svg, out, ver)
