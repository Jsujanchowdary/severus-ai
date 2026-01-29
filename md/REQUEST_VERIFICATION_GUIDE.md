# 📊 Verifying Stress Test Requests with kubectl

## Current Situation

The severus-ai Streamlit app **doesn't log individual HTTP requests** by default. The logs only show:
- Application startup
- User logins
- Chat creation

```bash
kubectl logs severus-ai-7c9bf475d9-5r4dx
# Output:
# Collecting usage statistics...
# You can now view your Streamlit app...
# [INFO] auth - User logged in: sujancho
# [INFO] chat - Chat created: 24 for sujancho
```

## ✅ Solution: Add Request Logging to Streamlit

### Method 1: Add Middleware Logging (Recommended)

Update `app.py` to log every HTTP request:

```python
import streamlit as st
import logging
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Log every request
logger.info(f"HTTP Request received at {datetime.utcnow().isoformat()}")

# Rest of your Streamlit app...
```

### Method 2: Use Nginx/Traefik Access Logs

Since you're using Traefik ingress, check Traefik's access logs:

```bash
# Get Traefik pod
kubectl -n kube-system get pods -l app.kubernetes.io/name=traefik

# View access logs
kubectl -n kube-system logs <traefik-pod-name> | grep "severus-ai"

# Count requests
kubectl -n kube-system logs <traefik-pod-name> | grep "severus-ai" | wc -l
```

## 🔍 Current Verification Methods

### 1. Count Requests from Stress Pod Logs

```bash
# Get stress pod logs
kubectl logs job/stress-pod > stress-logs.txt

# Count successful requests
grep "Success requests" stress-logs.txt

# Output: Success requests     : 20000
```

### 2. Check HPA Metrics (Indirect)

```bash
# CPU spike indicates requests were processed
kubectl top pods -l app=severus-ai

# HPA scaling shows load was handled
kubectl get hpa severus-ai-hpa
```

### 3. Monitor Resource Usage

```bash
# From stress test logs - shows pod was under load
kubectl logs job/stress-pod | grep "RESOURCE USAGE"

# Output:
# Pod: severus-ai-7c9bf475d9-5r4dx  CPU_peak=99m Memory_peak=171Mi
```

## 🎯 Best Practice: Add Request Counter

### Option A: Simple Counter in app.py

```python
import streamlit as st

# Initialize counter in session state
if 'request_count' not in st.session_state:
    st.session_state.request_count = 0

# Increment on each request
st.session_state.request_count += 1

# Log it
print(f"Request #{st.session_state.request_count} at {datetime.utcnow()}", flush=True)
```

### Option B: Use Prometheus Metrics

Add prometheus client to track requests:

```python
from prometheus_client import Counter, generate_latest

request_counter = Counter('http_requests_total', 'Total HTTP requests')

@app.route('/metrics')
def metrics():
    request_counter.inc()
    return generate_latest()
```

## 📝 Quick Verification Commands

```bash
# 1. Get all severus-ai pods
kubectl get pods -l app=severus-ai

# 2. Check logs from all pods
for pod in $(kubectl get pods -l app=severus-ai -o name); do
  echo "=== $pod ==="
  kubectl logs $pod | tail -20
done

# 3. Count log lines (rough estimate)
kubectl logs severus-ai-7c9bf475d9-5r4dx | wc -l

# 4. Check stress test results
kubectl logs job/stress-pod | grep -E "(Success|Failed) requests"
```

## 🔥 Real-Time Monitoring During Stress Test

```bash
# Terminal 1: Watch pod scaling
kubectl get pods -l app=severus-ai --watch

# Terminal 2: Monitor HPA
kubectl get hpa severus-ai-hpa --watch

# Terminal 3: Watch resource usage
watch -n 2 'kubectl top pods -l app=severus-ai'

# Terminal 4: Stream stress test logs
kubectl logs -f job/stress-pod
```

## ✅ Recommended Solution

**Add this to your `app.py`** to log every request:

```python
import streamlit as st
import logging
from datetime import datetime

# At the top of app.py
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[logging.StreamHandler()]
)
logger = logging.getLogger(__name__)

# Log every page load
logger.info(f"Page request from {st.session_state.get('username', 'anonymous')}")
```

Then verify with:

```bash
# Count all requests
kubectl logs severus-ai-7c9bf475d9-5r4dx | grep "Page request" | wc -l

# See request timestamps
kubectl logs severus-ai-7c9bf475d9-5r4dx | grep "Page request"
```

---

**Current Status:** The stress test's internal counters (20,000 requests) are accurate. To verify via pod logs, you need to add request logging to the Streamlit app.
