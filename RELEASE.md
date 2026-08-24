<!-- Copyright (c) 2026 Obeo -->
<!-- This program and the accompanying materials are made available under the -->
<!-- terms of the Eclipse Public License 2.0 which is available at -->
<!-- https://www.eclipse.org/legal/epl-2.0/. -->
<!-- -->
<!-- SPDX-License-Identifier: EPL-2.0 -->

# Release process

Stable releases are built and published by GitHub Actions from annotated tags named
`vX.Y.Z`. Branch builds remain prereleases and are not offered as updates by BD-1.

## 1. Prepare the release

1. Update `version` in `pyproject.toml` and complete the `Unreleased` section of
   `CHANGELOG.md`.
2. If dependencies changed, update `THIRD_PARTY_LICENSES.md`.
3. Commit the release preparation and ensure it is present on the branch to release.

Verify:

```bash
git status --short
.venv/bin/python3.13 -c 'import tomllib; print(tomllib.load(open("pyproject.toml", "rb"))["project"]["version"])'
```

The printed version must be `X.Y.Z`, with no leading `v`, and the worktree must not
contain unintended changes.

## 2. Run the checks

```bash
.venv/bin/ruff check .
.venv/bin/ruff format --check .
PYSTRAY_BACKEND=dummy .venv/bin/python3.13 -m unittest discover -s tests
.venv/bin/python3.13 -m build
```

Verify that every command succeeds and that the source archive and wheel under
`dist/` contain `LICENSE`, `NOTICE`, and `THIRD_PARTY_LICENSES.md`:

```bash
tar -tf dist/bd1-X.Y.Z.tar.gz | rg '/(LICENSE|NOTICE|THIRD_PARTY_LICENSES.md)$'
unzip -l dist/bd1-X.Y.Z-py3-none-any.whl | rg '(LICENSE|NOTICE|THIRD_PARTY_LICENSES.md)$'
```

## 3. Create the release tag

Replace `X.Y.Z` below with the exact version from `pyproject.toml`:

```bash
git tag -a vX.Y.Z -m "BD-1 X.Y.Z"
git push origin vX.Y.Z
```

Verify on GitHub Actions that the workflow starts for the tag. It deliberately fails
if the tag and package versions differ.

## 4. Verify the published release

After the workflow succeeds, open the GitHub release for `vX.Y.Z` and verify:

- it is neither a draft nor a prerelease and is marked as the latest release;
- it contains `bd1-windows-x86_64.exe`, `bd1-linux-x86_64.tar.gz`, and
  `bd1-macos-arm64.zip`;
- the Windows installer and macOS application display version `X.Y.Z`;
- the bundles contain the three license and notice files.

## 5. Smoke-test the update

From the previous stable version on each supported platform:

1. Start BD-1 and wait for the update check.
2. Verify that the tray offers `Télécharger BD-1 vX.Y.Z` and opens the correct asset.
3. Install or extract the download according to `README.md`.
4. Verify that BD-1 starts and keeps the existing settings and database.

If a release is invalid, do not reuse its tag or replace its assets. Fix the issue,
increment the patch version, and publish a new release.
