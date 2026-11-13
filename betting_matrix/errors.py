"""Exceptions communes aux sources de donnees gratuites."""

from __future__ import annotations


class SourceError(Exception):
    """Erreur generique d'une source de donnees."""

    code = "source"

    def __init__(self, message: str, code: str | None = None):
        super().__init__(message)
        self.message = message
        if code:
            self.code = code

    def user_message(self) -> str:
        return self.message


class SourceNetworkError(SourceError):
    """Source injoignable (reseau, DNS, timeout)."""

    code = "network"


class SourceRateLimitError(SourceError):
    """Source temporairement limitee."""

    code = "rate_limit"
