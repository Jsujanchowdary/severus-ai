pipeline {
    agent any

    environment {
        IMAGE_NAME = "sujanchow/serverus-ai"
        IMAGE_TAG  = "v1"

        APP_PORT = "8505"

        DOCKER_BIN     = "/Applications/Docker.app/Contents/Resources/bin/docker"
        DOCKER_CONTEXT = "desktop-linux"

        // Ensure Docker Desktop + credential helper are visible to Jenkins
        PATH = "/Applications/Docker.app/Contents/Resources/bin:/usr/local/bin:/usr/bin:/bin:/usr/sbin:/sbin"

        PYTHON_BIN  = "/opt/homebrew/bin/python3"
        HELM_BIN    = "/opt/homebrew/bin/helm"
        KUBECTL_BIN = "/Applications/Docker.app/Contents/Resources/bin/kubectl"
    }

    stages {

        stage('Checkout') {
            steps {
                checkout scm
            }
        }

        /* ================= OBSERVABILITY SETUP ================= */

        stage('Setup Monitoring Requirements') {
            steps {
                sh '''
                    set -euo pipefail
                    echo "📥 Adding Prometheus Helm repository..."
                    $HELM_BIN repo add prometheus-community https://prometheus-community.github.io/helm-charts
                    $HELM_BIN repo update
                '''
            }
        }

        stage('Deploy Monitoring Stack') {
            steps {
                sh '''
                    set -euo pipefail
                    echo "📊 Deploying Prometheus and Grafana stack..."
                    $HELM_BIN upgrade --install kube-prometheus-stack prometheus-community/kube-prometheus-stack \
                        --namespace default \
                        --set grafana.adminPassword=admin123 \
                        --set prometheus.prometheusSpec.serviceMonitorSelectorNilUsesHelmValues=false
                '''
            }
        }

        stage('Configure Application Monitoring') {
            steps {
                sh '''
                    set -euo pipefail
                    echo "🔧 Configuring application metrics discovery..."
                    
                    # Ensure ServiceMonitor is correctly labeled for Prometheus discovery
                    # Using --overwrite to ensure the label is applied even if it's there
                    $KUBECTL_BIN label servicemonitor severus-ai release=kube-prometheus-stack --overwrite || echo "⚠️ ServiceMonitor not found yet, will be applied during deployment"

                    echo "📥 Importing Grafana Dashboard..."
                    # Wait for Grafana to be ready
                    sleep 10
                    
                    # Import dashboard via API using curl (more reliable in Jenkins)
                    # We wrap the JSON in the format Grafana expects
                    DASHBOARD_PATH="config/grafana-dashboard-application.json"
                    
                    if [ -f "$DASHBOARD_PATH" ]; then
                        echo "Found dashboard file. Importing..."
                        curl -u admin:admin123 -X POST \
                            -H "Content-Type: application/json" \
                            -d @$DASHBOARD_PATH \
                            http://kube-prometheus-stack-grafana.default.svc.cluster.local/api/dashboards/db || echo "⚠️ Failed to import dashboard via internal URL, trying local port-forward fallback if in local mode"
                    else
                        echo "❌ Dashboard file not found at $DASHBOARD_PATH"
                    fi
                '''
            }
        }

        /* ================= BUILD ================= */

        stage('Application Build') {
            steps {
                sh '''
                    set -euo pipefail

                    echo "🔧 Installing dependencies (venv)..."

                    $PYTHON_BIN -m venv venv
                    . venv/bin/activate

                    echo "Python in use: $(which python)"
                    echo "Pip in use: $(which pip)"

                    pip install --upgrade pip
                    pip install -r requirements.txt
                '''
            }
        }

        /* ================= RUN (SMOKE START) ================= */

        stage('Run (Smoke Start)') {
            steps {
                sh '''
                    set -euo pipefail

                    echo "🚀 Starting application for smoke test..."

                    . venv/bin/activate

                    if [ -z "$VIRTUAL_ENV" ]; then
                      echo "❌ Virtualenv not active"
                      exit 1
                    fi

                    which python
                    which streamlit

                    nohup streamlit run app.py \
                      --server.port=${APP_PORT} \
                      --server.headless=true \
                      > app.log 2>&1 &

                    sleep 20
                '''
            }
        }

        /* ================= TEST ================= */

        stage('Test (Smoke Test)') {
            steps {
                sh '''
                    set -euo pipefail

                    echo "🧪 Running smoke test..."

                    echo "---- App logs ----"
                    tail -n 30 app.log || true
                    echo "------------------"

                    curl --retry 5 --retry-delay 2 --fail http://127.0.0.1:${APP_PORT}

                    echo "✅ Smoke test passed"
                '''
            }
        }

        /* ================= DOCKER LOGIN ================= */

        stage('Docker Login') {
            steps {
                withCredentials([usernamePassword(
                    credentialsId: 'dockerhub-creds',
                    usernameVariable: 'DOCKER_USER',
                    passwordVariable: 'DOCKER_PASS'
                )]) {
                    sh '''
                        echo "🔐 Logging into Docker Hub..."
                        echo "$DOCKER_PASS" | \
                        $DOCKER_BIN --context ${DOCKER_CONTEXT} login \
                          -u "$DOCKER_USER" --password-stdin
                    '''
                }
            }
        }

        /* ================= DOCKER BUILD ================= */

        stage('Docker Build Image') {
            steps {
                sh '''
                    set -euo pipefail
                    echo "🐳 Building Docker image..."
                    $DOCKER_BIN --context ${DOCKER_CONTEXT} build \
                      -t ${IMAGE_NAME}:${IMAGE_TAG} .
                '''
            }
        }

        /* ================= SECURITY ================= */

        stage('Trivy Security Scan') {
            steps {
                sh '''
                    set -euo pipefail
                    echo "🔐 Running Trivy scan..."

                    DOCKER_SOCK=$(ls ~/.docker/run/docker.sock 2>/dev/null || echo /var/run/docker.sock)

                    $DOCKER_BIN --context ${DOCKER_CONTEXT} run --rm \
                      -v $DOCKER_SOCK:/var/run/docker.sock \
                      aquasec/trivy:latest image \
                      --severity CRITICAL,HIGH \
                      --exit-code 0 \
                      ${IMAGE_NAME}:${IMAGE_TAG} | tee trivy-report.txt
                '''
            }
            post {
                always {
                    archiveArtifacts artifacts: 'trivy-report.txt', fingerprint: true
                }
            }
        }

        /* ================= PUSH ================= */

        stage('Docker Push Image') {
            steps {
                sh '''
                    set -e

                    echo "📦 Pushing Docker image (with retry)..."

                    for i in 1 2 3; do
                    echo "👉 Push attempt $i..."
                    if $DOCKER_BIN --context ${DOCKER_CONTEXT} push ${IMAGE_NAME}:${IMAGE_TAG}; then
                        echo "✅ Docker push succeeded"
                        exit 0
                    fi
                    echo "⚠️ Push failed, retrying in 10s..."
                    sleep 10
                    done

                    echo "❌ Docker push failed after retries"
                    exit 1
                '''
            }
        }

        /* ================= STRESS POD IMAGE BUILD ================= */
        /* Builds and pushes stress-pod Docker image automatically */

        stage('Build Stress Pod Image') {
            steps {
                sh '''
                    set -euo pipefail
                    echo "🔨 Building stress-pod Docker image..."
                    
                    cd stress-pod
                    $DOCKER_BIN --context ${DOCKER_CONTEXT} build \
                      -t sujanchow/stress-pod:${IMAGE_TAG} \
                      -t sujanchow/stress-pod:latest .
                    
                    echo "✅ Stress-pod image built successfully"
                '''
            }
        }

        stage('Push Stress Pod Image') {
            steps {
                sh '''
                    set -euo pipefail
                    echo "📤 Pushing stress-pod image to registry..."
                    
                    $DOCKER_BIN --context ${DOCKER_CONTEXT} push sujanchow/stress-pod:${IMAGE_TAG}
                    $DOCKER_BIN --context ${DOCKER_CONTEXT} push sujanchow/stress-pod:latest
                    
                    echo "✅ Stress-pod image pushed successfully"
                '''
            }
        }

        /* ================= DEPLOY ================= */

        stage('Deploy to Kubernetes (Ingress via Helm)') {
            steps {
                sh '''
                    set -euo pipefail
                    echo "☸️ Deploying Severus AI..."
                    
                    # Delete old stress-pod job if it exists (Jobs are immutable)
                    $KUBECTL_BIN delete job stress-pod --ignore-not-found=true
                    
                    $HELM_BIN upgrade --install severus-ai helm/severus-ai \
                      --set image.repository=${IMAGE_NAME} \
                      --set image.tag=${IMAGE_TAG}
                '''
            }
        }

        /* ================= POST-DEPLOY TESTS ================= */

        stage('Post-Deployment Tests') {
            parallel {

                stage('Ingress Reachability Test') {
                    steps {
                        sh '''
                        set -euo pipefail

                        echo "🌐 Testing Ingress reachability via Traefik (port 8081)..."

                        kubectl -n kube-system port-forward svc/traefik 8081:80 >/tmp/traefik.log 2>&1 &

                        sleep 6

                        curl --retry 5 --retry-delay 2 --fail \
                            -H "Host: severus-ai.local" \
                            http://127.0.0.1:8081

                        echo "✅ Ingress reachable via Traefik"
                        '''
                    }
                }

                stage('Ollama Connectivity Test') {
                    steps {
                        sh '''
                            set +e
                            echo "🧠 Testing Ollama connectivity (NON-BLOCKING)"

                            POD=$($KUBECTL_BIN get pods -l app=severus-ai \
                            --field-selector=status.phase=Running \
                            -o jsonpath="{.items[0].metadata.name}")

                            if [ -z "$POD" ]; then
                            echo "⚠️ No running pod found (rolling deploy). Skipping."
                            exit 0
                            fi

                            echo "Using pod: $POD"

                            $KUBECTL_BIN exec "$POD" -- \
                            curl -s --max-time 5 http://host.docker.internal:11434/api/tags \
                            && echo "✅ Ollama reachable" \
                            || echo "⚠️ Ollama not reachable (allowed)"

                            exit 0
                        '''
                    }
                }

                stage('Kubernetes Health Test') {
                    steps {
                        sh '''
                            echo "🩺 Checking Kubernetes health..."
                            $KUBECTL_BIN rollout status deployment/severus-ai --timeout=120s
                            $KUBECTL_BIN get pods -l app=severus-ai
                        '''
                    }
                }

                stage('Log Sanity Test') {
                    steps {
                        sh '''
                            echo "📜 Checking logs..."
                            $KUBECTL_BIN logs deployment/severus-ai | tail -n 50
                        '''
                    }
                }

                stage('K3s Version Validation') {
                    steps {
                        sh '''
                            mkdir -p k3s-validation-logs

                            for VERSION in v1.26 v1.27 v1.28 v1.29 v1.30 v1.31 v1.32 v1.33 v1.34 v1.35; do
                              $HELM_BIN upgrade --install severus-ai helm/severus-ai \
                                --dry-run --debug \
                                --set image.repository=${IMAGE_NAME} \
                                --set image.tag=${IMAGE_TAG} \
                                --set global.k3sVersion=$VERSION \
                                > k3s-validation-logs/k3s-$VERSION.log
                            done
                        '''
                    }
                    post {
                        always {
                            archiveArtifacts artifacts: 'k3s-validation-logs/*.log', fingerprint: true
                        }
                    }
                }
            }
        }

        /* ================= STRESS TEST ================= */

        stage('Stress Test') {
            steps {
                sh '''
                    set -euo pipefail
                    
                    echo "🔥 Starting Stress Test..."
                    
                    # Delete previous stress test job if exists
                    $KUBECTL_BIN delete job stress-pod --ignore-not-found=true
                    
                    # Wait for job deletion
                    sleep 5
                    
                    # Deploy stress test (this creates the job)
                    echo "Deploying stress test job..."
                    $HELM_BIN upgrade --install severus-ai helm/severus-ai \
                      --set image.repository=${IMAGE_NAME} \
                      --set image.tag=${IMAGE_TAG} \
                      --set stress.enabled=true
                    
                    # Wait for job to start
                    echo "Waiting for stress test job to start..."
                    sleep 10
                    
                    # Monitor job status
                    echo "Monitoring stress test progress..."
                    for i in {1..60}; do
                      STATUS=$($KUBECTL_BIN get job stress-pod -o jsonpath='{.status.conditions[?(@.type=="Complete")].status}' 2>/dev/null || echo "")
                      FAILED=$($KUBECTL_BIN get job stress-pod -o jsonpath='{.status.conditions[?(@.type=="Failed")].status}' 2>/dev/null || echo "")
                      
                      if [ "$STATUS" = "True" ]; then
                        echo "✅ Stress test completed successfully"
                        break
                      elif [ "$FAILED" = "True" ]; then
                        echo "❌ Stress test failed"
                        $KUBECTL_BIN logs job/stress-pod || true
                        exit 1
                      fi
                      
                      echo "Stress test still running... ($i/60)"
                      sleep 10
                    done
                    
                    # Get final logs
                    echo ""
                    echo "=============================================="
                    echo "STRESS TEST LOGS"
                    echo "=============================================="
                    $KUBECTL_BIN logs job/stress-pod || echo "Could not retrieve logs"
                    
                    # Check HPA status
                    echo ""
                    echo "=============================================="
                    echo "HPA STATUS"
                    echo "=============================================="
                    $KUBECTL_BIN get hpa severus-ai-hpa || echo "HPA not found"
                    
                    # Check pod scaling
                    echo ""
                    echo "=============================================="
                    echo "POD STATUS"
                    echo "=============================================="
                    $KUBECTL_BIN get pods -l app=severus-ai
                    
                    echo ""
                    echo "✅ Stress test stage completed"
                '''
            }
            post {
                always {
                    sh '''
                        # Archive stress test logs
                        $KUBECTL_BIN logs job/stress-pod > stress-test-logs.txt 2>&1 || echo "No logs available" > stress-test-logs.txt
                        
                        # Get HPA events
                        $KUBECTL_BIN describe hpa severus-ai-hpa > hpa-events.txt 2>&1 || echo "No HPA found" > hpa-events.txt
                    '''
                    archiveArtifacts artifacts: 'stress-test-logs.txt,hpa-events.txt', fingerprint: true
                }
            }
        }
    }
}