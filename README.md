# BD-1

<p align="center">
  <img src="icons/hd/robot-active.png" alt="BD-1 active desktop companion" width="180">
</p>

BD-1 is a local desktop companion that observes user activity and suggests a daily or
weekly time report. It is not a clock-in system: it stores factual observations and
recomputes suggestions on demand.

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
