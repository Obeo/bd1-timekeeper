# Copyright (c) 2026 Obeo
#
# This program and the accompanying materials are made available under the
# terms of the Eclipse Public License 2.0 which is available at
# https://www.eclipse.org/legal/epl-2.0/.
#
# SPDX-License-Identifier: EPL-2.0

# Target "cli"  : bd1 and bd1-eurecia, without the desktop extra.
# Target "test" : adds the desktop and dev extras for lint and unit tests.

FROM python:3.13-slim AS cli

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

WORKDIR /src
COPY . /src

RUN pip install --no-cache-dir -e .

ENTRYPOINT ["bd1"]
CMD ["--help"]


FROM cli AS test

# pynput needs a C toolchain on Linux for its evdev dependency.
RUN apt-get update \
    && apt-get install -y --no-install-recommends gcc libc6-dev \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir -e ".[desktop,dev]"

ENV PYSTRAY_BACKEND=dummy
ENTRYPOINT []
CMD ["sh", "-c", "ruff check . && ruff format --check . && python -m unittest discover -s tests -v"]
