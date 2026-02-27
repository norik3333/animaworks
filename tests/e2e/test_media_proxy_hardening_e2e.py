# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: Apache-2.0
"""E2E tests for hardened /api/media/proxy behavior with real upstream fetch."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from core.config.models import MediaProxyConfig


TEST_IMAGE_URLS = (
    "https://httpbin.org/image/png",
    "https://images.unsplash.com/photo-1465101046530-73398c7f28ca?fm=png",
)


def _create_app(tmp_path: Path, media_proxy: MediaProxyConfig):
    animas_dir = tmp_path / "animas"
    animas_dir.mkdir(parents=True, exist_ok=True)
    shared_dir = tmp_path / "shared"
    shared_dir.mkdir(parents=True, exist_ok=True)

    with (
        patch("server.app.ProcessSupervisor") as mock_sup_cls,
        patch("server.app.load_config") as mock_cfg,
        patch("server.app.WebSocketManager") as mock_ws_cls,
        patch("server.app.load_auth") as mock_auth,
    ):
        cfg = MagicMock()
        cfg.setup_complete = True
        cfg.server = SimpleNamespace(media_proxy=media_proxy)
        mock_cfg.return_value = cfg

        auth_cfg = MagicMock()
        auth_cfg.auth_mode = "local_trust"
        mock_auth.return_value = auth_cfg

        supervisor = MagicMock()
        supervisor.get_all_status.return_value = {}
        supervisor.get_process_status.return_value = {"status": "stopped", "pid": None}
        supervisor.is_scheduler_running.return_value = False
        supervisor.scheduler = None
        mock_sup_cls.return_value = supervisor

        ws_manager = MagicMock()
        ws_manager.active_connections = []
        mock_ws_cls.return_value = ws_manager

        from server.app import create_app

        app = create_app(animas_dir, shared_dir)

    import server.app as _sa

    _auth = MagicMock()
    _auth.auth_mode = "local_trust"
    _sa.load_auth = lambda: _auth

    return app


def _skip_if_upstream_unreachable(resp) -> None:
    if resp.status_code == 502:
        detail = resp.json().get("detail", "")
        if "Failed to fetch upstream image" in detail:
            pytest.skip("Network to upstream image host is unavailable in this environment.")


async def _request_first_available_image(client: AsyncClient):
    last_resp = None
    for image_url in TEST_IMAGE_URLS:
        resp = await client.request("GET", "/api/media/proxy", params={"url": image_url})
        if resp.status_code == 200:
            return resp
        last_resp = resp
    if last_resp is not None:
        _skip_if_upstream_unreachable(last_resp)
        return last_resp
    pytest.skip("No upstream URL candidates configured.")


class TestMediaProxyHardeningE2E:
    async def test_open_mode_real_upstream_image_fetch(self, tmp_path: Path) -> None:
        app = _create_app(
            tmp_path,
            MediaProxyConfig(mode="open_with_scan", rate_limit_requests=30, rate_limit_window_s=60),
        )
        with patch("server.routes.media_proxy.load_config") as mock_load_config:
            mock_load_config.return_value = MagicMock(
                server=MagicMock(
                    media_proxy=MediaProxyConfig(
                        mode="open_with_scan",
                        rate_limit_requests=30,
                        rate_limit_window_s=60,
                    ),
                ),
            )
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                resp = await _request_first_available_image(client)

        _skip_if_upstream_unreachable(resp)
        assert resp.status_code == 200
        assert "image/png" in resp.headers.get("content-type", "")

    async def test_rate_limit_returns_429_with_retry_after_real_flow(self, tmp_path: Path) -> None:
        app = _create_app(
            tmp_path,
            MediaProxyConfig(mode="open_with_scan", rate_limit_requests=1, rate_limit_window_s=60),
        )
        with patch("server.routes.media_proxy.load_config") as mock_load_config:
            mock_load_config.return_value = MagicMock(
                server=MagicMock(
                    media_proxy=MediaProxyConfig(
                        mode="open_with_scan",
                        rate_limit_requests=1,
                        rate_limit_window_s=60,
                    ),
                ),
            )
            from server.routes import media_proxy as media_proxy_module

            media_proxy_module._PROXY_RATE_LIMIT_BUCKETS.clear()
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                first = await _request_first_available_image(client)
                _skip_if_upstream_unreachable(first)
                second = await _request_first_available_image(client)

        assert second.status_code == 429
        assert second.headers.get("retry-after") is not None
