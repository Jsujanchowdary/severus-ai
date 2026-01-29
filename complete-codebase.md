# Kube Stress Simulator - Complete Codebase

This document contains all the source code from the kube-stress-simulator project, organized by directory structure.

---

## Directory Structure

```
kube-stress-simulator/
├── app/
│   ├── Dockerfile
│   └── app.py
├── stress-pod/
│   ├── Dockerfile
│   └── stress_pod.sh
└── helm/
    └── stress-simulator/
        ├── Chart.yaml
        ├── values.yaml
        └── templates/
            ├── hpa-service-a.yaml
            ├── hpa-service-b.yaml
            ├── metrics-rbac.yaml
            ├── rbac.yaml
            ├── service-a.yaml
            ├── service-b.yaml
            ├── services.yaml
            └── stress-pod.yaml
```

---

## 📁 app/

### app/Dockerfile

```dockerfile
FROM ubuntu:22.04

ENV DEBIAN_FRONTEND=noninteractive

# Install system packages
RUN apt-get update && apt-get install -y \
    python3 \
    python3-pip \
    vim \
    curl \
    ca-certificates \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Copy application
COPY app.py .

# Install Python dependencies
RUN pip3 install flask

EXPOSE 8080

CMD ["python3", "app.py"]
```

### app/app.py

```python
from flask import Flask, request, jsonify
import time
import os
import json
from datetime import datetime

app = Flask(__name__)

SERVICE_NAME = os.getenv("SERVICE_NAME", "unknown-service")

LOG_DIR = "/var/log/app"
LOG_FILE = f"{LOG_DIR}/requests.log"

# Ensure log directory exists
os.makedirs(LOG_DIR, exist_ok=True)

@app.route("/process", methods=["POST"])
def process():
    data = request.json or {}

    log_message = {
        "service": SERVICE_NAME,
        "request_id": data.get("request_id"),
        "payload": data.get("payload"),
        "source": data.get("source"),
        "sent_timestamp": data.get("timestamp"),
        "received_epoch": time.time(),
        "received_utc": datetime.utcnow().isoformat() + "Z"
    }

    log_line = json.dumps(log_message)

    # 1️⃣ Write to file
    with open(LOG_FILE, "a") as f:
        f.write(log_line + "\n")

    # 2️⃣ Also print to stdout (kubectl logs)
    print(log_line, flush=True)

    return jsonify({
        "status": "processed",
        "service": SERVICE_NAME
    })

@app.route("/health")
def health():
    return jsonify({"health": "healthy"})

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8080)
```

---

## 📁 stress-pod/

### stress-pod/Dockerfile

```dockerfile
FROM ubuntu:22.04

ARG KUBECTL_VERSION=v1.29.0

RUN apt-get update && \
    apt-get install -y curl bash ca-certificates && \
    curl -LO https://dl.k8s.io/release/${KUBECTL_VERSION}/bin/linux/amd64/kubectl && \
    install -o root -g root -m 0755 kubectl /usr/local/bin/kubectl && \
    rm -rf /var/lib/apt/lists/* kubectl

WORKDIR /stress
COPY stress_pod.sh .
RUN chmod +x stress_pod.sh

# 🔑 THIS IS THE KEY LINE
ENTRYPOINT ["./stress_pod.sh"]
```

### stress-pod/stress_pod.sh

