# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

"""Build small ASL data store files for tests."""

from __future__ import annotations

import struct
from datetime import datetime

from bd1.asl import FIRST_RECORD_OFFSET, HEADER_SIZE, MAGIC, RECORD_FORMAT, STRING_FORMAT

RECORD_SIZE = struct.calcsize(RECORD_FORMAT)


def build_asl(entries: list[tuple[datetime, str]]) -> bytes:
    """Return an ASL file with one message record per (time, message)."""
    data = bytearray(HEADER_SIZE)
    data[: len(MAGIC)] = MAGIC

    positions = []
    for observed_at, message in entries:
        reference = _append_string(data, message)
        positions.append(len(data))
        fields = [0] * 19
        fields[1] = RECORD_SIZE - 6
        fields[4] = int(observed_at.timestamp())
        fields[18] = reference
        data += struct.pack(RECORD_FORMAT, *fields)

    for index, position in enumerate(positions[:-1]):
        struct.pack_into(">Q", data, position + 6, positions[index + 1])
    struct.pack_into(">Q", data, FIRST_RECORD_OFFSET, positions[0] if positions else 0)
    return bytes(data)


def _append_string(data: bytearray, text: str) -> int:
    raw = text.encode("utf-8")
    if len(raw) <= 7:
        return int.from_bytes(bytes([0x80 | len(raw)]) + raw.ljust(7, b"\0"), "big")
    position = len(data)
    data += struct.pack(STRING_FORMAT, 1, len(raw) + 1) + raw + b"\0"
    return position
