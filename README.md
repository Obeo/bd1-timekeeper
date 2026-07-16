<!-- Copyright (c) 2026 Obeo -->
<!-- -->
<!-- This program and the accompanying materials are made available under the -->
<!-- terms of the Eclipse Public License 2.0 which is available at -->
<!-- https://www.eclipse.org/legal/epl-2.0. -->
<!-- -->
<!-- SPDX-License-Identifier: EPL-2.0 -->

# BD-1

<p align="center">
  <img src="icons/hd/robot-active.png" alt="BD-1 active desktop companion" width="180">
</p>

BD-1 is a local desktop companion that observes user activity and suggests a daily or
weekly time report. It is not a clock-in system: it stores factual observations and
recomputes suggestions on demand.

## Installation

Installable builds are published from the latest successful build of the `master`
branch:

<https://github.com/Obeo/bd1-timekeeper/releases/tag/build/master>

Download the asset matching your operating system:

- Windows: `BD-1-setup-x86_64.exe`
- Linux: `bd1-linux-x86_64.tar.gz`
- macOS: `bd1-macos-arm64.zip`

### Windows

Run `BD-1-setup-x86_64.exe` and follow the installer. The application is installed
as `BD-1.exe` and can be launched at the end of the setup.

If autostart was enabled in a previous installation, reinstalling in a different
folder updates the existing Windows startup entry to the new executable location.

### Linux

Extract `bd1-linux-x86_64.tar.gz`, then run the `BD-1` executable from the extracted
folder:

```bash
tar -xzf bd1-linux-x86_64.tar.gz
./BD-1/BD-1
```

### macOS

Extract `bd1-macos-arm64.zip`, then open `BD-1.app`.

## Development

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -e .
bd1
```

The base install supports reports, settings, and persistence. To run the tray
application and activity detection, install the desktop extra:

```bash
python -m pip install -e ".[desktop]"
```

On Linux, `pynput` depends on `evdev`, which may compile locally. If that build
fails with `Python.h: No such file or directory`, install the Python development
headers for your distribution, then retry the desktop extra.

The report windows use `tkinter`, which is packaged separately by some Linux
distributions. On openSUSE, install it if `bd1` fails with
`No module named 'tkinter'`:

```bash
sudo zypper install python313-tk
```

Useful commands:

```bash
bd1 --report today
bd1 --report week
bd1 --mark-working
bd1 --mark-break
bd1 --diagnose-desktop
bd1 --profile-runtime
bd1 --no-activity-monitor
bd1 --enable-autostart
bd1 --disable-autostart
bd1 --autostart-status
python -m unittest discover -s tests
```

The SQLite database and `settings.json` live in the user data directory resolved by
`platformdirs`.

## License

Copyright (c) 2026 Obeo.

BD-1 is made available under the Eclipse Public License 2.0. See
[LICENSE](LICENSE) for the complete terms and [NOTICE](NOTICE) for project
copyright and redistribution information.

The application includes third-party dependencies under their own licenses. See
[THIRD_PARTY_LICENSES.md](THIRD_PARTY_LICENSES.md) for the dependency inventory.

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for development, testing, and contribution
guidelines. Security reports should follow [SECURITY.md](SECURITY.md). Product
changes are tracked in [CHANGELOG.md](CHANGELOG.md).
