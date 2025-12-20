# -*- mode: python ; coding: utf-8 -*-

from PyInstaller.utils.hooks import collect_submodules, copy_metadata

APP_NAME = 'Delta'
MAIN_SCRIPT = 'main.py'

mpl_hidden_imports = collect_submodules('matplotlib')

a = Analysis(
    [MAIN_SCRIPT],
    pathex=[],
    binaries=[],
datas=[
        # SVG нужна внутри exe для About диалога
        ('icon.svg', '.'), 
        # Файлы документации для виджета DocsViewer
        ('README.md', '.'), 
        ('MANUAL.md', '.'), 
    ] + copy_metadata('delta'), # Метаданные сработают, т.к. мы установим пакет в build.cmd
    hiddenimports=[
        'matplotlib.backends.backend_qtagg',
        'matplotlib.backends.backend_svg',
        'matplotlib.backends.backend_pdf',
    ] + mpl_hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=1, # Легкая оптимизация байткода
)

pyz = PYZ(a.pure)

splash = Splash(
    'build/splash.png',
    binaries=a.binaries,
    datas=a.datas,
    text_pos=None,
    text_size=12,
    minify_script=True,
    always_on_top=True,
)

exe = EXE(
    pyz,
    a.scripts,
    splash,
    [],
    exclude_binaries=True,
    name=APP_NAME,
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=False, 
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='build/icon.ico', 
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    splash.binaries,
    strip=False,
    upx=True,
    upx_exclude=[],
    name=APP_NAME,
)
