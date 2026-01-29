# Stress Testing Quick Reference

## Files Created

### Stress Pod
- `stress-pod/Dockerfile` - Container image with kubectl
- `stress-pod/stress_pod.sh` - Load testing script

### Helm Templates
- `helm/severus-ai/templates/rbac.yaml` - Permissions for stress pod
- `helm/severus-ai/templates/metrics-rbac.yaml` - Metrics access
- `helm/severus-ai/templates/hpa.yaml` - Auto-scaling config
- `helm/severus-ai/templates/stress-pod.yaml` - Stress test job

### Modified Files
- `helm/severus-ai/values.yaml` - Added stress config, resources, HPA
- `helm/severus-ai/templates/deployment.yaml` - Added resource limits
- `Jenkinsfile` - Added "Stress Test" stage

## Docker Image
```
sujanchow/stress-pod:latest
```

## Quick Commands

### Run Jenkins Pipeline
Just trigger a new build - stress test runs automatically!

### Manual Stress Test
```bash
# Deploy with stress test enabled
helm upgrade --install severus-ai helm/severus-ai \
  --set image.repository=sujanchow/serverus-ai \
  --set image.tag=v1 \
  --set stress.enabled=true

# Watch stress test
kubectl logs -f job/stress-pod

# Monitor HPA
kubectl get hpa severus-ai-hpa --watch
```

### Disable Stress Test
```bash
helm upgrade --install severus-ai helm/severus-ai \
  --set image.repository=sujanchow/serverus-ai \
  --set image.tag=v1 \
  --set stress.enabled=false
```

### Adjust Load
Edit `helm/severus-ai/values.yaml`:
```yaml
stress:
  args:
    totalRequests: 1000  # Increase load
    concurrency: 50      # More concurrent requests
```

## Configuration Reference

| Parameter | Default | Description |
|-----------|---------|-------------|
| `stress.enabled` | true | Enable/disable stress testing |
| `stress.args.totalRequests` | 500 | Requests per run |
| `stress.args.concurrency` | 20 | Concurrent requests |
| `stress.args.runs` | 5 | Number of runs |
| `stress.args.sleepSeconds` | 5 | Sleep between runs |
| `hpa.enabled` | true | Enable auto-scaling |
| `hpa.minReplicas` | 1 | Minimum pods |
| `hpa.maxReplicas` | 5 | Maximum pods |
| `hpa.cpu.averageUtilization` | 50 | CPU threshold % |
| `resources.requests.cpu` | 100m | CPU request |
| `resources.limits.cpu` | 500m | CPU limit |
| `resources.requests.memory` | 128Mi | Memory request |
| `resources.limits.memory` | 512Mi | Memory limit |

## Troubleshooting

### Check Stress Test Status
```bash
kubectl get job stress-pod
kubectl logs job/stress-pod
```

### Check HPA
```bash
kubectl get hpa
kubectl describe hpa severus-ai-hpa
```

### Check Pods
```bash
kubectl get pods -l app=severus-ai
kubectl top pods
```

### Delete Stress Job
```bash
kubectl delete job stress-pod
```
