import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


import pytest  # noqa: E402


@pytest.fixture(autouse=True)
def _no_real_texts(monkeypatch, request):
    """Tests must never text Kabir's phone: replace the iMessage channel unless a test opts in."""
    if "real_imessage" in request.keywords:
        return
    import alerts
    monkeypatch.setattr(alerts, "_imessage", lambda *a, **k: "skipped (tests)")


def pytest_configure(config):
    config.addinivalue_line("markers", "real_imessage: run the real alerts._imessage (with subprocess faked)")
