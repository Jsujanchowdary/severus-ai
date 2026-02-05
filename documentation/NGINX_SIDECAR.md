# nginx Sidecar Implementation Summary

## Changes Made

### 1. nginx Configuration Files

**Created `config/nginx.conf`:**
- Dual-server configuration
- Port 8501: HTTPS with mTLS validation (for internal pod-to-pod)
- Port 8080: Plain HTTP (for browser/Ingress access)
- Both forward to Streamlit on localhost:8502

**Created `helm/severus-ai/templates/nginx-config.yaml`:**
- ConfigMap template for nginx configuration
- Templated `ssl_verify_client` setting from values.yaml

### 2. Deployment Updates

**Modified `helm/severus-ai/templates/deployment.yaml`:**
- Added nginx sidecar container (when certificates.enabled=true)
- nginx listens on ports 8501 (HTTPS/mTLS) and 8080 (HTTP)
- Streamlit moved to internal port 8502
- nginx ConfigMap mounted at `/etc/nginx/nginx.conf`
- TLS certificates mounted at `/etc/certs/`
- Health probes use nginx port 8080

### 3. Service Updates

**Modified `helm/severus-ai/templates/service.yaml`:**
- When certificates enabled:
  - Port 8501 → nginx HTTPS/mTLS
  - Port 8080 → nginx HTTP
- When certificates disabled:
  - Port 8501 → Streamlit directly

### 4. Ingress Updates

**Modified `helm/severus-ai/templates/ingress.yaml`:**
- Routes to port 8080 (plain HTTP) when certificates enabled
- Browser access works without certificates

### 5. Values Configuration

**Modified `helm/severus-ai/values.yaml`:**
- Added `certificates.nginx` section
- nginx image: `nginx:1.25-alpine`
- `verifyClient: optional` (permissive mode)

### 6. stress-pod Configuration

**stress-pod/stress_pod.sh:**
- Already configured to use HTTPS with client certificates
- Will use port 8501 with mTLS validation
- Falls back to HTTP if certificates not found

---

## Architecture

```
┌─────────────────────────────────────────────────────────┐
│                  Severus AI Pod                         │
│                                                         │
│  ┌────────────────┐         ┌──────────────────┐      │
│  │ nginx Sidecar  │────────▶│  Streamlit App   │      │
│  │                │         │  localhost:8502  │      │
│  │ Port 8501 ◀────┼─────────┤                  │      │
│  │ (mTLS)         │         │                  │      │
│  │                │         │                  │      │
│  │ Port 8080 ◀────┼─────────┤                  │      │
│  │ (HTTP)         │         │                  │      │
│  └────────────────┘         └──────────────────┘      │
│         ▲                                               │
└─────────┼───────────────────────────────────────────────┘
          │
    ┌─────┴──────┐
    │            │
Internal Traffic  External Traffic
(stress-pod)     (Browser/Ingress)
    │                │
Port 8501        Port 8080
(HTTPS/mTLS)     (HTTP)
```

---

## Traffic Flow

### Internal Traffic (stress-pod → Severus AI)
```
stress-pod
  └─> https://severus-ai:8501 (with client cert)
       └─> nginx validates certificate
            └─> ✅ Valid → Forward to Streamlit:8502
            └─> ❌ Invalid → 400 Bad Request (SSL error)
```

### External Traffic (Browser/Ingress → Severus AI)
```
Browser/Ingress
  └─> http://severus-ai:8080 (no cert needed)
       └─> nginx (no validation)
            └─> Forward to Streamlit:8502
```

---

## Next Steps

1. **Deploy to Kubernetes**
   ```bash
   helm upgrade --install severus-ai helm/severus-ai \
     --set image.repository=sujanchow/serverus-ai \
     --set image.tag=v1
   ```

2. **Verify nginx is running**
   ```bash
   kubectl get pods -l app=severus-ai
   kubectl logs deployment/severus-ai -c nginx
   ```

3. **Test mTLS validation**
   ```bash
   # Should succeed (with valid cert)
   kubectl exec -it deployment/stress-pod -- curl \
     --cert /etc/certs/tls.crt \
     --key /etc/certs/tls.key \
     --cacert /etc/certs/ca.crt \
     https://severus-ai:8501
   
   # Should fail (without cert)
   kubectl run test-pod --rm -it --image=curlimages/curl -- \
     curl https://severus-ai:8501
   ```

4. **Test plain HTTP access**
   ```bash
   # Should succeed (no cert needed)
   kubectl port-forward svc/severus-ai 8080:8080
   curl http://localhost:8080
   ```

5. **Run stress test**
   ```bash
   kubectl delete job stress-pod --ignore-not-found
   helm upgrade --install severus-ai helm/severus-ai \
     --set stress.enabled=true
   kubectl logs job/stress-pod -f
   ```

6. **Check nginx logs for certificate validation**
   ```bash
   kubectl logs deployment/severus-ai -c nginx | grep SSL
   ```

---

## Configuration Options

### Strict Mode (Reject invalid certificates)
```yaml
# values.yaml
certificates:
  nginx:
    verifyClient: on  # Require valid certificate
```

### Permissive Mode (Allow but log)
```yaml
# values.yaml
certificates:
  nginx:
    verifyClient: optional  # Allow without cert
```

---

## Files Modified

- ✅ `config/nginx.conf` (new)
- ✅ `helm/severus-ai/templates/nginx-config.yaml` (new)
- ✅ `helm/severus-ai/templates/deployment.yaml` (modified)
- ✅ `helm/severus-ai/templates/service.yaml` (modified)
- ✅ `helm/severus-ai/templates/ingress.yaml` (modified)
- ✅ `helm/severus-ai/values.yaml` (modified)
- ✅ `stress-pod/stress_pod.sh` (already configured correctly)
