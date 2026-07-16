<!-- Copyright (c) 2026 Obeo -->
<!-- This program and the accompanying materials are made available under the -->
<!-- terms of the Eclipse Public License 2.0 which is available at -->
<!-- https://www.eclipse.org/legal/epl-2.0/. -->
<!-- -->
<!-- SPDX-License-Identifier: EPL-2.0 -->

# Contributing to BD-1

Contributions are welcome through pull requests on GitHub.

Before opening a pull request:

1. Keep changes focused and explain the user-visible or maintenance impact.
2. Add or update tests for behavioral changes.
3. Run `ruff check .` and `ruff format --check .`.
4. Run `python -m unittest discover -s tests -v`.
5. Keep the EPL-2.0 header and copyright notice on new source files.
6. Check third-party license obligations when adding a dependency or asset.

By submitting a contribution, you agree that it may be distributed by Obeo
under the Eclipse Public License 2.0, unless another written agreement applies.

## Development setup

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -e ".[desktop,dev,build]"
```

The project uses Python 3.13 or later, Ruff for linting and formatting, and the
standard library `unittest` test runner.
