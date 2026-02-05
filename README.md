# Severus AI

Severus AI is a production-ready, cloud-native personal AI assistant built with Streamlit and integrated with Ollama.

## 🛡️ Security First
This project features a robust security model including:
- **Mutual TLS (mTLS)** for internal pod-to-pod communication.
- **External HTTPS (TLS)** for secure browser access.
- **Automated Certificate Lifecycle** managed by `cert-manager`.
- **Nginx Sidecar Architecture** for high-performance security proxying.

## 🚀 Documentation
All technical documentation is located in the [documentation/](documentation/README.md) directory.

### Key Documents:
- [Application Architecture](documentation/01_Application_Architecture.md)
- [Security Implementation](documentation/SECURITY.md)
- [Networking & Ingress](documentation/07_Networking_Architecture.md)
- [Deployment Guide](documentation/DEPLOYMENT_GUIDE.md)
- [CI/CD Pipeline](documentation/02_CICD_Pipeline.md)
- [AI Debugger System](documentation/04_AI_Debugger.md)
- [Performance Evaluation](documentation/03_Performance_Evaluation.md)

## 🛠️ Quick Start
To deploy the full secure stack, please refer to the [Deployment Guide](documentation/DEPLOYMENT_GUIDE.md).

```bash
# Basic Helm Install
helm upgrade --install severus-ai helm/severus-ai
```

---
Author: Jujjavarapu Sujan Chowdary