```bash
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
# Readiness check
# -----------------------------
for TARGET in "${TARGETS[@]}"; do
  HEALTH_URL="${TARGET%/process}/health"
  echo "Waiting for target to be ready: $HEALTH_URL"
  until curl -s "$HEALTH_URL" >/dev/null; do sleep 1; done
done

# -----------------------------
# Clear old logs
# -----------------------------
if [[ ${#POD_LABELS[@]} -gt 0 ]]; then
  echo ""
  echo "Clearing old logs before stress run"
  echo "----------------------------------------------"
  for LABEL in "${POD_LABELS[@]}"; do
    for POD in $(kubectl get pods -l "$LABEL" -o jsonpath='{.items[*].metadata.name}'); do
      kubectl exec "$POD" -- sh -c "rm -f /var/log/app/requests.log || true"
    done
  done
fi

# -----------------------------
# Resource Monitoring (NO LABEL FILTERS)
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
        if curl -s --max-time 5 -X POST "$TARGET" \
          -H "Content-Type: application/json" \
          -d "$REQUEST_BODY" >/dev/null; then
          increment "$SUCCESS_FILE"
        else
          increment "$FAILURE_FILE"
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
# Resource Peak Summary (SAFE)
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
# Validation (STRICT – unchanged)
# -----------------------------
if [[ ${#POD_LABELS[@]} -gt 0 ]]; then
  echo ""
  echo "Validation started"
  echo "----------------------------------------------"

  OVERALL_STATUS="PASS"
  EXPECTED_TOTAL=$((TOTAL_REQUESTS * RUNS))

  for LABEL in "${POD_LABELS[@]}"; do
    TOTAL_SEEN=0
    for POD in $(kubectl get pods -l "$LABEL" -o jsonpath='{.items[*].metadata.name}'); do
      COUNT=$(kubectl exec "$POD" -- \
        sh -c "grep -c stress-pod /var/log/app/requests.log 2>/dev/null || echo 0")
      COUNT=$(echo "$COUNT" | tr -cd '0-9')
      TOTAL_SEEN=$((TOTAL_SEEN + COUNT))
      echo "Pod: $POD → Requests seen: $COUNT"
    done

    LOSS=$((EXPECTED_TOTAL - TOTAL_SEEN))
    LOSS_PERCENT=$((LOSS * 100 / EXPECTED_TOTAL))

    echo "Service label       : $LABEL"
    echo "Expected total      : $EXPECTED_TOTAL"
    echo "Total requests seen : $TOTAL_SEEN"
    echo "Lost requests       : $LOSS (${LOSS_PERCENT}%)"

    (( TOTAL_SEEN < EXPECTED_TOTAL )) && OVERALL_STATUS="FAIL"
    echo "----------------------------------------------"
  done

  echo "Overall validation status : $OVERALL_STATUS"
  [[ "$OVERALL_STATUS" == "FAIL" ]] && exit 1
fi
```

---

## 📁 helm/stress-simulator/

### helm/stress-simulator/Chart.yaml

```yaml
apiVersion: v2
name: stress-simulator
description: Kubernetes pod stress simulator with data payload, time tracking, and RBAC
type: application
version: 0.1.0
appVersion: "2.0"
```

### helm/stress-simulator/values.yaml

```yaml
# ------------------------
# Global Settings
# ------------------------
global:
  imagePullPolicy: IfNotPresent

# ------------------------
# Application Image
# ------------------------
app:
  image:
    repository: sujanchow/kube-app
    tag: "4.0"

  resources:
    requests:
      cpu: "50m"
      memory: "16Mi"
    limits:
      cpu: "60m"
      memory: "24Mi"

# ------------------------
# Stress Pod Image
# ------------------------
stress:
  image:
    repository: sujanchow/stress-pod
    tag: "2.3"

  args:
    targets:
      - http://service-a:8080/process
      - http://service-b:8080/process

    totalRequests: 500
    concurrency: 20

    runs: 5
    sleepSeconds: 5

    podLabels:
      - app=service-a
      - app=service-b


# ------------------------
# Services
# ------------------------
service:
  port: 8080
  type: ClusterIP

# ------------------------
# RBAC
# ------------------------
rbac:
  create: true
  serviceAccountName: stress-sa

# ------------------------
# HPA Configuration
# ------------------------
hpa:
  enabled: true

  minReplicas: 1
  maxReplicas: 10

  cpu:
    averageUtilization: 50

```

---

## 📁 helm/stress-simulator/templates/

### helm/stress-simulator/templates/hpa-service-a.yaml

```yaml
{{- if .Values.hpa.enabled }}
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: service-a-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: service-a
  minReplicas: {{ .Values.hpa.minReplicas }}
  maxReplicas: {{ .Values.hpa.maxReplicas }}
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: {{ .Values.hpa.cpu.averageUtilization }}
{{- end }}
```

### helm/stress-simulator/templates/hpa-service-b.yaml

```yaml
{{- if .Values.hpa.enabled }}
apiVersion: autoscaling/v2
kind: HorizontalPodAutoscaler
metadata:
  name: service-b-hpa
spec:
  scaleTargetRef:
    apiVersion: apps/v1
    kind: Deployment
    name: service-b
  minReplicas: {{ .Values.hpa.minReplicas }}
  maxReplicas: {{ .Values.hpa.maxReplicas }}
  metrics:
    - type: Resource
      resource:
        name: cpu
        target:
          type: Utilization
          averageUtilization: {{ .Values.hpa.cpu.averageUtilization }}
{{- end }}
```

### helm/stress-simulator/templates/metrics-rbac.yaml

