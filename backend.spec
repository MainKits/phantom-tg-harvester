"""
PyInstaller spec file for Phantom TG Harvester backend.
Run: pyinstaller backend.spec
"""
import os, sys
block_cipher = None

# Collect all backend modules
a = Analysis(
    ['backend_runner.py'],
    pathex=['.'],
    binaries=[],
    datas=[
        ('backend', 'backend'),
    ],
    hiddenimports=[
        'uvicorn',
        'uvicorn.logging',
        'uvicorn.loops',
        'uvicorn.loops.auto',
        'uvicorn.protocols',
        'uvicorn.protocols.http',
        'uvicorn.protocols.http.auto',
        'uvicorn.protocols.websockets',
        'uvicorn.protocols.websockets.auto',
        'uvicorn.lifespan',
        'uvicorn.lifespan.on',
        'fastapi',
        'aiosqlite',
        'telethon',
        'pydantic',
        'multipart',
        'socks',
        'aiohttp',
        'httpx',
        'tiktok_uploader',
        'playwright',
    ],
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
