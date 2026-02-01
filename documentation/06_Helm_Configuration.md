# Severus AI - Helm Configuration and Kubernetes Resources

## Table of Contents
1. [Overview](#overview)
2. [Helm Chart Structure](#helm-chart-structure)
3. [Deployment Configuration](#deployment-configuration)
4. [Service and RBAC](#service-and-rbac)
5. [Ingress Configuration](#ingress-configuration)
6. [ServiceMonitor](#servicemonitor)
7. [Values and Customization](#values-and-customization)

---

## Overview

Helm is used as the package manager for deploying Severus AI to Kubernetes. The chart includes:
- **Deployment**: Pod specification with probes and resource limits
- **Service**: ClusterIP service exposing ports 8501 (app) and 8000 (metrics)
- **Ingress**: Traefik-based HTTP routing
- **ServiceMonitor**: Prometheus metrics discovery
- **RBAC**: (Future) Role-Based Access Control

---

## Helm Chart Structure

```
helm/severus-ai/
├── Chart.yaml                 # Chart metadata
├── values.yaml                # Default configuration
└── templates/
    ├── deployment.yaml        # Pod deployment spec
    ├── service.yaml           # ClusterIP service
    ├── ingress.yaml           # HTTP ingress
    ├── servicemonitor.yaml    # Prometheus discovery
    └── stress-pod.yaml        # Performance test job (conditional)
```

---

## Deployment Configuration

### Full Template (`deployment.yaml`)

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "severus-ai.fullname" . }}
  labels:
    {{- include "severus-ai.labels" . | nindent 4 }}
spec:
  replicas: {{ .Values.replicaCount }}
  selector:
    matchLabels:
      {{- include "severus-ai.selectorLabels" . | nindent 6 }}
  template:
    metadata:
      labels:
        {{- include "severus-ai.selectorLabels" . | nindent 8 }}
    spec:
      containers:
      - name: severus-ai
        image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"
        imagePullPolicy: {{ .Values.image.pullPolicy }}
        ports:
          - name: http
            containerPort: 8501
            protocol: TCP
          - name: metrics
            containerPort: 8000
            protocol: TCP
        env:
          - name: OLLAMA_BASE_URL
            value: {{ .Values.ollama.baseUrl }}
          - name: prometheus_multiproc_dir
            value: /app/data/metrics
        livenessProbe:
          httpGet:
            path: /
            port: 8501
          initialDelaySeconds: 15
          periodSeconds: 20
        readinessProbe:
          httpGet:
            path: /
            port: 8501
          initialDelaySeconds: 5
          periodSeconds: 10
        resources:
          requests:
            cpu: {{ .Values.resources.requests.cpu }}
            memory: {{ .Values.resources.requests.memory }}
          limits:
            cpu: {{ .Values.resources.limits.cpu }}
            memory: {{ .Values.resources.limits.memory }}
        volumeMounts:
          - name: app-data
            mountPath: /app/data
      volumes:
        - name: app-data
          emptyDir: {}
```

### Key Features

#### 1. Health Probes

**Liveness Probe:**
```yaml
livenessProbe:
  httpGet:
    path: /
    port: 8501
  initialDelaySeconds: 15
  periodSeconds: 20
```

**Purpose:**
- Kubernetes restarts pod if liveness fails
- Prevents stuck containers from staying "Running"
- Critical for detecting application crashes

**Readiness Probe:**
```yaml
readinessProbe:
  httpGet:
    path: /
    port: 8501
  initialDelaySeconds: 5
  periodSeconds: 10
```

**Purpose:**
- Pod is marked "Ready" only if this passes
- Traffic is sent only to ready pods
- Prevents broken pods from receiving requests

#### 2. Resource Limits

```yaml
resources:
  requests:
    cpu: "250m"      # Minimum guaranteed
    memory: "512Mi"
  limits:
    cpu: "1000m"     # Maximum allowed
    memory: "2Gi"
```

**Benefits:**
- Prevents resource starvation
- Enables HPA (Horizontal Pod Autoscaler)
- Ensures predictable performance

---

## Service and RBAC  

### Service Configuration (`service.yaml`)

```yaml
apiVersion: v1
kind: Service
metadata:
  name: {{ include "severus-ai.fullname" . }}
  labels:
    {{- include "severus-ai.labels" . | nindent 4 }}
spec:
  type: ClusterIP
  ports:
    - port: 8501
      targetPort: http
      protocol: TCP
      name: http
    - port: 8000
      targetPort: metrics
      protocol: TCP
      name: metrics
  selector:
    {{- include "severus-ai.selectorLabels" . | nindent 4 }}
```

**Port Mapping:**
| Service Port | Target Port | Name | Purpose |
|--------------|-------------|------|---------|
| 8501 | 8501 (http) | http | Streamlit UI |
| 8000 | 8000 (metrics) | metrics | Prometheus metrics |

### RBAC (Future Enhancement)

**ServiceAccount:**
```yaml
apiVersion: v1
kind: ServiceAccount
metadata:
  name: severus-ai
```

**Role:**
```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: Role
metadata:
  name: severus-ai-role
rules:
  - apiGroups: [""]
    resources: ["secrets", "configmaps"]
    verbs: ["get", "list"]
```

**RoleBinding:**
```yaml
apiVersion: rbac.authorization.k8s.io/v1
kind: RoleBinding
metadata:
  name: severus-ai-binding
subjects:
  - kind: ServiceAccount
    name: severus-ai
roleRef:
  kind: Role
  name: severus-ai-role
  apiGroup: rbac.authorization.k8s.io
```

---

## Ingress Configuration

### Template (`ingress.yaml`)

```yaml
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {{ include "severus-ai.fullname" . }}
  annotations:
    kubernetes.io/ingress.class: traefik
spec:
  rules:
    - host: severus-ai.local
      http:
        paths:
          - path: /
            pathType: Prefix
            backend:
              service:
                name: {{ include "severus-ai.fullname" . }}
                port:
                  number: 8501
```

**How It Works:**
1. User visits `http://severus-ai.local`
2. Traefik ingress controller matches host header
3. Routes request to `severus-ai` service on port 8501
4. Service forwards to pod container port 8501

### Local Access Setup

**Add to `/etc/hosts`:**
```
127.0.0.1 severus-ai.local
127.0.0.1 grafana.local
127.0.0.1 prometheus.local
```

**Port Forwarding (for local cluster):**
```bash
kubectl -n kube-system port-forward svc/traefik 80:80
```

**Access URLs:**
- Application: http://severus-ai.local
- Grafana: http://grafana.local
- Prometheus: http://prometheus.local

---

## ServiceMonitor

### Template (`servicemonitor.yaml`)

```yaml
apiVersion: monitoring.coreos.com/v1
kind: ServiceMonitor
metadata:
  name: {{ include "severus-ai.fullname" . }}
  labels:
    {{- include "severus-ai.labels" . | nindent 4 }}
    release: kube-prometheus-stack  # REQUIRED
spec:
  selector:
    matchLabels:
      {{- include "severus-ai.selectorLabels" . | nindent 6 }}
  endpoints:
  - port: metrics
    interval: 15s
    path: /metrics
```

**Key Points:**
- `release: kube-prometheus-stack` label is CRITICAL for discovery
- Matches services with label `app=severus-ai`
- Scrape endpoint `metrics` (port 8000) every 15 seconds

---

## Values and Customization

### Default Values (`values.yaml`)

```yaml
replicaCount: 1

image:
  repository: sujanchow/serverus-ai
  tag: v1
  pullPolicy: IfNotPresent

service:
  type: ClusterIP
  port: 8501
  metricsPort: 8000

ingress:
  enabled: true
  className: traefik
  hosts:
    - host: severus-ai.local
      paths:
        - path: /
          pathType: Prefix

resources:
  requests:
    cpu: "250m"
    memory: "512Mi"
  limits:
    cpu: "1000m"
    memory: "2Gi"

ollama:
  baseUrl: "http://host.docker.internal:11434"

stress:
  enabled: false  # Only for performance testing
```

### Customization Examples

**1. Change Replica Count:**
```bash
helm upgrade severus-ai ./helm/severus-ai --set replicaCount=3
```

**2. Use Different Image:**
```bash
helm upgrade severus-ai ./helm/severus-ai \
  --set image.repository=myrepo/severus-ai \
  --set image.tag=v2.0
```

**3. Increase Resources:**
```bash
helm upgrade severus-ai ./helm/severus-ai \
  --set resources.limits.cpu=2000m \
  --set resources.limits.memory=4Gi
```

**4. Enable Stress Test:**
```bash
helm upgrade severus-ai ./helm/severus-ai \
  --set stress.enabled=true
```

---

## Summary

The Helm chart provides:
- ✅ **Declarative** infrastructure as code
- ✅ **Reproducible** deployments
- ✅ **Health probes** for reliability
- ✅ **Resource limits** for stability
- ✅ **Ingress** for HTTP access
- ✅ **ServiceMonitor** for observability
- ✅ **Customization** via values.yaml

This configuration ensures **production-ready**, **scalable**, and **observable** deployments of Severus AI.
