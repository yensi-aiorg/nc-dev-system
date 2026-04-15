from unittest.mock import Mock, patch

import httpx

from ncdev.v3.citex_client import CitexClient


def test_health_check_returns_true_for_success() -> None:
    with patch("ncdev.v3.citex_client.httpx.get", return_value=Mock(status_code=200)) as mock_get:
        client = CitexClient(project_id="demo")
        assert client.health_check() is True
    mock_get.assert_called_once()


def test_health_check_returns_false_on_error() -> None:
    with patch("ncdev.v3.citex_client.httpx.get", side_effect=httpx.ConnectError("refused")):
        client = CitexClient(project_id="demo")
        assert client.health_check() is False


def test_ingest_posts_content_with_category() -> None:
    response = Mock(status_code=201)
    with patch("ncdev.v3.citex_client.httpx.post", return_value=response) as mock_post:
        client = CitexClient(project_id="demo")
        assert client.ingest("body", "code", {"source": "x"}) is True
    payload = mock_post.call_args.kwargs["json"]
    assert payload["projectId"] == "demo"
    assert payload["content"] == "body"
    assert payload["category"] == "code"
    assert payload["metadata"]["ncdev_category"] == "code"
    assert payload["metadata"]["source"] == "x"


def test_ingest_returns_false_on_error() -> None:
    with patch("ncdev.v3.citex_client.httpx.post", side_effect=httpx.ConnectError("refused")):
        client = CitexClient(project_id="demo")
        assert client.ingest("content", "code") is False


def test_query_returns_content_strings() -> None:
    response = Mock(status_code=200)
    response.json.return_value = {
        "items": [
            {"content": "User model has email, name fields"},
            {"content": "Project model has title, status fields"},
        ]
    }
    response.raise_for_status = Mock()
    with patch("ncdev.v3.citex_client.httpx.post", return_value=response):
        client = CitexClient(project_id="demo")
        results = client.query("what data models exist?")
        assert len(results) == 2
        assert "User model" in results[0]


def test_query_returns_empty_on_error() -> None:
    with patch("ncdev.v3.citex_client.httpx.post", side_effect=httpx.ConnectError("nope")):
        client = CitexClient(project_id="demo")
        assert client.query("anything") == []


def test_query_sends_top_k_in_payload() -> None:
    response = Mock(status_code=200)
    response.json.return_value = {"items": [{"content": "color primary: #0f172a"}]}
    response.raise_for_status = Mock()
    with patch("ncdev.v3.citex_client.httpx.post", return_value=response) as mock_post:
        client = CitexClient(project_id="demo")
        client.query("design tokens", limit=3)
    payload = mock_post.call_args.kwargs["json"]
    assert payload["limit"] == 3
    assert payload["projectId"] == "demo"
