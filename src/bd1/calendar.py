# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0.
#
# SPDX-License-Identifier: EPL-2.0

from __future__ import annotations

from datetime import date
from functools import lru_cache

import holidays


@lru_cache(maxsize=4)
def _french_holidays(year: int) -> holidays.HolidayBase:
    return holidays.country_holidays("FR", years=year, language="fr")


def is_working_day(value: date) -> bool:
    return value.weekday() < 5 and value not in _french_holidays(value.year)
