import sys
import struct
from pathlib import Path
from PySide6.QtWidgets import QApplication
from PySide6.QtSvg import QSvgRenderer
from PySide6.QtGui import QPainter, QImage, QColor
from PySide6.QtCore import QByteArray, QBuffer, QIODevice

def create_ico_header(num_images: int) -> bytes:
    """
    Создает заголовок ICO файла (6 байт).
    Format: Reserved (2), Type (2), Count (2)
    """
    return struct.pack('<HHH', 0, 1, num_images)

def create_ico_directory_entry(width: int, height: int, size: int, offset: int) -> bytes:
    """
    Создает запись в каталоге для одной иконки (16 байт).
    """
    # 0 означает 256 пикселей в формате ICO
    w = 0 if width == 256 else width
    h = 0 if height == 256 else height
    
    return struct.pack(
        '<BBBBHHII',
        w,      # Width
        h,      # Height
        0,      # ColorCount (0 if >= 8bpp)
        0,      # Reserved
        1,      # Planes
        32,     # BitCount (32 for RGBA)
        size,   # BytesInRes (размер PNG данных)
        offset  # ImageOffset (смещение от начала файла)
    )

def generate_ico(svg_path: Path, ico_path: Path):
    if not svg_path.exists():
        print(f"Error: {svg_path} not found!")
        sys.exit(1)

    print(f"Converting {svg_path.name} -> {ico_path.name}...")
    
    renderer = QSvgRenderer(str(svg_path))
    if not renderer.isValid():
        print(f"Error: Invalid SVG file: {svg_path}")
        sys.exit(1)

    # Размеры иконок (стандарт Windows)
    # Порядок важен: от большого к маленькому или наоборот, Windows разберется,
    # но лучше класть 256 первым.
    sizes = [(256, 256), (48, 48), (32, 32), (16, 16)]
    
    # Список кортежей: (ширина, высота, байты_png)
    images_data = []

    for w, h in sizes:
        # 1. Рисуем SVG на QImage
        img = QImage(w, h, QImage.Format.Format_ARGB32)
        img.fill(QColor(0, 0, 0, 0))
        
        painter = QPainter(img)
        renderer.render(painter)
        painter.end()

        # 2. Сохраняем в буфер как PNG
        qbyte = QByteArray()
        buffer = QBuffer(qbyte)
        buffer.open(QIODevice.OpenModeFlag.WriteOnly)
        success = img.save(buffer, "PNG") # type: ignore
        
        if not success:
            print(f"Error saving PNG for {w}x{h}")
            continue
            
        # Получаем raw bytes
        png_bytes = qbyte.data()
        images_data.append((w, h, png_bytes))

    if not images_data:
        print("Error: No images generated.")
        sys.exit(1)

    # 3. Сборка ICO файла вручную
    with open(ico_path, 'wb') as f:
        # А. Пишем заголовок
        f.write(create_ico_header(len(images_data)))
        
        # Б. Вычисляем смещения
        # Первый PNG начинается сразу после заголовка (6 байт) и каталога (16 байт * кол-во)
        offset = 6 + (16 * len(images_data))
        
        # В. Пишем каталог (Directory Entries)
        for w, h, data in images_data:
            size = len(data)
            f.write(create_ico_directory_entry(w, h, size, offset))
            offset += size
            
        # Г. Пишем сами данные (PNG) подряд
        for _, _, data in images_data:
            f.write(data)

    print("Success! Icon created without Pillow.")

if __name__ == "__main__":
    app = QApplication.instance()
    if not app:
        app = QApplication(sys.argv)
    root = Path(__file__).parent.parent
    svg = root / "icon.svg"
    ico = root / "icon.ico"  # Default path
    
    if len(sys.argv) > 1:
        ico = Path(sys.argv[1])
    
    generate_ico(svg, ico)
