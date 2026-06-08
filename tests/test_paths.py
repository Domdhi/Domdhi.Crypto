"""Tests for the data-directory contract — paths.py decides *where* the tool
reads and writes, so the ``$DOMDHI_CRYPTO_HOME``-vs-CWD rule and the fixed
filename constants get pinned here like the other core modules.
"""

from pathlib import Path

from domdhi_crypto.shared import paths


def test_data_dir_uses_env_when_set(monkeypatch, tmp_path):
    monkeypatch.setenv("DOMDHI_CRYPTO_HOME", str(tmp_path))
    assert paths.data_dir() == Path(tmp_path)


def test_data_dir_expands_user_in_env(monkeypatch):
    monkeypatch.setenv("DOMDHI_CRYPTO_HOME", "~/domdhi-data")
    assert paths.data_dir() == Path.home() / "domdhi-data"


def test_data_dir_falls_back_to_cwd_when_env_unset(monkeypatch, tmp_path):
    monkeypatch.delenv("DOMDHI_CRYPTO_HOME", raising=False)
    monkeypatch.chdir(tmp_path)
    assert paths.data_dir() == Path.cwd() == tmp_path


def test_helpers_join_dir_with_fixed_filenames(monkeypatch, tmp_path):
    monkeypatch.setenv("DOMDHI_CRYPTO_HOME", str(tmp_path))
    assert paths.config_path() == tmp_path / "config.local.json"
    assert paths.coins_path() == tmp_path / "coins.local.json"
    assert paths.db_path() == tmp_path / "crypto.db"
    assert paths.dashboard_path() == tmp_path / "dashboard.html"


def test_helpers_use_the_module_constants(monkeypatch, tmp_path):
    monkeypatch.setenv("DOMDHI_CRYPTO_HOME", str(tmp_path))
    assert paths.config_path() == tmp_path / paths.CONFIG_FILE
    assert paths.coins_path() == tmp_path / paths.COINS_FILE
    assert paths.db_path() == tmp_path / paths.DB_FILE
    assert paths.dashboard_path() == tmp_path / paths.DASHBOARD_FILE
