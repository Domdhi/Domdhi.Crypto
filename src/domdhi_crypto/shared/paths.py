"""Where the tool reads and writes user files.

Once installed (``pip install -e .``) the package lives in site-packages, so
``__file__`` is the wrong place to keep your data. Instead, runtime files live
in the *data directory*: ``$DOMDHI_CRYPTO_HOME`` if set, otherwise the current
working directory. Run the CLI from your repo/project folder and it finds your
``config.local.json``, ``coins.local.json``, and ``crypto.db`` right where you left
them.
"""
import os
from pathlib import Path

# Names are fixed; only the directory they live in is configurable.
CONFIG_FILE = "config.local.json"
CONFIG_EXAMPLE = "config.example.json"
COINS_FILE = "coins.local.json"
COINS_EXAMPLE = "coins.example.json"
DB_FILE = "crypto.db"
DASHBOARD_FILE = "dashboard.html"
DIGEST_FILE = "digest.md"


def data_dir() -> Path:
    """Directory holding user config/data — $DOMDHI_CRYPTO_HOME or the CWD."""
    env = os.environ.get("DOMDHI_CRYPTO_HOME")
    return Path(env).expanduser() if env else Path.cwd()


def config_path() -> Path:
    return data_dir() / CONFIG_FILE


def coins_path() -> Path:
    return data_dir() / COINS_FILE


def db_path() -> Path:
    return data_dir() / DB_FILE


def dashboard_path() -> Path:
    return data_dir() / DASHBOARD_FILE


def digest_path() -> Path:
    return data_dir() / DIGEST_FILE
