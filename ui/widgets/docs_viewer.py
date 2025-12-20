import markdown
from pathlib import Path
from PySide6.QtWidgets import (QDialog, QVBoxLayout, QTabWidget, QTextBrowser, 
                               QPushButton, QHBoxLayout)
from PySide6.QtCore import QUrl
from PySide6.QtGui import QDesktopServices
from core.utils import resource_path


class DocsViewer(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Documentation")
        self.resize(900, 700)
        
        layout = QVBoxLayout(self)
        
        self.tabs = QTabWidget()
        layout.addWidget(self.tabs)
        
        # Словарь для маппинга "имя файла" -> "индекс вкладки"
        self._file_to_tab_index = {}
        
        # Загружаем документы
        self._add_doc_tab("Manual", "MANUAL.md")
        self._add_doc_tab("Readme", "README.md")
        
        # Кнопка закрытия
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        btn_close = QPushButton("Close")
        btn_close.clicked.connect(self.accept)
        btn_layout.addWidget(btn_close)
        
        layout.addLayout(btn_layout)

    def _add_doc_tab(self, title: str, filename: str):
        browser = QTextBrowser()
        
        # 1. ОТКЛЮЧАЕМ автоматический переход, чтобы обрабатывать вручную
        browser.setOpenLinks(False)
        # 2. Подключаем обработчик кликов
        browser.anchorClicked.connect(self._on_link_clicked)
        
        # Стили (белый фон)
        browser.setStyleSheet("""
            QTextBrowser {
                background-color: #ffffff;
                color: #333333;
                selection-background-color: #0078d7;
                selection-color: #ffffff;
            }
        """)

        try:
            full_path = Path(resource_path(filename))
            if not full_path.exists():
                full_path = Path(__file__).parent.parent.parent / filename

            if full_path.exists():
                text = full_path.read_text(encoding="utf-8")
                html = self._md_to_html(text)
                browser.setHtml(html)
                
                # Запоминаем исходный путь файла (для относительных ссылок в markdown)
                # Это нужно, чтобы Qt понимал, где искать картинки, если они будут
                browser.setSearchPaths([str(full_path.parent)])
            else:
                browser.setHtml(f"<h1 style='color:red'>File not found: {filename}</h1>")
                
        except Exception as e:
            browser.setHtml(f"<h1 style='color:red'>Error loading {filename}</h1><p>{str(e)}</p>")

        # Добавляем вкладку и запоминаем её индекс по имени файла
        idx = self.tabs.addTab(browser, title)
        self._file_to_tab_index[filename] = idx

    def _on_link_clicked(self, url: QUrl):
        """
        Перехватывает клик по ссылке.
        - Если ссылка на MD файл -> переключает вкладку.
        - Если ссылка веб -> открывает браузер.
        """
        filename = url.fileName()
        
        # 1. Проверяем, есть ли вкладка с таким файлом (например, MANUAL.md)
        if filename in self._file_to_tab_index:
            target_index = self._file_to_tab_index[filename]
            self.tabs.setCurrentIndex(target_index)
            return

        # 2. Если это не внутренний файл, открываем как обычную ссылку (в браузере ОС)
        # QDesktopServices умеет открывать http, mailto и file://
        QDesktopServices.openUrl(url)

    def _md_to_html(self, text: str) -> str:
        """Конвертация MD -> HTML с базовым CSS"""
        # Расширения: tables для таблиц, fenced_code для блоков кода ```
        html_content = markdown.markdown(text, extensions=['tables', 'fenced_code'])
        
        css = """
        <style>
            body { 
                font-family: "Segoe UI", "Verdana", sans-serif; 
                color: #24292e;           /* Темно-серый, почти черный */
                background-color: #ffffff; 
                line-height: 1.6;
                font-size: 14px;
            }
            h1 { 
                color: #0366d6;           /* Приятный синий */
                border-bottom: 1px solid #eaecef; 
                padding-bottom: 0.3em;
                margin-top: 0;
            }
            h2 { 
                color: #24292e;
                border-bottom: 1px solid #eaecef; 
                padding-bottom: 0.3em; 
                margin-top: 24px; 
            }
            h3 { color: #24292e; margin-top: 20px; }
            
            /* Стили для инлайн-кода (белые прямоугольники на скрине) */
            code { 
                background-color: #f6f8fa; /* Очень светло-серый фон */
                color: #e01b24;            /* Красный текст для контраста */
                padding: 2px 4px; 
                border-radius: 4px; 
                font-family: "Consolas", "Courier New", monospace; 
                font-size: 90%;
            }
            
            /* Стили для блоков кода */
            pre { 
                background-color: #f6f8fa; 
                padding: 16px; 
                border-radius: 6px; 
                overflow: auto; 
            }
            pre code {
                color: #24292e; /* Обычный цвет внутри блока */
                background-color: transparent;
            }
            
            /* Таблицы */
            table { border-collapse: collapse; width: 100%; margin: 15px 0; }
            th, td { border: 1px solid #dfe2e5; padding: 6px 13px; }
            th { background-color: #f6f8fa; font-weight: bold; }
            tr:nth-child(2n) { background-color: #f8f8f8; }
            
            /* Цитаты */
            blockquote { 
                border-left: 4px solid #dfe2e5; 
                padding: 0 15px; 
                color: #6a737d; 
                margin-left: 0;
            }
            a { color: #0366d6; text-decoration: none; }
            a:hover { text-decoration: underline; }
        </style>
        """
        
        return f"{css}\n{html_content}"
