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

        /* ================= DEPLOY ================= */

        stage('Deploy to Kubernetes (Ingress via Helm)') {
            steps {
                sh '''
                    set -euo pipefail
                    echo "☸️ Deploying Severus AI..."

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

                stage('Stress Pod Performance Test') {
                    steps {
                        sh '''
                            set +e
                            echo "🔥 Starting stress test job for Severus AI (NON-BLOCKING)"

                            JOB_NAME=stress-pod

                            # Clean up old job if exists (safe)
                            $KUBECTL_BIN delete job $JOB_NAME --ignore-not-found

                            echo "📦 Applying stress job manifest..."
                            $KUBECTL_BIN apply -f k8s/stress/stress-job.yaml

                            echo "⏳ Waiting for stress job to complete..."
                            $KUBECTL_BIN wait --for=condition=complete job/$JOB_NAME --timeout=120s \
                            || echo "⚠️ Stress job timeout (allowed)"

                            echo "📜 Stress job logs:"
                            $KUBECTL_BIN logs job/$JOB_NAME || echo "⚠️ No logs available"

                            echo "🧹 Cleaning up stress job..."
                            $KUBECTL_BIN delete job $JOB_NAME --ignore-not-found

                            echo "✅ Stress test stage finished"
                            exit 0
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
    }
}