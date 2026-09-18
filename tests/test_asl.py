# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

from __future__ import annotations

import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from asl_builder import build_asl

from bd1.asl import AslError, read_asl_messages


class AslReaderTest(unittest.TestCase):
    def test_reads_short_and_long_messages_in_order(self) -> None:
        first = datetime(2026, 9, 17, 9, 11, 42).astimezone()
        second = datetime(2026, 9, 17, 9, 16, 42).astimezone()
        path = self.directory / "2026.09.17.asl"
        path.write_bytes(build_asl([(first, "short"), (second, "Display is turned off")]))

        messages = read_asl_messages(path)

        self.assertEqual(messages, [(first, "short"), (second, "Display is turned off")])

    def test_rejects_other_files(self) -> None:
        path = self.directory / "not-asl.log"
        path.write_bytes(b"2026-09-17 09:11:42 Display is turned on\n")

        with self.assertRaises(AslError):
            read_asl_messages(path)

    def setUp(self) -> None:
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        self.directory = Path(temporary.name)


if __name__ == "__main__":
    unittest.main()
