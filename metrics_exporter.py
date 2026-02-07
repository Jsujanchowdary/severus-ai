#!/usr/bin/env python3
"""
Metrics exporter sidecar for Severus AI.
Reads metrics from the shared multiprocess directory and exposes them.
"""

import os
from http.server import BaseHTTPRequestHandler, HTTPServer

from prometheus_client import (
    CONTENT_TYPE_LATEST,
    CollectorRegistry,
    generate_latest,
    multiprocess,
)

# Ensure we know where to read metrics from
# prometheus_client expects lowercase 'prometheus_multiproc_dir'
if "prometheus_multiproc_dir" not in os.environ:
    os.environ["prometheus_multiproc_dir"] = os.getenv("PROMETHEUS_MULTIPROC_DIR", "/app/data/metrics")

PROMETHEUS_MULTIPROC_DIR = os.environ["prometheus_multiproc_dir"]

def run_server():
    print(f"🚀 Starting metrics exporter reading from {PROMETHEUS_MULTIPROC_DIR}...")

    # Verify directory exists
    if not os.path.exists(PROMETHEUS_MULTIPROC_DIR):
        print(f"⚠️  Warning: {PROMETHEUS_MULTIPROC_DIR} does not exist yet. Waiting...")
        os.makedirs(PROMETHEUS_MULTIPROC_DIR, exist_ok=True)

    # Custom handler to gather metrics on every request
    class MetricsHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path == '/metrics':
                try:
                    registry = CollectorRegistry()
                    multiprocess.MultiProcessCollector(registry, path=PROMETHEUS_MULTIPROC_DIR)
                    data = generate_latest(registry)

                    self.send_response(200)
                    self.send_header('Content-Type', CONTENT_TYPE_LATEST)
                    self.end_headers()
                    self.wfile.write(data)
                except Exception as e:
                    self.send_response(500)
                    self.end_headers()
                    self.wfile.write(f"Error collecting metrics: {str(e)}".encode())
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, format, *args):
            pass  # Suppress logs

    # Start server
    server = HTTPServer(('0.0.0.0', 8000), MetricsHandler)
    print("✅ Metrics server started on port 8000")
    server.serve_forever()

if __name__ == "__main__":
    run_server()
