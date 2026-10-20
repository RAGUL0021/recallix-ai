"""Application errors carry a safe, user-facing message. Technical detail goes to logs only."""
from __future__ import annotations

import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(f"recallix.{name}")


class AppError(Exception):
    """Raise with a message that is safe to show to end users."""

    def __init__(self, user_message: str):
        super().__init__(user_message)
        self.user_message = user_message


class ValidationFailed(AppError):
    pass


class QuotaExceeded(AppError):
    pass


class AuthFailed(AppError):
    pass


class ServiceUnavailable(AppError):
    pass
