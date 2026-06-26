"""Тесты сборки прокси-URL из секретов ProxyMania и проверки живости."""
import os
import base


def _clear(monkeypatch):
    for k in ("PROXY_URL","PROXY_HOST","PROXY_PORT","PROXY_LOGIN","PROXY_PASS"):
        monkeypatch.delenv(k, raising=False)


def test_url_from_full_proxy_url(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("PROXY_URL", "http://u:p@1.2.3.4:8000")
    assert base.BaseSource.get_proxies() == {
        "http": "http://u:p@1.2.3.4:8000", "https": "http://u:p@1.2.3.4:8000"}


def test_url_built_from_parts(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("PROXY_HOST", "1.2.3.4")
    monkeypatch.setenv("PROXY_PORT", "8000")
    monkeypatch.setenv("PROXY_LOGIN", "06ad7ff23fc272d1")
    monkeypatch.setenv("PROXY_PASS", "R4HawQ9oEduSTFrp")
    p = base.BaseSource.get_proxies()
    assert p == {
        "http": "http://06ad7ff23fc272d1:R4HawQ9oEduSTFrp@1.2.3.4:8000",
        "https": "http://06ad7ff23fc272d1:R4HawQ9oEduSTFrp@1.2.3.4:8000"}


def test_none_when_nothing_set(monkeypatch):
    _clear(monkeypatch)
    assert base.BaseSource.get_proxies() is None


def test_source_specific_overrides(monkeypatch):
    _clear(monkeypatch)
    monkeypatch.setenv("PROXY_URL", "http://u:p@1.1.1.1:1")
    monkeypatch.setenv("AVITO_PROXY_URL", "http://a:b@2.2.2.2:2")
    p = base.BaseSource.get_proxies("AVITO_PROXY_URL")
    assert "2.2.2.2" in p["http"]
