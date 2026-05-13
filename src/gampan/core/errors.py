"""Exception hierarchy for gampan."""


class GampanError(Exception):
    """Root of all gampan-raised errors."""


class ConfigError(GampanError):
    """Invalid or missing `.gampan/config.yml`."""


class AuthError(GampanError):
    """Authentication / credential resolution failed."""


class SchemaError(GampanError):
    """YAML or pydantic validation failure at load time."""


class StateError(GampanError):
    """`.gampan/state.json` is corrupted, unreadable, or schema-mismatched."""


class GamApiError(GampanError):
    """Google Ad Manager API returned an error."""


class GamApiRetryableError(GamApiError):
    """Transient GAM error (5xx, throttling). Safe to retry."""


class GamApiPermanentError(GamApiError):
    """Permanent GAM error (4xx validation). Do not retry."""
