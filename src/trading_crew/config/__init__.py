"""Configuration management.

Provides a single ``Settings`` object built from environment variables and
YAML files. Import it anywhere:

    from trading_crew.config import settings
"""

from trading_crew.config.settings import Settings, get_settings

settings = get_settings()

__all__ = ["Settings", "get_settings", "settings"]
