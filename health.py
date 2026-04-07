"""
Tiny aiohttp health + metrics server. Per PRD §5.9.
Binds to 127.0.0.1:8088 by default (loopback only, not reachable from internet).
"""
from __future__ import annotations

import logging
import time
from typing import Awaitable, Callable

from aiohttp import web

log = logging.getLogger("bepors.health")

StatsFn = Callable[[], Awaitable[dict[str, int]]]


class HealthServer:
    def __init__(
        self,
        stats_fn: StatsFn,
        *,
        host: str = "127.0.0.1",
        port: int = 8088,
        metrics_enabled: bool = False,
        metrics_secret: str | None = None,
    ):
        self.stats_fn = stats_fn
        self.host = host
        self.port = port
        self.metrics_enabled = metrics_enabled
        self.metrics_secret = metrics_secret
        self._started_at = time.time()
        self._runner: web.AppRunner | None = None

    async def start(self) -> None:
        app = web.Application()
        app.router.add_get("/health", self._handle_health)
        if self.metrics_enabled:
            app.router.add_get("/admin/metrics", self._handle_metrics)
        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        site = web.TCPSite(runner, self.host, self.port)
        await site.start()
        self._runner = runner
        log.info("health server listening on %s:%d", self.host, self.port)

    async def stop(self) -> None:
        if self._runner:
            await self._runner.cleanup()
            self._runner = None

    # ---- handlers -----------------------------------------------------------

    async def _handle_health(self, request: web.Request) -> web.Response:
        stats = await self.stats_fn()
        payload = {
            "ok": True,
            "uptime_sec": int(time.time() - self._started_at),
            **stats,
        }
        return web.json_response(payload)

    async def _handle_metrics(self, request: web.Request) -> web.Response:
        secret = request.headers.get("X-Metrics-Secret") or request.query.get("secret")
        if not self.metrics_secret or secret != self.metrics_secret:
            return web.Response(status=401, text="unauthorized")
        stats = await self.stats_fn()
        lines = [
            "# HELP bepors_uptime_seconds Process uptime in seconds",
            "# TYPE bepors_uptime_seconds gauge",
            f"bepors_uptime_seconds {int(time.time() - self._started_at)}",
        ]
        for k, v in stats.items():
            key = k.replace("-", "_")
            lines.append(f"# HELP bepors_{key} Bepors {k}")
            lines.append(f"# TYPE bepors_{key} gauge")
            lines.append(f"bepors_{key} {v}")
        return web.Response(text="\n".join(lines) + "\n", content_type="text/plain")
