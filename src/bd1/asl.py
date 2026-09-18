# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

"""Reader for Apple System Log (ASL) data store files.

macOS keeps the power management history in ``/private/var/log/powermanagement``
as one ``YYYY.MM.DD.asl`` file per day: a binary linked list of message records
with big-endian fields. Only the timestamp and the message text are read.
"""

from __future__ import annotations

import struct
from datetime import datetime
from pathlib import Path

MAGIC = b"ASL DB\0\0\0\0\0\0"
HEADER_SIZE = 80
FIRST_RECORD_OFFSET = 16

# Message record: type, length, next, id, time, nanoseconds, level, flags, pid,
# uid, gid, ruid, rgid, refpid, key-value count, host, sender, facility, message.
RECORD_FORMAT = ">HIQQQIHHIIIIIIIQQQQ"
NEXT_FIELD = 2
TIME_FIELD = 4
MESSAGE_FIELD = 18

# A string reference is either an inline string (high bit set, length in the
# next seven bits, bytes right after) or the offset of a string record.
INLINE_FLAG = 1 << 63
STRING_FORMAT = ">HI"


class AslError(ValueError):
    pass


def read_asl_messages(path: Path) -> list[tuple[datetime, str]]:
    """Return (time, message) for every record, in file order."""
    data = path.read_bytes()
    if not data.startswith(MAGIC):
        raise AslError(f"Not an ASL data store: {path}")

    messages = []
    offset = struct.unpack_from(">Q", data, FIRST_RECORD_OFFSET)[0]
    while offset:
        fields = struct.unpack_from(RECORD_FORMAT, data, offset)
        observed_at = datetime.fromtimestamp(fields[TIME_FIELD]).astimezone()
        messages.append((observed_at, _read_string(data, fields[MESSAGE_FIELD])))
        offset = fields[NEXT_FIELD]
    return messages


def _read_string(data: bytes, reference: int) -> str:
    if reference == 0:
        return ""
    if reference & INLINE_FLAG:
        length = (reference >> 56) & 0x7F
        return reference.to_bytes(8, "big")[1 : 1 + length].decode("utf-8", "replace")
    start = reference + struct.calcsize(STRING_FORMAT)
    length = struct.unpack_from(STRING_FORMAT, data, reference)[1]
    return data[start : start + length].split(b"\0", 1)[0].decode("utf-8", "replace")
