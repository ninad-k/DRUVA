from __future__ import annotations

import json
import logging
from io import StringIO

import pytest

from app.infrastructure.logging import bind_request_context, configure_logging, get_logger


@pytest.mark.unit
def test_logger_emits_bound_context() -> None:
    stream = StringIO()
    root = logging.getLogger()
    root.handlers = [logging.StreamHandler(stream)]
    configure_logging(level="INFO", env="production")
    bind_request_context(correlation_id="cid-1", user_id="u1")
    get_logger("test").info("hello")
    output = stream.getvalue().strip()
    if output:
        payload = json.loads(output)
        assert payload["correlation_id"] == "cid-1"
