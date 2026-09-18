"""Public, credential-free errors."""


class JevDroidError(Exception):
    """Base class for expected operational failures."""


class DeviceError(JevDroidError):
    """Device unavailable, unstable, or unable to execute an action."""


class EmptyScreen(DeviceError):
    """No accessible elements in the active window."""


class ProviderError(JevDroidError):
    """Inference failed; response bodies and request headers are never included."""

    def __init__(self, message: str, *, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class BudgetExceeded(JevDroidError):
    """A request cannot fit inside the remaining estimated budget."""


class InvalidDecision(JevDroidError):
    """The provider selected an action outside the supplied choices."""
