#!/bin/bash
set -e

usage() {
  echo ""
  echo "Usage:"
  echo "  stress_pod.sh -t <target_url> [-t <target_url> ...] \\"
  echo "                -tr <total_requests> -c <concurrency> \\"
  echo "                [-r <runs>] [-s <sleep_seconds>] \\"
  echo "                [-p <pod_label> ...]"
  echo ""
  exit 1
}

# -----------------------------
# Defaults
# -----------------------------
TOTAL_REQUESTS=100
CONCURRENCY=5
RUNS=1
SLEEP_BETWEEN_RUNS=0

TARGETS=()
POD_LABELS=()
DATA_SET=("alpha" "beta" "gamma" "delta" "epsilon")

# -----------------------------
# Parse arguments
# -----------------------------
while [[ $# -gt 0 ]]; do
  case "$1" in
    -t) TARGETS+=("$2"); shift 2 ;;
    -tr) TOTAL_REQUESTS="$2"; shift 2 ;;
    -c) CONCURRENCY="$2"; shift 2 ;;
    -r) RUNS="$2"; shift 2 ;;
    -s) SLEEP_BETWEEN_RUNS="$2"; shift 2 ;;
    -p) POD_LABELS+=("$2"); shift 2 ;;
    -h|--help) usage ;;
    *) echo "Unknown option: $1"; usage ;;
  esac
done

