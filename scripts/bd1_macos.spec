# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files


project_root = Path(SPECPATH).parent
datas = collect_data_files("bd1") + collect_data_files("holidays")
datas += [
    (str(project_root / filename), ".")
    for filename in ("LICENSE", "NOTICE", "THIRD_PARTY_LICENSES.md")
]

analysis = Analysis(
    [str(project_root / "scripts" / "bd1_entry.py")],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=[
        "pystray._darwin",
        "pynput.keyboard._darwin",
        "pynput.mouse._darwin",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(analysis.pure)

executable = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="BD-1",
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
collection = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=True,
    upx_exclude=[],
    name="BD-1",
)
application = BUNDLE(
    collection,
    name="BD-1.app",
    icon=str(project_root / "icons" / "macos" / "BD-1.icns"),
    bundle_identifier="com.bd1.app",
    info_plist={"LSUIElement": True},
)
