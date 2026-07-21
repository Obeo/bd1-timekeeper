# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

from __future__ import annotations

import shutil
import subprocess


def is_microphone_used_by(process_names: tuple[str, ...]) -> bool:
    if not process_names or shutil.which("pactl") is None:
        return False
    try:
        result = subprocess.run(
            ["pactl", "list", "source-outputs"],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    if result.returncode != 0:
        return False

    normalized_names = tuple(name.casefold() for name in process_names if name)
    return any(
        _source_output_matches(block, normalized_names)
        for block in _source_output_blocks(result.stdout)
    )


def _source_output_blocks(value: str) -> tuple[str, ...]:
    blocks: list[str] = []
    current: list[str] = []
    for line in value.splitlines():
        if line.startswith("Source Output #") and current:
            blocks.append("\n".join(current))
            current = []
        current.append(line)
    if current:
        blocks.append("\n".join(current))
    return tuple(blocks)


def _source_output_matches(block: str, process_names: tuple[str, ...]) -> bool:
    normalized_block = block.casefold()
    return any(name in normalized_block for name in process_names)