[[ ${#TARGETS[@]} -eq 0 ]] && echo "ERROR: At least one -t <target_url> is required" && exit 1

# -----------------------------
# Counters (atomic)
# -----------------------------
SUCCESS_FILE=/tmp/success
FAILURE_FILE=/tmp/failure

echo 0 > "$SUCCESS_FILE"
echo 0 > "$FAILURE_FILE"

increment() {
  local file=$1
  (
    flock -x 200
    echo $(( $(cat "$file") + 1 )) > "$file"
  ) 200>"$file.lock"
}

# -----------------------------
# Certificate Configuration
# -----------------------------
CLIENT_CERT="${CLIENT_CERT_PATH:-/etc/certs/tls.crt}"
CLIENT_KEY="${CLIENT_KEY_PATH:-/etc/certs/tls.key}"
CA_BUNDLE="${CA_BUNDLE_PATH:-/etc/certs/ca.crt}"

# Check if certificates exist
CERT_ENABLED=false
if [[ -f "$CLIENT_CERT" && -f "$CLIENT_KEY" && -f "$CA_BUNDLE" ]]; then
  echo "✅ mTLS certificates found"
  echo "   Client cert: $CLIENT_CERT"
  echo "   Client key:  $CLIENT_KEY"
  echo "   CA bundle:   $CA_BUNDLE"
  CERT_ENABLED=true
else
  echo "⚠️  mTLS certificates not found - using plain HTTP"
fi

# -----------------------------
# Readiness check
# -----------------------------
for TARGET in "${TARGETS[@]}"; do
  echo "Waiting for target to be ready: $TARGET"
  
  if [[ "$CERT_ENABLED" == "true" ]]; then
    # Use mTLS
    until curl -s --cert "$CLIENT_CERT" --key "$CLIENT_KEY" --cacert "$CA_BUNDLE" "$TARGET" > /dev/null 2>&1; do 
      sleep 2
    done
  else
    # Plain HTTP
    until curl -s "$TARGET" > /dev/null 2>&1; do 
      sleep 2
    done
  fi
  
  echo "✅ Target is ready: $TARGET"
done

# -----------------------------
# Resource Monitoring
# -----------------------------
RESOURCE_LOG=/tmp/resource_usage.log
echo "timestamp,pod,cpu_millicores,memory_mib" > "$RESOURCE_LOG"

monitor_resources() {
  while true; do
    TS=$(date +%s)
    kubectl top pod --no-headers 2>/dev/null | \
      awk -v ts="$TS" '{print ts "," $1 "," $2 "," $3}' >> "$RESOURCE_LOG"
    sleep 2
  done
}

monitor_resources &
MONITOR_PID=$!

# -----------------------------
# Stress Test Info
# -----------------------------
echo ""
echo "=============================================="
echo "STRESS TEST STARTED at $(date -u)"
echo "Targets            : ${TARGETS[*]}"
echo "Requests per run   : $TOTAL_REQUESTS"
echo "Concurrency        : $CONCURRENCY"
echo "Runs               : $RUNS"
echo "Sleep between runs : ${SLEEP_BETWEEN_RUNS}s"
echo "=============================================="

START_TIME=$(date +%s)

# -----------------------------
# RUN LOOP
# -----------------------------
for RUN in $(seq 1 "$RUNS"); do
  echo ""
  echo "----------------------------------------------"
  echo "RUN $RUN of $RUNS started at $(date -u)"
  echo "----------------------------------------------"

  RUN_START=$(date +%s)

  for TARGET in "${TARGETS[@]}"; do
    echo "Sending $TOTAL_REQUESTS requests to $TARGET"
    PIDS=()

    for i in $(seq 1 "$TOTAL_REQUESTS"); do
      PAYLOAD=${DATA_SET[$((i % ${#DATA_SET[@]}))]}

      REQUEST_BODY=$(cat <<EOF
{
  "request_id": "$RUN-$i",
  "payload": "$PAYLOAD",
  "source": "stress-pod",
  "timestamp": "$(date +%s)"
}
EOF
)

      (
        if [[ "$CERT_ENABLED" == "true" ]]; then
          # Use mTLS with client certificate
          if curl -s --max-time 10 \
               --cert "$CLIENT_CERT" \
               --key "$CLIENT_KEY" \
               --cacert "$CA_BUNDLE" \
               -X GET "$TARGET" | grep -q "Streamlit"; then
            increment "$SUCCESS_FILE"
          else
            increment "$FAILURE_FILE"
          fi
        else
          # Plain HTTP (fallback)
          if curl -s --max-time 10 -X GET "$TARGET" | grep -q "Streamlit"; then
            increment "$SUCCESS_FILE"
          else
            increment "$FAILURE_FILE"
          fi
        fi
      ) &

      PIDS+=($!)

      if (( ${#PIDS[@]} >= CONCURRENCY )); then
        wait "${PIDS[0]}"
        PIDS=("${PIDS[@]:1}")
      fi
    done

    for pid in "${PIDS[@]}"; do
      wait "$pid"
    done
  done

  RUN_END=$(date +%s)
  echo ""
  echo "RUN $RUN COMPLETED"
  echo "Time taken : $((RUN_END - RUN_START))s"

  [[ "$RUN" -lt "$RUNS" && "$SLEEP_BETWEEN_RUNS" -gt 0 ]] && sleep "$SLEEP_BETWEEN_RUNS"
done

# -----------------------------
# Metrics Grace Period
# -----------------------------
echo "Waiting 30 seconds for final metrics collection..."
sleep 30

# -----------------------------
# Stop Resource Monitor
# -----------------------------
kill "$MONITOR_PID" 2>/dev/null || true

# -----------------------------
# Summary
# -----------------------------
END_TIME=$(date +%s)

echo ""
echo "=============================================="
echo "ALL RUNS COMPLETED"
echo "Success requests     : $(cat "$SUCCESS_FILE")"
echo "Failed requests      : $(cat "$FAILURE_FILE")"
echo "Total execution time : $((END_TIME - START_TIME))s"
echo "=============================================="

# -----------------------------
# Resource Peak Summary
# -----------------------------
echo ""
echo "=============================================="
echo "RESOURCE USAGE SUMMARY (PEAK)"
echo "=============================================="

if [[ $(wc -l <"$RESOURCE_LOG") -le 1 ]]; then
  echo "No resource metrics captured (metrics became available late)"
else
  awk -F',' '
  NR>1 {
    cpu[$2] = (cpu[$2] > $3 ? cpu[$2] : $3)
    mem[$2] = (mem[$2] > $4 ? mem[$2] : $4)
  }
  END {
    for (p in cpu)
      printf "Pod: %-35s CPU_peak=%s Memory_peak=%s\n", p, cpu[p], mem[p]
  }' "$RESOURCE_LOG"
fi

# -----------------------------
# Validation
# -----------------------------
if [[ ${#POD_LABELS[@]} -gt 0 ]]; then
  echo ""
  echo "Validation started"
  echo "----------------------------------------------"

  OVERALL_STATUS="PASS"
  EXPECTED_TOTAL=$((TOTAL_REQUESTS * RUNS))

  for LABEL in "${POD_LABELS[@]}"; do
    TOTAL_PODS=$(kubectl get pods -l "$LABEL" --field-selector=status.phase=Running -o name | wc -l)
    echo "Service label       : $LABEL"
    echo "Running pods        : $TOTAL_PODS"
    
    if [[ $TOTAL_PODS -eq 0 ]]; then
      echo "⚠️  No running pods found for label: $LABEL"
      OVERALL_STATUS="FAIL"
    else
      echo "✅ Pods are running for label: $LABEL"
    fi
    echo "----------------------------------------------"
  done

  echo "Overall validation status : $OVERALL_STATUS"
  [[ "$OVERALL_STATUS" == "FAIL" ]] && exit 1
fi

echo ""
echo "✅ STRESS TEST COMPLETED SUCCESSFULLY"
