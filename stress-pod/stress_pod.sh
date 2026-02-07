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
# AI ANALYSIS CONFIGURATION
# -----------------------------
OLLAMA_API="${OLLAMA_API:-http://host.docker.internal:11434}"
OLLAMA_MODEL="${OLLAMA_MODEL:-deepseek-v3.1:671b-cloud}"
K_CMD="kubectl"

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

# -----------------------------
# METRICS CALCULATION
# -----------------------------
calculate_stats() {
  # Collect metrics for analysis
  SUCCESS_COUNT=$(cat "$SUCCESS_FILE" 2>/dev/null || echo 0)
  FAILURE_COUNT=$(cat "$FAILURE_FILE" 2>/dev/null || echo 0)
  TOTAL_COUNT=$((SUCCESS_COUNT + FAILURE_COUNT))
  SUCCESS_RATE=0
  [[ $TOTAL_COUNT -gt 0 ]] && SUCCESS_RATE=$((SUCCESS_COUNT * 100 / TOTAL_COUNT))
  
  DURATION=$((END_TIME - START_TIME))
  THROUGHPUT=0
  [[ $DURATION -gt 0 ]] && THROUGHPUT=$(awk -v t="$TOTAL_COUNT" -v d="$DURATION" 'BEGIN {printf "%.1f", t / d}')
  
  # Get pod count and resource metrics (Filtered by labels)
  POD_COUNT=0
  TOTAL_PEAK_CPU=0
  TOTAL_PEAK_MEM=0
  
  local POD_NAMES=""
  if [[ ${#POD_LABELS[@]} -gt 0 ]]; then
    for LABEL in "${POD_LABELS[@]}"; do
      local NAMES=$($K_CMD get pods -l "$LABEL" --field-selector=status.phase=Running -o name 2>/dev/null | sed 's/pod\///')
      if [[ -n "$NAMES" ]]; then
        POD_NAMES="$POD_NAMES $NAMES"
        POD_COUNT=$((POD_COUNT + $(echo "$NAMES" | wc -w | xargs)))
      fi
    done
  else
    local NAMES=$($K_CMD get pods --field-selector=status.phase=Running -o name 2>/dev/null | sed 's/pod\///')
    POD_NAMES="$NAMES"
    POD_COUNT=$(echo "$NAMES" | wc -w | xargs)
  fi
  
  # Extract peak metrics from resource log for SPECIFIC pods
  if [[ -f "$RESOURCE_LOG" && $(wc -l <"$RESOURCE_LOG") -gt 1 ]]; then
    # Create a regex of pod names for awk
    local REGEX=$(echo "$POD_NAMES" | xargs | tr ' ' '|')
    
    # Calculate aggregate peaks for scaling math
    TOTAL_PEAK_CPU=$(awk -F',' -v regex="$REGEX" 'NR>1 && $2 ~ regex {cpu[$2] = (cpu[$2] > $3 ? cpu[$2] : $3)} END {for (p in cpu) sum += cpu[p]; print sum}' "$RESOURCE_LOG")
    TOTAL_PEAK_MEM=$(awk -F',' -v regex="$REGEX" 'NR>1 && $2 ~ regex {mem[$2] = (mem[$2] > $4 ? mem[$2] : $4)} END {for (p in mem) sum += mem[p]; print sum}' "$RESOURCE_LOG")
  fi

  # =====================================================
  # MATHEMATICAL SCALING CALCULATIONS
  # =====================================================
  TARGET_CPU_UTIL=50 # Target 50% utilization
  IDEAL_POD_COUNT=$POD_COUNT
  CPU_REQ_RECOMMENDED="N/A"
  CPU_LIM_RECOMMENDED="N/A"
  MEM_REQ_RECOMMENDED="N/A"
  MEM_LIM_RECOMMENDED="N/A"
  COST_SAVINGS_PERCENT=0
  
  if [[ $POD_COUNT -gt 0 && $TOTAL_PEAK_CPU -gt 0 ]]; then
    # Calculate Ideal Pods: (Total Peak CPU / Target Utilization)
    IDEAL_POD_COUNT=$(awk -v total_cpu="$TOTAL_PEAK_CPU" -v target="$TARGET_CPU_UTIL" 'BEGIN {print int((total_cpu/target) + 0.99)}')
    [[ $IDEAL_POD_COUNT -lt 1 ]] && IDEAL_POD_COUNT=1
    
    # Calculate Resources per Pod
    local CPU_PER_POD=$(awk -v total_cpu="$TOTAL_PEAK_CPU" -v pods="$POD_COUNT" 'BEGIN {print total_cpu/pods}')
    local MEM_PER_POD=$(awk -v total_mem="$TOTAL_PEAK_MEM" -v pods="$POD_COUNT" 'BEGIN {print total_mem/pods}')
    
    # Recommendations with headroom
    CPU_REQ_RECOMMENDED=$(awk -v cpu="$CPU_PER_POD" 'BEGIN {printf "%.0fm", cpu * 1.2}')
    CPU_LIM_RECOMMENDED=$(awk -v cpu="$CPU_PER_POD" 'BEGIN {printf "%.0fm", cpu * 1.5}')
    MEM_REQ_RECOMMENDED=$(awk -v mem="$MEM_PER_POD" 'BEGIN {printf "%.0fMi", mem * 1.2}')
    MEM_LIM_RECOMMENDED=$(awk -v mem="$MEM_PER_POD" 'BEGIN {printf "%.0fMi", mem * 1.5}')
    
    # Calculate Savings
    COST_SAVINGS_PERCENT=$(awk -v cur="$POD_COUNT" -v ideal="$IDEAL_POD_COUNT" 'BEGIN {printf "%.1f", ((cur - ideal) / cur) * 100}')
  fi

  echo ""
  echo "=============================================="
  echo "📊 DETERMINISTIC SCALING SUMMARY"
  echo "=============================================="
  echo "• Metrics      : $TOTAL_COUNT req, $FAILURE_COUNT failed (${SUCCESS_RATE}% success)"
  echo "• Throughput   : ${THROUGHPUT} req/s"
  echo "• Current State: $POD_COUNT pods | Total Peak CPU: ${TOTAL_PEAK_CPU}m | Total Peak Mem: ${TOTAL_PEAK_MEM}Mi"
  echo "• Recommended  : $IDEAL_POD_COUNT pods"
  echo "• Resources/Pod: CPU Req/Lim: $CPU_REQ_RECOMMENDED / $CPU_LIM_RECOMMENDED | Mem Req/Lim: $MEM_REQ_RECOMMENDED / $MEM_LIM_RECOMMENDED"
  echo "• Est. Savings : ${COST_SAVINGS_PERCENT}%"
  echo "=============================================="
}

# -----------------------------
# AI ANALYSIS (Ollama)
# -----------------------------
analyze_with_ollama() {
  # Check if Ollama is available
  if ! curl -s --max-time 3 "$OLLAMA_API/api/tags" > /dev/null 2>&1; then
    echo ""
    echo "⚠️ AI Analysis skipped: Ollama not available at $OLLAMA_API"
    return 0
  fi
  
  echo ""
  echo "=============================================="
  echo "🤖 AI COST OPTIMIZATION ANALYSIS (Ollama)"
  echo "=============================================="

  # Build the prompt
  local PROMPT="You are a Kubernetes scaling expert. I have performed mathematical scaling calculations based on stress test metrics. 
Summarize these results and explain the reasoning and also let me know if there is any other solution to decrease the cost and increase the performance.

CALCULATED METRICS:
•  Requests: $TOTAL_COUNT total, $FAILURE_COUNT failed (${SUCCESS_RATE}% success)
•  Throughput: ${THROUGHPUT} req/s
•  Current State: $POD_COUNT pods | Peak CPU: $TOTAL_PEAK_CPU m | Peak Mem: $TOTAL_PEAK_MEM Mi
•  Missed Requests: $FAILURE_COUNT

DETERMINISTIC RECOMMENDATIONS (Use these in your report):
1. HORIZONTAL SCALING:
   - Recommended: $IDEAL_POD_COUNT pods (Targeting ${TARGET_CPU_UTIL}% CPU utilization)
   - Estimated Savings: ${COST_SAVINGS_PERCENT}%

2. VERTICAL SCALING:
   - CPU Request/Limit: $CPU_REQ_RECOMMENDED / $CPU_LIM_RECOMMENDED
   - Memory Request/Limit: $MEM_REQ_RECOMMENDED / $MEM_LIM_RECOMMENDED

Write a concise report following this structure:
1. MISSED REQUESTS: Analysis of failures.
2. HORIZONTAL SCALING: Recommendation based on the calculated $IDEAL_POD_COUNT pods.
3. VERTICAL SCALING: Justify the resource recommendations.
4. ESTIMATED SAVINGS: Explain the ${COST_SAVINGS_PERCENT}% savings/cost impact.

Monthly cost estimate: Assuming \$0.05/pod/hour, current cost is \$$(awk -v p="$POD_COUNT" 'BEGIN {printf "%.2f", p * 0.05 * 24 * 30}') vs optimized \$$(awk -v p="$IDEAL_POD_COUNT" 'BEGIN {printf "%.2f", p * 0.05 * 24 * 30}').

Keep it professional and data-driven. No disclaimers or filler."

  # Escape the prompt for JSON
  local ESCAPED_PROMPT=$(echo "$PROMPT" | jq -Rs .)
  
  # Call Ollama API
  echo "Analyzing with $OLLAMA_MODEL..."
  echo ""
  
  local RESPONSE=$(curl -s --max-time 60 "$OLLAMA_API/api/generate" \
    -H "Content-Type: application/json" \
    -d "{\"model\": \"$OLLAMA_MODEL\", \"prompt\": $ESCAPED_PROMPT, \"stream\": false}" 2>/dev/null)
  
  if [[ -z "$RESPONSE" ]]; then
    echo "⚠️  No response from Ollama - model may be loading or unavailable"
    return 0
  fi
  
  # Extract the response text
  local ANALYSIS=$(echo "$RESPONSE" | jq -r '.response // empty' 2>/dev/null)
  
  if [[ -n "$ANALYSIS" ]]; then
    echo "----------------------------------------------"
    echo "$ANALYSIS"
    echo "----------------------------------------------"
    echo ""
    
    # Save analysis to file for later reference
    local ANALYSIS_FILE="/tmp/stress_analysis_$(date +%Y%m%d_%H%M%S).txt"
    {
      echo "Stress Test Analysis - $(date)"
      echo "=============================================="
      echo "Metrics:"
      echo "  Requests: $TOTAL_COUNT (${SUCCESS_RATE}% success)"
      echo "  Duration: ${DURATION}s | Throughput: ${THROUGHPUT} req/s"
      echo "  Pods: $POD_COUNT"
      echo ""
      echo "AI Analysis:"
      echo "$ANALYSIS"
    } > "$ANALYSIS_FILE"
    echo "📄 Analysis saved to: $ANALYSIS_FILE"
  else
    echo "⚠️  Could not parse Ollama response"
    echo "Raw response: $RESPONSE"
  fi
}

echo ""
echo "✅ STRESS TEST COMPLETED SUCCESSFULLY"

# 1. Calculate and show deterministic summary
calculate_stats

# 2. Run AI analysis if possible
analyze_with_ollama
