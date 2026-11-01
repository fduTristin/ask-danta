import asyncio
import socket

import httpx
import pytest

from app.config import Settings
from app.reader import PageReader, public_address
from app.search import SearchError


@pytest.fixture(autouse=True)
def clean_config(monkeypatch):
    for field in Settings.model_fields:
        monkeypatch.delenv(field.upper(), raising=False)


def config(**kwargs):
    return Settings(_env_file=None, model_api_key="test-key", search_provider="tavily", search_api_key="search-key", **kwargs)


SOURCE = {"id": "W1", "url": "https://example.org/page", "title": "测试网页", "is_mock": False}


def dns_records(addresses):
    async def resolve(*args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (address, 443)) for address in addresses]
    return resolve


@pytest.mark.parametrize("addresses", [["127.0.0.1"], ["10.1.1.1"], ["169.254.169.254"], ["::1"], ["8.8.8.8", "192.168.1.1"], ["::ffff:8.8.8.8"]])
def test_reader_rejects_nonpublic_and_mixed_dns(addresses, monkeypatch):
    async def run():
        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", dns_records(addresses))
        with pytest.raises(SearchError, match="不允许访问"):
            await public_address(httpx.URL(SOURCE["url"]))
    asyncio.run(run())


@pytest.mark.parametrize("url", ["http://user:pass@example.org", "http://example.org:8000", "file:///etc/passwd"])
def test_reader_rejects_url_credentials_ports_schemes(url):
    with pytest.raises(SearchError):
        asyncio.run(public_address(httpx.URL(url)))


def test_reader_pins_validated_ip_and_rechecks_redirect(monkeypatch):
    async def run():
        lookups = []
        requests = []

        async def dns(host, *args, **kwargs):
            lookups.append(host)
            return await dns_records(["127.0.0.1"] if host == "localhost" else ["8.8.8.8"] )()

        def handler(request):
            requests.append(request)
            assert request.url.host == "8.8.8.8"
            assert request.headers["host"] == "example.org"
            assert request.extensions["sni_hostname"] == "example.org"
            return httpx.Response(302, headers={"location": "http://localhost/private"})

        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", dns)
        with pytest.raises(SearchError, match="不允许访问"):
            await PageReader(config(), httpx.MockTransport(handler)).read(SOURCE)
        assert len(requests) == 1 and lookups == ["example.org", "localhost"]
    asyncio.run(run())


def test_reader_extracts_bounds_and_closes_stream(monkeypatch):
    async def run():
        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", dns_records(["8.8.8.8"]))
        closed = False

        class Body(httpx.AsyncByteStream):
            async def __aiter__(self):
                yield b"<html><script>ignore me</script><p>" + b"x" * 1_000_010

            async def aclose(self):
                nonlocal closed
                closed = True

        reader = PageReader(config(), httpx.MockTransport(lambda r: httpx.Response(200, headers={"content-type": "text/html"}, stream=Body())))
        result = await reader.read(SOURCE)
        assert result["truncated"] and len(result["text"]) == 12000
        assert "ignore me" not in result["text"] and closed
    asyncio.run(run())


def test_reader_invalid_redirect_returns_sanitized_error(monkeypatch):
    async def run():
        monkeypatch.setattr(asyncio.get_running_loop(), "getaddrinfo", dns_records(["8.8.8.8"]))
        reader = PageReader(config(), httpx.MockTransport(lambda r: httpx.Response(
            302, headers={"location": "http://example.org:invalid/private-token"})))
        with pytest.raises(SearchError) as error:
            await reader.read(SOURCE)
        assert error.value.code == "page_unreachable"
        assert "private-token" not in error.value.message
    asyncio.run(run())