```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: stress-metrics-reader
rules:
- apiGroups: ["metrics.k8s.io"]
  resources:
    - pods
  verbs:
    - get
    - list
---
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: stress-metrics-binding
subjects:
- kind: ServiceAccount
  name: stress-sa
  namespace: default
roleRef:
  kind: ClusterRole
  name: stress-metrics-reader
  apiGroup: rbac.authorization.k8s.io
```

### helm/stress-simulator/templates/rbac.yaml

```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: stress-sa
---
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: pod-reader
rules:
# Allow viewing pods
- apiGroups: [""]
  resources:
    - pods
  verbs:
    - get
    - list
    - watch

# Allow reading pod logs
- apiGroups: [""]
  resources:
    - pods/log
  verbs:
    - get

# ✅ Allow kubectl exec
- apiGroups: [""]
  resources:
    - pods/exec
  verbs:
    - create
---
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: stress-binding
subjects:
- kind: ServiceAccount
  name: stress-sa
roleRef:
  kind: Role
  name: pod-reader
  apiGroup: rbac.authorization.k8s.io
```

### helm/stress-simulator/templates/service-a.yaml

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: service-a
spec:
  replicas: 1
  selector:
    matchLabels:
      app: service-a
  template:
    metadata:
      labels:
        app: service-a
    spec:
      containers:
      - name: app
        image: sujanchow/kube-app:3.0
        env:
        - name: SERVICE_NAME
          value: "service-a"
        ports:
        - containerPort: 8080

        # 🔥 RESOURCE LIMITS (THIS IS THE KEY FIX)
        resources:
          requests:
            cpu: "50m"
            memory: "16Mi"
          limits:
            cpu: "60m"
            memory: "24Mi"

        volumeMounts:
        - name: app-logs
          mountPath: /var/log/app

      volumes:
      - name: app-logs
        emptyDir: {}
```

### helm/stress-simulator/templates/service-b.yaml

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: service-b
spec:
  replicas: 1
  selector:
    matchLabels:
      app: service-b
  template:
    metadata:
      labels:
        app: service-b
    spec:
      containers:
      - name: app
        image: sujanchow/kube-app:3.0
        env:
        - name: SERVICE_NAME
          value: "service-b"
        ports:
        - containerPort: 8080

        # 🔥 RESOURCE LIMITS (THIS IS THE KEY FIX)
        resources:
          requests:
            cpu: "50m"
            memory: "16Mi"
          limits:
            cpu: "60m"
            memory: "24Mi"

        volumeMounts:
        - name: app-logs
          mountPath: /var/log/app
      volumes:
      - name: app-logs
        emptyDir: {}
```

### helm/stress-simulator/templates/services.yaml

```yaml
---
apiVersion: v1
kind: Service
metadata:
  name: service-a
spec:
  type: {{ .Values.service.type }}
  selector:
    app: service-a
  ports:
    - port: 8080
      targetPort: 8080
---
apiVersion: v1
kind: Service
metadata:
  name: service-b
spec:
  type: {{ .Values.service.type }}
  selector:
    app: service-b
  ports:
    - port: 8080
      targetPort: 8080
```

### helm/stress-simulator/templates/stress-pod.yaml

```yaml
apiVersion: batch/v1
kind: Job
metadata:
  name: stress-pod
spec:
  backoffLimit: 0
  template:
    metadata:
      labels:
        app: stress
    spec:
      serviceAccountName: stress-sa
      restartPolicy: Never
      containers:
        - name: stress
          image: "{{ .Values.stress.image.repository }}:{{ .Values.stress.image.tag }}"
          imagePullPolicy: Always

          command: ["/bin/bash", "-c"]
          args:
            - |
              ./stress_pod.sh \
{{- range .Values.stress.args.targets }}
                -t {{ . }} \
{{- end }}
                -tr {{ .Values.stress.args.totalRequests }} \
                -c {{ .Values.stress.args.concurrency }} \
                -r {{ .Values.stress.args.runs }} \
                -s {{ .Values.stress.args.sleepSeconds }} \
{{- range .Values.stress.args.podLabels }}
                -p {{ . }} \
{{- end }}
```

---

## Summary

This document contains the complete codebase for the **kube-stress-simulator** project, including:

- **Application Service** (`app/`): Flask-based microservice that processes requests and logs them
- **Stress Testing Pod** (`stress-pod/`): Bash script-based load generator with kubectl integration
- **Helm Chart** (`helm/stress-simulator/`): Kubernetes deployment configuration with:
  - Service deployments (service-a, service-b)
  - Horizontal Pod Autoscalers (HPA)
  - RBAC configurations
  - Kubernetes Services
  - Stress testing Job

All code is presented exactly as it exists in the repository with no modifications.
