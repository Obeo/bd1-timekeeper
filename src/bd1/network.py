# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

from __future__ import annotations

import ctypes
import socket
import sys
from fnmatch import fnmatchcase

import psutil

from bd1.settings import DEFAULT_VPN_INTERFACE_PATTERNS

INTRANET_HOSTNAME = "intranet.obeo.fr"
INTRANET_PORT = 443
OFFICE = "office"
REMOTE = "remote"


def network_status(hostname: str = INTRANET_HOSTNAME) -> dict[str, object]:
    status: dict[str, object] = {
        "intranet_hostname": hostname,
        "intranet_resolved": False,
    }
    try:
        addresses = socket.getaddrinfo(hostname, INTRANET_PORT, type=socket.SOCK_STREAM)
    except OSError:
        return status

    if not addresses:
        return status

    status["intranet_resolved"] = True
    for family, _, _, _, remote_address in addresses:
        try:
            with socket.socket(family, socket.SOCK_DGRAM) as connection:
                connection.connect(remote_address)
                local_address = connection.getsockname()[0]
        except OSError:
            continue

        status["local_address"] = local_address
        interface = _interface_for(local_address)
        if interface is not None:
            status["network_interface"] = interface
            description = _windows_interface_description(interface)
            if description is not None:
                status["network_interface_description"] = description
        break
    return status


def _interface_for(local_address: str) -> str | None:
    address = local_address.split("%", 1)[0]
    try:
        interfaces = psutil.net_if_addrs()
    except psutil.Error:
        return None

    for name, addresses in interfaces.items():
        if any(
            entry.family in (socket.AF_INET, socket.AF_INET6)
            and entry.address.split("%", 1)[0] == address
            for entry in addresses
        ):
            return name
    return None


def _windows_interface_description(interface: str) -> str | None:
    if sys.platform != "win32":
        return None

    from ctypes import wintypes

    class AdapterAddresses(ctypes.Structure):
        pass

    AdapterAddresses._fields_ = (
        ("alignment", ctypes.c_ulonglong),
        ("next", ctypes.POINTER(AdapterAddresses)),
        ("adapter_name", ctypes.c_char_p),
        ("first_unicast_address", ctypes.c_void_p),
        ("first_anycast_address", ctypes.c_void_p),
        ("first_multicast_address", ctypes.c_void_p),
        ("first_dns_server_address", ctypes.c_void_p),
        ("dns_suffix", ctypes.c_wchar_p),
        ("description", ctypes.c_wchar_p),
        ("friendly_name", ctypes.c_wchar_p),
    )

    try:
        get_adapters_addresses = ctypes.WinDLL("iphlpapi").GetAdaptersAddresses
    except (AttributeError, OSError):
        return None
    get_adapters_addresses.argtypes = (
        wintypes.ULONG,
        wintypes.ULONG,
        ctypes.c_void_p,
        ctypes.c_void_p,
        ctypes.POINTER(wintypes.ULONG),
    )
    get_adapters_addresses.restype = wintypes.ULONG

    size = wintypes.ULONG(15_000)
    for _ in range(2):
        buffer = ctypes.create_string_buffer(size.value)
        result = get_adapters_addresses(
            socket.AF_UNSPEC,
            0,
            None,
            buffer,
            ctypes.byref(size),
        )
        if result == 111:  # ERROR_BUFFER_OVERFLOW
            continue
        if result != 0:
            return None

        adapter = ctypes.cast(buffer, ctypes.POINTER(AdapterAddresses))
        while adapter:
            current = adapter.contents
            if current.friendly_name and current.friendly_name.casefold() == interface.casefold():
                return current.description or None
            adapter = current.next
        return None
    return None


def work_location(
    status: dict[str, object],
    vpn_interface_patterns: tuple[str, ...] = DEFAULT_VPN_INTERFACE_PATTERNS,
) -> str:
    if not status.get("intranet_resolved"):
        return REMOTE

    interface = status.get("network_interface")
    if not isinstance(interface, str) or not interface:
        return REMOTE

    identifiers = (interface, status.get("network_interface_description"))
    # ponytail: adapter identifiers are heuristic; use native tunnel types if they fall short.
    for identifier in identifiers:
        if isinstance(identifier, str) and any(
            fnmatchcase(identifier.casefold(), pattern.casefold())
            for pattern in vpn_interface_patterns
        ):
            return REMOTE
    return OFFICE
