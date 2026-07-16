<!-- Copyright (c) 2026 Obeo -->
<!-- This program and the accompanying materials are made available under the -->
<!-- terms of the Eclipse Public License 2.0 which is available at -->
<!-- https://www.eclipse.org/legal/epl-2.0/. -->
<!-- -->
<!-- SPDX-License-Identifier: EPL-2.0 -->

# Third-party licenses

BD-1 is distributed under the Eclipse Public License 2.0. The dependencies
listed below remain under their respective licenses and are not relicensed by
BD-1. The versions used in a particular build are determined by the resolved
Python environment and should be recorded with the release evidence.

## Runtime dependencies

| Component | License | Upstream project | License text |
| --- | --- | --- | --- |
| platformdirs | MIT | <https://github.com/tox-dev/platformdirs> | <https://github.com/tox-dev/platformdirs/blob/main/LICENSE> |
| psutil | BSD-3-Clause | <https://github.com/giampaolo/psutil> | <https://github.com/giampaolo/psutil/blob/master/LICENSE> |
| tzdata | Apache-2.0 | <https://github.com/python/tzdata> | <https://github.com/python/tzdata/blob/main/LICENSE> |

## Desktop dependencies

These packages are installed by the optional `desktop` extra and are included
in the desktop application build:

| Component | License | Upstream project | License text |
| --- | --- | --- | --- |
| Pillow | MIT-CMU | <https://github.com/python-pillow/Pillow> | <https://github.com/python-pillow/Pillow/blob/main/LICENSE> |
| pynput | LGPL-3.0 | <https://github.com/moses-palmer/pynput> | <https://github.com/moses-palmer/pynput/blob/master/COPYING> |
| pystray | LGPL-3.0 | <https://github.com/moses-palmer/pystray> | <https://github.com/moses-palmer/pystray/blob/master/COPYING> |
| six | MIT | <https://github.com/benjaminp/six> | <https://github.com/benjaminp/six/blob/main/LICENSE> |

## Build dependency

| Component | License | Upstream project | License text |
| --- | --- | --- | --- |
| PyInstaller | GPL-2.0-or-later with the PyInstaller exception | <https://github.com/pyinstaller/pyinstaller> | <https://github.com/pyinstaller/pyinstaller/blob/develop/COPYING.txt> |

The PyInstaller exception permits distributing applications built with
PyInstaller under the application's own license. PyInstaller's bootloader and
license terms remain applicable to generated executables.

## System components

Platform-provided components such as Python, tkinter, GTK, Ayatana AppIndicator,
X11 libraries, and Windows or macOS system frameworks are not Python project
dependencies and are not redistributed as part of the source repository. Their
license and notice terms are supplied by the relevant operating system or
distribution.

Before publishing a release, maintainers should inspect the resolved dependency
set, refresh this inventory when dependencies change, and verify that the
license and notice files are present in both source archives and binary release
artifacts.
