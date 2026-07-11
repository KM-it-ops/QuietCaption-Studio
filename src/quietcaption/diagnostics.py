import logging
import re
from pathlib import Path


def redact_path(value: str) -> str:
    return "<media>" if value else value


class PrivacyFilter(logging.Filter):
    _PATH = re.compile(r"(?:[A-Za-z]:\\|/)[^\s]+")

    def __init__(self, secrets: list[str] | None = None):
        super().__init__()
        self.secrets = [secret for secret in secrets or [] if secret]

    def filter(self, record: logging.LogRecord) -> bool:
        message = record.getMessage()
        message = self._PATH.sub("<media>", message)
        for secret in self.secrets:
            message = message.replace(secret, "<redacted>")
        record.msg, record.args = message, ()
        return True

