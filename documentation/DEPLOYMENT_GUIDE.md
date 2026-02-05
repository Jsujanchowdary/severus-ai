# Deploying Severus AI with Certificate Manager

This guide walks you through deploying Severus AI with mutual TLS (mTLS) certificate verification.

## Prerequisites

- Kubernetes cluster (Minikube, kind, or cloud provider)
- kubectl configured
- Helm 3.x installed
- Docker images built and pushed (or available locally)

## Quick Start

```bash
# 1. Install cert-manager
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.14.0/cert-manager.yaml

# 2. Wait for cert-manager to be ready
kubectl wait --for=condition=ready pod -l app=cert-manager -n cert-manager --timeout=300s

# 3. Create ClusterIssuer
kubectl apply -f k8s/cluster-issuer.yaml

# 4. Deploy Severus AI
helm upgrade --install severus-ai ./helm/severus-ai

# 5. Verify deployment
kubectl get pods
kubectl get certificates
kubectl get secrets | grep tls
```

## Detailed Steps

### Step 1: Install cert-manager

cert-manager is a Kubernetes add-on that automates certificate management.

```bash
# Install cert-manager CRDs and controller
kubectl apply -f https://github.com/cert-manager/cert-manager/releases/download/v1.14.0/cert-manager.yaml

# Verify installation
kubectl get pods -n cert-manager

# Expected output:
# NAME                                       READY   STATUS    RESTARTS   AGE
# cert-manager-xxxxxxxxxx-xxxxx              1/1     Running   0          1m
# cert-manager-cainjector-xxxxxxxxxx-xxxxx   1/1     Running   0          1m
# cert-manager-webhook-xxxxxxxxxx-xxxxx      1/1     Running   0          1m
```

### Step 2: Create ClusterIssuer

The ClusterIssuer creates a self-signed Certificate Authority (CA) for internal certificates.

```bash
# Apply ClusterIssuer configuration
kubectl apply -f k8s/cluster-issuer.yaml

# Verify ClusterIssuer is ready
kubectl get clusterissuer

# Expected output:
# NAME                       READY   AGE
# selfsigned-cluster-issuer  True    10s
# severus-ai-ca-issuer       True    10s

# Check CA certificate
kubectl get certificate -n cert-manager
kubectl get secret severus-ai-ca-secret -n cert-manager
```

### Step 3: Configure Deployment

Review and customize `helm/severus-ai/values.yaml`:

```yaml
certificates:
  enabled: true  # Enable certificate verification
  issuer: severus-ai-ca-issuer
  
  verification:
    enforceMode: permissive  # Start with permissive, change to strict after testing
```

**Enforcement Modes:**
- `permissive`: Allows requests without certificates (logs warnings) - **Recommended for initial deployment**
- `strict`: Rejects all requests without valid certificates - **Use in production**

### Step 4: Deploy Severus AI

```bash
# Deploy using Helm
helm upgrade --install severus-ai ./helm/severus-ai

# Watch deployment progress
kubectl get pods -w

# Expected pods:
# - severus-ai-xxxxxxxxxx-xxxxx (Running)
# - stress-pod-xxxxx (Completed)
```

### Step 5: Verify Certificates

```bash
# Check certificates are created
kubectl get certificates

# Expected output:
# NAME              READY   SECRET            AGE
# severus-ai-ca     True    severus-ai-ca-secret   2m
# severus-ai-tls    True    severus-ai-tls    1m
# stress-pod-tls    True    stress-pod-tls    1m

# Check certificate secrets
kubectl get secrets | grep tls

# Inspect certificate details
kubectl describe certificate severus-ai-tls
```

### Step 6: Test mTLS Connection

```bash
# Check stress-pod logs (should show successful mTLS connection)
kubectl logs job/stress-pod

# Expected output:
# ✅ mTLS certificates found
#    Client cert: /etc/certs/tls.crt
#    Client key:  /etc/certs/tls.key
#    CA bundle:   /etc/certs/ca.crt
# Waiting for target to be ready: http://severus-ai:8501
# ✅ Target is ready: http://severus-ai:8501

# Check Severus AI logs for certificate verification
kubectl logs -l app=severus-ai -c severus-ai | grep -i cert

# Expected output:
# Certificate verification enabled (mode: permissive)
# CA bundle: /etc/certs/ca.crt
```

### Step 7: Monitor Metrics

