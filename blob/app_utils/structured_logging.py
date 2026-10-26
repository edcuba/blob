# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""Structured JSON logging for Blob, backed by ``google-cloud-logging``.

Every log record is written to stdout as one JSON object via
``google.cloud.logging_v2.handlers.StructuredLogHandler``. Cloud Run and
Agent Runtime parse those lines into ``jsonPayload`` entries, so each field is
queryable in Logs Explorer and can be routed to BigQuery with a log sink.

The handler also reads the active OpenTelemetry span, so every entry gets
``logging.googleapis.com/trace`` and ``spanId``. Logs and the Cloud Trace spans
emitted by ADK are therefore correlated with no extra code.

Use :func:`log_event` to emit a machine-readable event:

.. code-block:: python

    log_event(logger, "tool.outcome", tool="recall_knowledge", status="success")

which produces (abridged)::

    {"message": "tool.outcome", "severity": "INFO", "event": "tool.outcome",
     "tool": "recall_knowledge", "status": "success",
     "logging.googleapis.com/trace": "projects/p/traces/…", …}

Configuration:

* ``BLOB_LOG_FORMAT`` — ``json`` (default) or ``text`` for human-readable
  local output, which still renders the structured fields as ``key=value``.
* ``BLOB_LOG_LEVEL`` — root log level, default ``INFO``.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from collections.abc import Mapping
from typing import Any

LOG_FORMAT_ENV = "BLOB_LOG_FORMAT"
LOG_LEVEL_ENV = "BLOB_LOG_LEVEL"

# Loggers that install their own handlers and do not propagate to root; they
# are pointed at the structured handler as well so all output is uniform JSON.
_NON_PROPAGATING_LOGGERS = ("uvicorn", "uvicorn.error", "uvicorn.access")

_HANDLER_MARKER = "_blob_structured_handler"


class _TextFormatter(logging.Formatter):
    """Human-readable formatter that keeps the structured fields visible."""

    def format(self, record: logging.LogRecord) -> str:
        base = super().format(record)
        fields = getattr(record, "json_fields", None)
        if isinstance(fields, Mapping) and fields:
            rendered = " ".join(
                f"{k}={json.dumps(v, default=str, ensure_ascii=False)}"
                for k, v in fields.items()
                if k != "event"
            )
            return f"{base} {rendered}"
        return base


def _build_handler(fmt: str) -> logging.Handler:
    if fmt == "text":
        handler: logging.Handler = logging.StreamHandler(sys.stdout)
        handler.setFormatter(
            _TextFormatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
        )
    else:
        from google.cloud.logging_v2.handlers import StructuredLogHandler

        handler = StructuredLogHandler(
            stream=sys.stdout,
            project_id=os.environ.get("GOOGLE_CLOUD_PROJECT") or None,
            labels={"service": os.environ.get("OTEL_SERVICE_NAME", "blob")},
            json_encoder_cls=_SafeJSONEncoder,
        )
    setattr(handler, _HANDLER_MARKER, True)
    return handler


class _SafeJSONEncoder(json.JSONEncoder):
    """JSON encoder that never fails on non-serializable values."""

    def default(self, o: Any) -> Any:
        if isinstance(o, set | frozenset | tuple):
            return list(o)
        return str(o)


def configure_structured_logging(*, force: bool = False) -> logging.Handler:
    """Install the structured JSON handler on the root logger (idempotent).

    Plain ``StreamHandler``s left by ``logging.basicConfig`` are replaced to
    avoid duplicate lines. Other handlers, such as pytest's capture handler,
    are left in place.

    Args:
        force: Reinstall the handler even if one is already present (used by
            tests after changing ``BLOB_LOG_FORMAT``).

    Returns:
        The active Blob log handler.
    """
    root = logging.getLogger()
    existing = [h for h in root.handlers if getattr(h, _HANDLER_MARKER, False)]
    if existing and not force:
        return existing[0]

    fmt = os.environ.get(LOG_FORMAT_ENV, "json").strip().lower() or "json"
    level_name = os.environ.get(LOG_LEVEL_ENV, "INFO").strip().upper() or "INFO"
    level = logging.getLevelName(level_name)
    if not isinstance(level, int):
        level = logging.INFO

    handler = _build_handler(fmt)

    for h in list(root.handlers):
        if getattr(h, _HANDLER_MARKER, False) or type(h) is logging.StreamHandler:
            root.removeHandler(h)
    root.addHandler(handler)
    root.setLevel(level)

    for name in _NON_PROPAGATING_LOGGERS:
        lg = logging.getLogger(name)
        lg.handlers = [handler]
        lg.propagate = False

    return handler


def log_event(
    logger: logging.Logger,
    event: str,
    *,
    level: int = logging.INFO,
    **fields: Any,
) -> None:
    """Emit a structured log event.

    ``event`` becomes both the log message and a top-level ``event`` field;
    keyword arguments become top-level JSON fields. ``None`` values are dropped
    so entries stay compact.
    """
    if not logger.isEnabledFor(level):
        return
    payload = {"event": event, **{k: v for k, v in fields.items() if v is not None}}
    logger.log(level, event, extra={"json_fields": payload})
