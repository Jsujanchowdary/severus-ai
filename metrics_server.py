"""
Metrics HTTP server for Prometheus scraping.

This runs a separate HTTP server on port 8000 to expose /metrics endpoint
without interfering with Streamlit's main application.
"""

import logging
import time

from prometheus_client import start_http_server

import metrics

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def start_metrics_server(port=8000):
    """
    Start Prometheus metrics HTTP server.

    Args:
        port: Port to run the metrics server on (default: 8000)
    """
    try:
        start_http_server(port)
        logger.info(f"✅ Metrics server started on port {port}")
        logger.info(f"📊 Metrics available at http://localhost:{port}/metrics")

        # Keep the server running
        while True:
            metrics.update_uptime()
            time.sleep(60)  # Update uptime every minute

    except Exception as e:
        logger.error(f"❌ Failed to start metrics server: {e}")
        raise

if __name__ == "__main__":
    start_metrics_server()
