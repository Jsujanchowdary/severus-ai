# Severus AI - Comprehensive Research Documentation

## 1. Executive Summary
Severus AI is an advanced, cloud-native personal AI platform designed for secure, high-performance inference in a zero-trust environment. It addresses the critical gap between local LLM accessibility and production-grade reliability by introducing a performance-gated CI/CD pipeline and automated AI-driven fault recovery.

---

## 2. System Architecture

The system utilizes a **Sidecar Pattern** for security offloading and an autonomous **Performance Validation Controller** (Stress Pod) within the deployment lifecycle.

### A. Integrated Architecture
Refer to the `OVERALL_ARCHITECTURE.md` for visual diagrams. The system resides in a Kubernetes cluster, utilizing Traefik as the Ingress controller and `cert-manager` for dynamic certificate issuance.

---

## 3. Core Feature Implementations

### A. High-Performance Sidecar Proxy (nginx.conf)
The Nginx sidecar is the primary security boundary. It enforces Mutual TLS (mTLS) for all internal service discovery.

```nginx
# config/nginx.conf
events {
    worker_connections 1024;
}

http {
    upstream streamlit {
        server 127.0.0.1:8502;
    }

    server {
        listen 8501 ssl;
        ssl_certificate /etc/certs/tls.crt;
        ssl_certificate_key /etc/certs/tls.key;
        ssl_client_certificate /etc/certs/ca.crt;
        ssl_verify_client on;
        
        location / {
            proxy_pass http://streamlit;
        }
    }

    server {
        listen 8080;
        location / {
            proxy_pass http://streamlit;
        }
    }
}
```

### B. Intelligent AI Debugger (ai_debugger.py)
A specialized agent that autonomously investigates build failures.

```python
# ai_debugger.py excerpt
def extract_runtime_error(log_text):
    patterns = [
        r'NameError: name \'(\w+)\' is not defined',
        r'ModuleNotFoundError: No module named \'(\w+)\'',
        r'SyntaxError:.*?(\w+)',
    ]
    for pattern in patterns:
        match = re.search(pattern, log_text)
        if match: return match.group(1)
    return None

def locate_token_in_repo(token, repo_index):
    # Deterministic search before AI analysis
    findings = []
    for file_entry in repo_index:
        for idx, line in enumerate(file_entry["lines"], start=1):
            if token in line:
                findings.append({"file": file_entry["file"], "line": idx, "code": line.strip()})
    return findings
```

### C. Performance Validation Controller (stress_pod.sh)
Ensures 99.9% request success rate before allowing a production rollout.

```bash
# stress-pod/stress_pod.sh (Core Logic)
for i in $(seq 1 "$TOTAL_REQUESTS"); do
  (
    if curl -s --cert "$CLIENT_CERT" --key "$CLIENT_KEY" --cacert "$CA_BUNDLE" \
       -X GET "$TARGET" | grep -q "Streamlit"; then
      increment "$SUCCESS_FILE"
    else
      increment "$FAILURE_FILE"
    fi
  ) &
done
```

---

## 4. Source Code Repository

### Master Core (app.py)
The primary application entry point, integrating security middleware and observability.

```python
# app.py
from cert_middleware import init_certificate_verifier
cert_verifier = init_certificate_verifier(
    ca_bundle_path="/etc/certs/ca.crt",
    enforce_mode=os.getenv("CERT_ENFORCE_MODE", "permissive")
)

# ... Streamlit Logic ...
if st.button("Summarize Uploaded Document"):
    reply = chat_with_model("deepseek-v3.1:671b-cloud", messages, chat_id=chat_id)
```

### Observability Layer (metrics.py)
Exposes custom instrumentation to Prometheus.

```python
# metrics.py
CERT_VERIFICATION_SUCCESS = Counter("severus_cert_verification_success_total", "...")
OLLAMA_REQUEST_DURATION = Histogram("severus_ollama_request_duration_seconds", "...", buckets=(0.5, 1.0, 5.0, 30.0))

def track_ollama_call(model, duration, success=True):
    status = "success" if success else "error"
    OLLAMA_CALLS.labels(model=model, status=status).inc()
    OLLAMA_REQUEST_DURATION.labels(model=model).observe(duration)
```

### CI/CD Pipeline Definition (Jenkinsfile)
The automated orchestration of build, security scan, stress test, and AI-driven recovery.

```groovy
// Jenkinsfile (Deployment & Stress Test Phases)
stage('Deploy to Kubernetes') {
    $HELM_BIN upgrade --install severus-ai helm/severus-ai
}
stage('Performance Evaluation') {
    $HELM_BIN upgrade --install severus-ai helm/severus-ai --set stress.enabled=true
    // Check Job Status for Success
}
post {
    always {
        // AI Debugger Recovery
        sh "python3 ai_debugger.py --repo-path ${WORKSPACE} --log-path ${logFile} --status ${status}"
    }
}
```

---

## 5. Deployment & Persistence

### Persistence (storage.py & auth.py)
Reliable state management for user sessions and chat history.

```python
# storage.py
def init_db():
    cur.execute("CREATE TABLE IF NOT EXISTS chats (id INTEGER PRIMARY KEY, username TEXT, title TEXT)")
    cur.execute("CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY, chat_id INTEGER, role TEXT, content TEXT)")
```

### Kubernetes Configuration (values.yaml)
Declarative infrastructure management.

```yaml
# helm/severus-ai/values.yaml
hpa:
  enabled: true
  minReplicas: 1
  maxReplicas: 5
  cpu:
    averageUtilization: 50
    
certificates:
  enabled: true
  nginx:
    verifyClient: "on"
```

---

## 6. Conclusion
The Severus AI architecture demonstrates a viable pathway for deploying sensitive AI workloads in insecure environments. By utilizing Sidecar security patterns and an AI-driven CI/CD recovery loop, the system achieves a level of reliability and security previously reserved for proprietary enterprise platforms.
