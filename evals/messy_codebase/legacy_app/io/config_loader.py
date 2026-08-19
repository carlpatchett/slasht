import json
import os
from pathlib import Path


def load_config(path, overrides=None):
    """Load JSON config, applying environment overrides then explicit ones."""
    raw = Path(path).read_text()
    settings = json.loads(raw)
    for key in list(settings):
        env_name = f"LEGACY_{key.upper()}"
        if env_name in os.environ:
            settings[key] = os.environ[env_name]
    for key, value in (overrides or {}).items():
        settings[key] = value
    return settings
