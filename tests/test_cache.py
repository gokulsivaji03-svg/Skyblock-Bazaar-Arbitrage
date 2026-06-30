import app.cache as cache


def _reset():
    cache.reset_for_tests()


def test_refresh_waits_for_inflight_fetch(monkeypatch):
    _reset()
    payload = {"products": {"WIDGET": {"quick_status": {}}}}
    started = __import__("threading").Event()
    release = __import__("threading").Event()

    def slow_fetch():
        started.set()
        release.wait(timeout=5)
        return payload

    monkeypatch.setattr(cache, "_fetch_live", slow_fetch)

    results = []

    def waiter():
        results.append(cache.refresh(force=True))

    t = __import__("threading").Thread(target=waiter)
    t.start()
    assert started.wait(timeout=2)

    assert cache.refresh(force=True) is payload
    release.set()
    t.join(timeout=5)
    assert results == [payload]
    _reset()


def test_get_data_raises_only_when_no_snapshot(monkeypatch):
    _reset()

    def fail():
        raise ValueError("network down")

    monkeypatch.setattr(cache, "_fetch_live", fail)

    try:
        cache.get_data(force=True)
        raised = False
    except RuntimeError as exc:
        raised = True
        assert "network down" in str(exc)
    assert raised
    _reset()
