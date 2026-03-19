# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('config.ini', '.')],
    hiddenimports=[
        'ionin',
        'ionin.compat',
        'ionin.compat.parser_adapter',
        'ionin.compat.storage_adapter',
        'ionin.compat.analysis_adapter',
        'ionin.acquisition.parsers.cn0359',
        'ionin.acquisition.parsers.standard',
        'ionin.storage.csv_writer',
        'ionin.storage.session_store',
        'ionin.analysis.calibration',
    ],
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
    name='alyPyAcquisition_ionin',
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
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name='alyPyAcquisition_ionin',
)
