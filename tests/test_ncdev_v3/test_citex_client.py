from unittest.mock import patch, MagicMock
import pytest
from ncdev.v3.citex_client import CitexClient


def test_health_check_success():
    client = CitexClient(project_id="test-proj")
    with patch("ncdev.v3.citex_client.httpx") as mock_httpx:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_httpx.get.return_value = mock_resp
        assert client.health_check() is True
        mock_httpx.get.assert_called_once()


def test_health_check_failure():
    client = CitexClient(project_id="test-proj")
    with patch("ncdev.v3.citex_client.httpx") as mock_httpx:
        mock_httpx.get.side_effect = ConnectionError("refused")
        assert client.health_check() is False


def test_ingest_success():
    client = CitexClient(project_id="test-proj")
    with patch("ncdev.v3.citex_client.httpx") as mock_httpx:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_httpx.post.return_value = mock_resp
        assert client.ingest("some content", category="design") is True
        call_args = mock_httpx.post.call_args
        body = call_args.kwargs["json"]
        assert body["project_id"] == "test-proj"
        assert body["metadata"]["category"] == "design"


def test_ingest_failure():
    client = CitexClient(project_id="test-proj")
    with patch("ncdev.v3.citex_client.httpx") as mock_httpx:
        mock_httpx.post.side_effect = ConnectionError("refused")
        assert client.ingest("content", category="design") is False


def test_query_returns_content():
    client = CitexClient(project_id="test-proj")
    with patch("ncdev.v3.citex_client.httpx") as mock_httpx:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {
            "results": [
                {"content": "User model has email, name fields"},
                {"content": "Project model has title, status fields"},
            ]
        }
        mock_httpx.post.return_value = mock_resp
        results = client.query("what data models exist?")
        assert len(results) == 2
        assert "User model" in results[0]


def test_query_returns_empty_on_failure():
    client = CitexClient(project_id="test-proj")
    with patch("ncdev.v3.citex_client.httpx") as mock_httpx:
        mock_httpx.post.side_effect = ConnectionError("refused")
        results = client.query("anything")
        assert results == []


def test_query_with_category_filter():
    client = CitexClient(project_id="test-proj")
    with patch("ncdev.v3.citex_client.httpx") as mock_httpx:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"results": [{"content": "color primary: #0f172a"}]}
        mock_httpx.post.return_value = mock_resp
        client.query("design tokens", category="design")
        call_args = mock_httpx.post.call_args
        body = call_args.kwargs["json"]
        assert body["filter"] == {"category": "design"}
