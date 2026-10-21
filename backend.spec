"""
PyInstaller spec file for Phantom TG Harvester backend.
Run: pyinstaller backend.spec
"""
import os, sys
from PyInstaller.utils.hooks import collect_submodules, collect_data_files
block_cipher = None

hidden_imports = [
    'uvicorn',
    'fastapi',
    'starlette',
    'aiosqlite',
    'telethon',
    'pydantic',
    'multipart',
    'socks',
    'aiohttp',
    'httpx',
    'tiktok_uploader',
    'playwright',
    'Pillow',
] + collect_submodules('fastapi') \
  + collect_submodules('starlette') \
  + collect_submodules('uvicorn') \
  + collect_submodules('telethon') \
  + collect_submodules('backend')

# Collect all backend modules
a = Analysis(
    ['backend_runner.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('backend', 'backend'),
    ],
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

import platform
icon_file = 'electron/icon.ico' if platform.system() == 'Windows' else None

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name='backend',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True if platform.system() == 'Windows' else False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,          # No console window shown to user
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=icon_file,
)
