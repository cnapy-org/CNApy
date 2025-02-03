# -*- mode: python ; coding: utf-8 -*-
from PyInstaller.utils.hooks import collect_data_files, collect_all, collect_submodules

datas, binaries, hiddenimports = collect_all('debugpy') # cf. https://github.com/pyinstaller/pyinstaller/issues/5363
hiddenimports += collect_submodules('xmlrpc')
datas += collect_data_files('efmtool_link')
datas += collect_data_files('straindesign')
datas += collect_data_files('gurobipy')
datas += collect_data_files('cnapy')


a = Analysis(
    ['cnapy.py'],
    pathex=[],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name='cnapy',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='cnapy',
)
