import pytest
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch
from models.schemas import MarketAnalysis
from main import app


@pytest.mark.asyncio
async def test_health():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"status": "ok"}


@pytest.mark.asyncio
async def test_analyze_missing_url():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/analyze", json={})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_analyze_returns_market_analysis():
    mock_result = MarketAnalysis(
        company="https://example.com",
        competitors=[],
        icp_prospects=[],
        market_summary="Example competes in the productivity space targeting SMBs.",
    )
    with patch("main.run_analysis", new=AsyncMock(return_value=mock_result)):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.post("/analyze", json={"company_url": "https://example.com"})
    assert resp.status_code == 200
    data = resp.json()
    assert data["company"] == "https://example.com"
    assert "market_summary" in data
    assert isinstance(data["competitors"], list)
    assert isinstance(data["icp_prospects"], list)