```bash
# Port-forward to metrics endpoint
kubectl port-forward svc/severus-ai 8000:8000

# In another terminal, check metrics
curl http://localhost:8000/metrics | grep cert_verification

# Expected metrics:
# severus_cert_verification_success_total 150
# severus_cert_verification_failure_total{reason="missing"} 0
```

## Testing Certificate Verification

### Test 1: Trusted Pod (stress-pod)

```bash
# Run stress test
kubectl delete job stress-pod  # Delete old job
helm upgrade --install severus-ai ./helm/severus-ai  # Recreate

# Check logs
kubectl logs job/stress-pod

# Should see successful requests
```

### Test 2: Untrusted Pod (no certificate)

```bash
# Try to connect without certificate
kubectl run test-pod --image=curlimages/curl --rm -it -- \
  curl http://severus-ai:8501

# In permissive mode: Should succeed with warning in logs
# In strict mode: Should fail with 403 Forbidden
```

### Test 3: Switch to Strict Mode

```bash
# Update to strict mode
helm upgrade severus-ai ./helm/severus-ai \
  --set certificates.verification.enforceMode=strict

# Test untrusted pod again (should fail)
kubectl run test-pod --image=curlimages/curl --rm -it -- \
  curl http://severus-ai:8501

# Expected: Connection refused or 403 Forbidden
```

## Troubleshooting

### Certificates Not Created

```bash
# Check cert-manager logs
kubectl logs -n cert-manager -l app=cert-manager --tail=50

# Check certificate status
kubectl describe certificate severus-ai-tls

# Common issues:
# - ClusterIssuer not ready: Wait longer or check issuer status
# - Invalid issuerRef: Verify issuer name matches
# - Namespace mismatch: Ensure certificate and issuer are in correct namespaces
```

### Pods Not Starting

```bash
# Check pod status
kubectl describe pod -l app=severus-ai

# Check events
kubectl get events --sort-by='.lastTimestamp'

# Common issues:
# - Secret not found: Verify certificate secret exists
# - Volume mount error: Check volume configuration in deployment
# - Image pull error: Verify Docker images are available
```

### Certificate Verification Fails

```bash
# Check if certificates are mounted
kubectl exec -it deployment/severus-ai -c severus-ai -- ls -la /etc/certs/

# Expected files:
# tls.crt (certificate)
# tls.key (private key)
# ca.crt (CA bundle)

# Verify certificate is valid
kubectl exec -it deployment/severus-ai -c severus-ai -- \
  openssl x509 -in /etc/certs/tls.crt -text -noout
```

### Stress Test Fails

```bash
# Check stress-pod logs
kubectl logs job/stress-pod

# Common issues:
# - Certificate not mounted: Check volume mounts in stress-pod.yaml
# - Wrong certificate path: Verify environment variables
# - Target not ready: Check Severus AI pod is running
```

## Rollback

If you need to disable certificates:

```bash
# Option 1: Switch to permissive mode
helm upgrade severus-ai ./helm/severus-ai \
  --set certificates.verification.enforceMode=permissive

# Option 2: Disable certificates completely
helm upgrade severus-ai ./helm/severus-ai \
  --set certificates.enabled=false

# Option 3: Uninstall cert-manager (nuclear option)
kubectl delete -f https://github.com/cert-manager/cert-manager/releases/download/v1.14.0/cert-manager.yaml
```

## Production Deployment Checklist

- [ ] cert-manager installed and verified
- [ ] ClusterIssuer created and ready
- [ ] Certificates generated for all pods
- [ ] Certificate verification tested in permissive mode
- [ ] Metrics monitored for certificate failures
- [ ] Switched to strict mode
- [ ] Untrusted access blocked and verified
- [ ] Certificate rotation tested
- [ ] Monitoring and alerting configured
- [ ] Documentation updated

## Next Steps

1. **Monitor certificate expiration**: Set up alerts for certificates expiring in < 30 days
2. **Audit access logs**: Review certificate verification metrics regularly
3. **Add more trusted pods**: Create certificates for other services that need access
4. **Implement certificate rotation**: Test manual certificate renewal process
5. **Production hardening**: Switch to strict mode and monitor for failures

## References

- [Security Implementation Guide](documentation/SECURITY.md)
- [cert-manager Documentation](https://cert-manager.io/docs/)
- [Helm Chart Configuration](helm/severus-ai/values.yaml)
