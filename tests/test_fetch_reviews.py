"""
TDD tests for fetch_reviews.py — written before implementation.
Run: pytest tests/ -v
"""
import json
import pytest
from unittest.mock import patch, MagicMock

import fetch_reviews


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _apify_trustpilot_response():
    # Matches blackfalcondata/trustpilot-reviews-scraper compact output
    return [
        {
            "reviewId": "abc123",
            "reviewerName": "John D.",
            "publishedDate": "2026-04-25T10:00:00.000Z",
            "title": "Withdrawal refused",
            "text": "They blocked my account after I won.",
            "rating": 1,
            "reviewUrl": "https://trustpilot.com/reviews/abc123",
        }
    ]


# ---------------------------------------------------------------------------
# normalize_trustpilot_item
# ---------------------------------------------------------------------------

class TestNormalizeTrustpilotItem:
    def test_maps_all_required_fields(self):
        raw = _apify_trustpilot_response()[0]
        result = fetch_reviews.normalize_trustpilot(raw)
        assert set(result.keys()) >= {"platform", "id", "reviewer", "date", "rating", "title", "text", "url"}

    def test_platform_is_trustpilot(self):
        result = fetch_reviews.normalize_trustpilot(_apify_trustpilot_response()[0])
        assert result["platform"] == "trustpilot"

    def test_rating_is_integer(self):
        result = fetch_reviews.normalize_trustpilot(_apify_trustpilot_response()[0])
        assert isinstance(result["rating"], int)
        assert result["rating"] == 1

    def test_missing_fields_dont_raise(self):
        result = fetch_reviews.normalize_trustpilot({})
        assert result["rating"] == 0
        assert result["text"] == ""


# ---------------------------------------------------------------------------
# review_fingerprint
# ---------------------------------------------------------------------------

class TestReviewFingerprint:
    def test_same_input_produces_same_hash(self):
        a = fetch_reviews.review_fingerprint("trustpilot", "John", "Great casino!")
        b = fetch_reviews.review_fingerprint("trustpilot", "John", "Great casino!")
        assert a == b

    def test_different_platform_produces_different_hash(self):
        a = fetch_reviews.review_fingerprint("trustpilot", "John", "text")
        b = fetch_reviews.review_fingerprint("askgamblers", "John", "text")
        assert a != b

    def test_returns_string(self):
        result = fetch_reviews.review_fingerprint("trustpilot", "John", "text")
        assert isinstance(result, str)
        assert len(result) > 0


# ---------------------------------------------------------------------------
# apify_run
# ---------------------------------------------------------------------------

class TestApifyRun:
    def test_calls_correct_url(self):
        with patch("fetch_reviews.requests.post") as mock_post:
            mock_post.return_value.json.return_value = []
            mock_post.return_value.raise_for_status = MagicMock()
            fetch_reviews.apify_run("getwally.net/trustpilot-reviews-scraper", {}, "token123")
        url = mock_post.call_args[0][0]
        assert "getwally.net~trustpilot-reviews-scraper" in url

    def test_converts_slash_to_tilde_in_actor_id(self):
        with patch("fetch_reviews.requests.post") as mock_post:
            mock_post.return_value.json.return_value = []
            mock_post.return_value.raise_for_status = MagicMock()
            fetch_reviews.apify_run("apify/rag-web-browser", {}, "token")
        url = mock_post.call_args[0][0]
        assert "apify~rag-web-browser" in url

    def test_raises_on_http_error(self):
        with patch("fetch_reviews.requests.post") as mock_post:
            mock_post.return_value.raise_for_status.side_effect = Exception("403")
            with pytest.raises(Exception):
                fetch_reviews.apify_run("actor/name", {}, "token")


# ---------------------------------------------------------------------------
# get_mock_data
# ---------------------------------------------------------------------------

class TestGetMockData:
    def test_returns_list(self):
        result = fetch_reviews.get_mock_data()
        assert isinstance(result, list)
        assert len(result) > 0

    def test_each_item_has_required_keys(self):
        required = {"brand", "brand_name", "platform", "reviewer", "date", "rating", "title", "text"}
        for item in fetch_reviews.get_mock_data():
            assert required <= set(item.keys()), f"Missing keys in: {item}"

    def test_covers_all_three_brands(self):
        brands = {r["brand"] for r in fetch_reviews.get_mock_data()}
        assert "lucky_dreams" in brands
        assert "rocket_play" in brands
        assert "only_win" in brands

    def test_has_all_three_platforms(self):
        platforms = {r["platform"] for r in fetch_reviews.get_mock_data()}
        assert "trustpilot" in platforms
        assert "askgamblers" in platforms
        assert "casinoguru" in platforms


# ---------------------------------------------------------------------------
# main()
# ---------------------------------------------------------------------------

class TestMain:
    def test_mock_mode_outputs_valid_json(self, capsys, monkeypatch):
        monkeypatch.setenv("REVIEWS_MOCK", "true")
        fetch_reviews.main()
        data = json.loads(capsys.readouterr().out)
        assert isinstance(data, list)
        assert len(data) > 0

    def test_mock_mode_json_has_all_brands(self, capsys, monkeypatch):
        monkeypatch.setenv("REVIEWS_MOCK", "true")
        fetch_reviews.main()
        data = json.loads(capsys.readouterr().out)
        brands = {r["brand"] for r in data}
        assert {"lucky_dreams", "rocket_play", "only_win"} <= brands

    def test_exits_with_1_on_missing_token(self, monkeypatch):
        monkeypatch.delenv("REVIEWS_MOCK", raising=False)
        monkeypatch.delenv("APIFY_API_TOKEN", raising=False)
        with pytest.raises(SystemExit) as exc:
            fetch_reviews.main()
        assert exc.value.code == 1
