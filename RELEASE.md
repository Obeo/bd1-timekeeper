<!-- Copyright (c) 2026 Obeo -->
<!-- This program and the accompanying materials are made available under the -->
<!-- terms of the Eclipse Public License 2.0 which is available at -->
<!-- https://www.eclipse.org/legal/epl-2.0/. -->
<!-- -->
<!-- SPDX-License-Identifier: EPL-2.0 -->

# Release checklist

1. Review the change log and confirm the version in `pyproject.toml`.
2. Run `ruff check .`, `ruff format --check .`, and the full unittest suite.
3. Build the source distribution and wheel and verify that `LICENSE`, `NOTICE`,
   and `THIRD_PARTY_LICENSES.md` are included. Verify that the same files are
   present in every platform bundle.
4. Inspect the resolved dependency versions and update
   `THIRD_PARTY_LICENSES.md` when the dependency set changes.
5. Create and push an annotated `vX.Y.Z` tag. GitHub Actions rejects tags that do
   not match `pyproject.toml`, then builds the Linux, Windows, and macOS artifacts.
6. Verify that GitHub Actions published the tag as the latest stable release with
   generated release notes, source archives, and all supported platform artifacts.
7. Install the previous version on each platform and confirm that BD-1 detects the
   new release and opens the correct download.
