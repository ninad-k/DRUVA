import pytest

from app.config import Settings

STRONG = "x" * 32


def make(**kw) -> Settings:
    return Settings(_env_file=None, **kw)


def test_development_allows_defaults():
    make()


@pytest.mark.parametrize("env", ["staging", "production"])
def test_non_dev_rejects_default_secret_and_missing_master_key(env):
    with pytest.raises(ValueError, match="JWT_SECRET"):
        make(env=env)


def test_non_dev_rejects_debug():
    with pytest.raises(ValueError, match="DEBUG"):
        make(env="production", jwt_secret=STRONG, master_key="k", debug=True)


def test_non_dev_rejects_short_secret():
    with pytest.raises(ValueError, match="JWT_SECRET"):
        make(env="production", jwt_secret="short", master_key="k")


def test_non_dev_accepts_strong_config():
    make(env="production", jwt_secret=STRONG, master_key="k")
