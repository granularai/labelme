# -*- mode: python -*-
# vim: ft=python


block_cipher = None


a = Analysis(
    ['labelus/main.py'],
    pathex=['labelus'],
    binaries=[],
    datas=[
        ('labelus/config/default_config.yaml', 'labelus/config'),
        ('labelus/icons/*', 'labelus/icons'),
    ],
    hiddenimports=[],
    hookspath=[],
    runtime_hooks=[],
    excludes=['matplotlib'],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)
exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    name='labelus',
    debug=False,
    strip=False,
    upx=True,
    runtime_tmpdir=None,
    console=False,
    icon='labelus/icons/icon.ico',
)
app = BUNDLE(
    exe,
    name='labelus.app',
    icon='labelus/icons/logo_sm.png',
    bundle_identifier=None,
    info_plist={'NSHighResolutionCapable': 'True'},
)
