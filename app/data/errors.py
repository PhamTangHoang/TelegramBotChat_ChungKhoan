class DataError(Exception):
    """Base class for recoverable or reportable data failures."""


class ProviderSchemaError(DataError):
    """A provider response cannot be parsed against the expected shape."""


class ProviderSemanticError(DataError):
    """A provider response's meaning is unknown or unsafe for analysis."""


class InvalidMarketDataError(DataError):
    """A parsed market row violates market-data invariants."""


class NoMarketDataError(DataError):
    """The provider has no usable history for the requested symbol."""


class FundamentalDataError(DataError):
    """A fundamental provider response is unavailable or cannot be normalized."""
