"""Mocked tests for the Bright Data client using respx."""

import httpx
import pytest
import respx

from freshdocs.brightdata import API_BASE, BrightDataClient, BrightDataError


@pytest.fixture
def client() -> BrightDataClient:
    return BrightDataClient(api_token="test-token")


@respx.mock
def test_collect_happy_path(client):
    trigger = respx.post(f"{API_BASE}/dca/trigger").mock(
        return_value=httpx.Response(200, json={"collection_id": "j_snap1"})
    )
    dataset = respx.get(f"{API_BASE}/dca/dataset").mock(side_effect=[
        httpx.Response(200, json={"status": "building"}),
        httpx.Response(200, json=[{"url": "https://x.com/a", "title": "A", "body_text": "body"}]),
    ])

    rows = client.collect("c_test", [{"url": "https://x.com/sitemap.xml"}], max_wait_s=30)
    assert rows[0]["title"] == "A"
    assert trigger.called
    assert dataset.call_count == 2
    # trigger called with collector id + queue_next=1
    assert trigger.calls[0].request.url.params["collector"] == "c_test"
    assert trigger.calls[0].request.url.params["queue_next"] == "1"


@respx.mock
def test_collect_returns_empty_list(client):
    respx.post(f"{API_BASE}/dca/trigger").mock(
        return_value=httpx.Response(200, json={"collection_id": "j_snap1"})
    )
    respx.get(f"{API_BASE}/dca/dataset").mock(
        return_value=httpx.Response(200, json=[])
    )
    rows = client.collect("c_test", [{"url": "https://x.com/sitemap.xml"}], max_wait_s=30)
    assert rows == []


@respx.mock
def test_401_raises_clear_error(client):
    respx.post(f"{API_BASE}/dca/trigger").mock(
        return_value=httpx.Response(401, json={"error": "unauthorized"})
    )
    with pytest.raises(BrightDataError, match="401"):
        client.trigger("c_test", [{"url": "u"}])


@respx.mock
def test_missing_collection_id_raises(client):
    respx.post(f"{API_BASE}/dca/trigger").mock(
        return_value=httpx.Response(200, json={"nope": 1})
    )
    with pytest.raises(BrightDataError, match="no collection_id"):
        client.trigger("c_test", [{"url": "u"}])


@respx.mock
def test_timeout_raises(client):
    respx.post(f"{API_BASE}/dca/trigger").mock(
        return_value=httpx.Response(200, json={"collection_id": "j_snap1"})
    )
    respx.get(f"{API_BASE}/dca/dataset").mock(
        return_value=httpx.Response(200, json={"status": "building"})
    )
    with pytest.raises(BrightDataError, match="timed out"):
        client.collect("c_test", [{"url": "u"}], max_wait_s=0.1)


def test_missing_token_raises():
    import freshdocs.brightdata as bd
    old = bd.os.environ.get("BRIGHT_DATA_API_TOKEN")
    bd.os.environ.pop("BRIGHT_DATA_API_TOKEN", None)
    try:
        with pytest.raises(BrightDataError, match="not set"):
            BrightDataClient()
    finally:
        if old:
            bd.os.environ["BRIGHT_DATA_API_TOKEN"] = old
