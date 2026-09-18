"""Conservative local estimates, never a claim about the provider's balance."""

from decimal import Decimal

from jevdroid.errors import BudgetExceeded, ProviderError
from jevdroid.models import RunConfig


class Budget:
    def __init__(self, config: RunConfig) -> None:
        self.config = config
        self.tokens = 0
        self.reserved = 0
        self.calls = 0

    @property
    def estimated_usd(self) -> Decimal:
        return Decimal(self.tokens) * self.config.input_price_per_million / 1_000_000

    def reserve(self) -> None:
        if self.reserved:
            raise BudgetExceeded("An unresolved request reservation prevents another call.")
        reservation = self.config.max_request_tokens
        cost = Decimal(reservation) * self.config.input_price_per_million / 1_000_000
        if self.estimated_usd + cost > self.config.budget_usd:
            raise BudgetExceeded("Estimated budget reached before sending the next request.")
        self.tokens += reservation
        self.reserved = reservation
        self.calls += 1

    def settle(self, tokens: int) -> None:
        if type(tokens) is not int or tokens < 0:
            raise ProviderError("Missing or invalid token usage; reservation retained.")
        if not self.reserved:
            raise ProviderError("Cannot settle usage without an outstanding reservation.")
        self.tokens += tokens - self.reserved
        self.reserved = 0
        if tokens > self.config.max_request_tokens:
            raise BudgetExceeded("Provider usage exceeded the configured reservation; stopping.")
