# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

from __future__ import annotations

import socket
import unittest
from types import SimpleNamespace
from unittest.mock import Mock, patch

from bd1.network import OFFICE, REMOTE, network_status, work_location


class NetworkStatusTest(unittest.TestCase):
    def test_reports_remote_when_intranet_does_not_resolve(self) -> None:
        with patch("bd1.network.socket.getaddrinfo", side_effect=socket.gaierror):
            self.assertEqual(
                {
                    "intranet_hostname": "intranet.obeo.fr",
                    "intranet_resolved": False,
                },
                network_status(),
            )

    def test_reports_selected_network_interface(self) -> None:
        connection = Mock()
        connection.__enter__ = Mock(return_value=connection)
        connection.__exit__ = Mock(return_value=None)
        connection.getsockname.return_value = ("10.0.0.7", 12345)
        address_info = [(socket.AF_INET, socket.SOCK_STREAM, 6, "", ("10.0.0.8", 443))]

        with (
            patch("bd1.network.socket.getaddrinfo", return_value=address_info),
            patch("bd1.network.socket.socket", return_value=connection),
            patch(
                "bd1.network.psutil.net_if_addrs",
                return_value={
                    "Ethernet": [SimpleNamespace(family=socket.AF_INET, address="10.0.0.7")]
                },
            ),
        ):
            status = network_status()

        self.assertTrue(status["intranet_resolved"])
        self.assertEqual("10.0.0.7", status["local_address"])
        self.assertEqual("Ethernet", status["network_interface"])

    def test_classifies_physical_and_openvpn_interfaces(self) -> None:
        self.assertEqual(
            OFFICE,
            work_location(
                {"intranet_resolved": True, "network_interface": "Wi-Fi"},
            ),
        )
        for interface in (
            "tun0",
            "tap0",
            "utun3",
            "ovpn-dco0",
            "OpenVPN Data Channel Offload",
            "Wintun Userspace Tunnel",
            "TAP-Windows Adapter V9",
        ):
            with self.subTest(interface=interface):
                self.assertEqual(
                    REMOTE,
                    work_location(
                        {"intranet_resolved": True, "network_interface": interface},
                    ),
                )

    def test_classifies_unresolved_or_unknown_route_as_remote(self) -> None:
        self.assertEqual(REMOTE, work_location({"intranet_resolved": False}))
        self.assertEqual(REMOTE, work_location({"intranet_resolved": True}))
        self.assertEqual(
            REMOTE,
            work_location(
                {"intranet_resolved": True, "network_interface": "Ethernet 2"},
                ("Ethernet 2",),
            ),
        )


if __name__ == "__main__":
    unittest.main()
