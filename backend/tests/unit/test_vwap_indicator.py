import numpy as np
import pytest

from app.core.indicators.numpy_impl import vwap


def test_cumulative_when_no_sessions():
    r = vwap([10, 12], [10, 12], [10, 12], [1, 1]).arrays["value"]
    assert r.tolist() == [10.0, 11.0]


def test_resets_on_session_change():
    r = vwap(
        [10, 12, 100, 102],
        [10, 12, 100, 102],
        [10, 12, 100, 102],
        [1, 1, 1, 1],
        session_ids=["d1", "d1", "d2", "d2"],
    ).arrays["value"]
    assert r.tolist() == [10.0, 11.0, 100.0, 101.0]


def test_zero_volume_is_nan():
    r = vwap([5], [5], [5], [0], session_ids=["d1"]).arrays["value"]
    assert np.isnan(r[0])


def test_session_length_mismatch_raises():
    with pytest.raises(ValueError):
        vwap([1, 2], [1, 2], [1, 2], [1, 1], session_ids=["d1"])
