#!/bin/bash
set -e

# Create directory for multiprocess metrics
export prometheus_multiproc_dir=/app/data/metrics
mkdir -p $prometheus_multiproc_dir
rm -rf $prometheus_multiproc_dir/*

echo "🚀 Starting Severus AI with metrics..."

# Start Streamlit with metrics
exec streamlit run app.py \
    --server.address=0.0.0.0 \
    --server.port=8501 \
    --server.enableCORS=false \
    --server.enableXsrfProtection=false \
    --server.maxUploadSize=200

(
    