"""Configure structlog with rich human output and optional JSON mode."""

from __future__ import annotations

import logging

import structlog


def configure(verbosity: int, json_output: bool = False) -> None:
    level_map = {0: logging.WARNING, 1: logging.INFO, 2: logging.DEBUG}
    level = level_map.get(min(verbosity, 2), logging.DEBUG)
    logging.basicConfig(level=level, format="%(message)s")
    structlog.configure(
        processors=(
            [structlog.processors.JSONRenderer()]
            if json_output
            else [structlog.dev.ConsoleRenderer(colors=True)]
        ),
        wrapper_class=structlog.make_filtering_bound_logger(level),
    )
