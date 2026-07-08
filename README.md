# BD-1

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

Useful commands:

```bash
bd1 --report today
bd1 --report week
bd1 --mark-working
bd1 --mark-break
python -m unittest discover -s tests
```

The SQLite database and `settings.json` live in the user data directory resolved by
`platformdirs`.
