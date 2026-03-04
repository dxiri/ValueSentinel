"""Health check endpoint for monitoring."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread

from valuesentinel.database import get_db
from valuesentinel.logging_config import get_logger
from valuesentinel.models import Alert, AlertStatus, Ticker

logger = get_logger("health")


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        if self.path == "/health":
            status = self._get_health()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(json.dumps(status).encode())
        else:
            self.send_response(404)
            self.end_headers()

    def _get_health(self) -> dict:
        try:
            with get_db() as session:
                ticker_count = session.query(Ticker).count()
                active_alerts = session.query(Alert).filter(
                    Alert.status == AlertStatus.ACTIVE
                ).count()

                # Most recent refresh
                latest = (
                    session.query(Ticker.last_fundamental_refresh)
                    .filter(Ticker.last_fundamental_refresh.isnot(None))
                    .order_by(Ticker.last_fundamental_refresh.desc())
                    .first()
                )
                last_refresh = (
                    latest[0].isoformat() if latest and latest[0] else None
                )

            return {
                "status": "healthy",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "tickers": ticker_count,
                "active_alerts": active_alerts,
                "last_fundamental_refresh": last_refresh,
            }
        except Exception:
            logger.exception("Health check failed")
            return {
                "status": "unhealthy",
                "error": "internal error",
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }

    def log_message(self, format, *args):
        # Suppress default HTTP request logging
        pass


def start_health_server(port: int = 8080) -> Thread:
    """Start the health check HTTP server in a background thread."""
    server = HTTPServer(("127.0.0.1", port), HealthHandler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("Health check server started on port %d", port)
    return thread
