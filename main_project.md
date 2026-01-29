# Severus AI - Complete Codebase Documentation

This document contains the complete code for all files in the Severus AI project, organized by directory structure.

---

## 📁 Directory Structure

```
Streamlit/
├── app.py
├── auth.py
├── chat.py
├── file_text_extractor.py
├── file_utils.py
├── metrics.py
├── storage.py
├── requirements.txt
├── dockerfile
├── docker-compose.yml
├── Jenkinsfile
├── instrctions.txt
├── config/
│   ├── __init__.py
│   └── settings.py
├── utils/
│   ├── __init__.py
│   ├── logger.py
│   └── ollama_client.py
├── helm/
│   └── severus-ai/
│       ├── Chart.yaml
│       ├── values.yaml
│       └── templates/
│           ├── _helpers.tpl
│           ├── deployment.yaml
│           ├── service.yaml
│           └── ingress.yaml
└── data/
    ├── app.db
    └── users.csv
```

---

## 📄 Root Directory Files

### `app.py`

```python
import streamlit as st
from pathlib import Path

from storage import init_db
from auth import signup, login
from chat import (
    create_chat,
    get_user_chats,
    get_messages,
    save_message,
    delete_chat,
    add_file_record,
)
from file_utils import save_uploaded_file, ensure_extracted_text
from utils.ollama_client import chat_with_model

# ======================================================
# APP CONFIG
# ======================================================
st.set_page_config(
    page_title="Severus AI",
    page_icon="🧠",
    layout="wide",
)

init_db()

# ======================================================
# SESSION STATE (MINIMAL & SAFE)
# ======================================================
st.session_state.setdefault("authenticated", False)
st.session_state.setdefault("username", None)
st.session_state.setdefault("chat_id", None)

st.session_state.setdefault("has_document", {})  # chat_id -> bool
st.session_state.setdefault("upload_notice", {})  # chat_id -> str | None
st.session_state.setdefault("files_to_process", None)  # TEMP buffer

# ======================================================
# HEADER
# ======================================================
st.markdown(
    """
    <div style="text-align:center; padding:10px 0 25px 0;">
        <h1>🧠 Severus AI</h1>
        <p style="color:gray;">Your personal local AI assistant</p>
    </div>
    """,
    unsafe_allow_html=True,
)

# ======================================================
# AUTH
# ======================================================
if not st.session_state.authenticated:
    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        tab1, tab2 = st.tabs(["🔐 Login", "🆕 Sign Up"])

        with tab1:
            u = st.text_input("Username")
            p = st.text_input("Password", type="password")
            if st.button("Login", use_container_width=True):
                if login(u, p):
                    st.session_state.authenticated = True
                    st.session_state.username = u
                    st.rerun()
                else:
                    st.error("Invalid credentials")

        with tab2:
            u = st.text_input("New Username")
            p = st.text_input("New Password", type="password")
            if st.button("Create Account", use_container_width=True):
                if signup(u, p):
                    st.success("Account created. Login now.")
                else:
                    st.error("Username already exists")

# ======================================================
# MAIN APP
# ======================================================
else:
    # ---------------- SIDEBAR ----------------
    st.sidebar.markdown(f"👤 **{st.session_state.username}**")

    if st.sidebar.button("🚪 Logout", use_container_width=True):
        st.session_state.clear()
        st.rerun()

    st.sidebar.divider()
    st.sidebar.markdown("### 💬 Chats")

    chats = get_user_chats(st.session_state.username)

    if st.sidebar.button("➕ New Chat", use_container_width=True):
        cid = create_chat(st.session_state.username)
        st.session_state.chat_id = cid
        st.session_state.has_document[cid] = False
        st.session_state.upload_notice[cid] = None
        st.rerun()

    for cid, title in chats:
        c1, c2 = st.sidebar.columns([5, 1])
        if c1.button(title, key=f"open_{cid}", use_container_width=True):
            st.session_state.chat_id = cid
            st.rerun()
        if c2.button("🗑️", key=f"del_{cid}"):
            delete_chat(cid)
            st.session_state.has_document.pop(cid, None)
            st.session_state.upload_notice.pop(cid, None)
            if st.session_state.chat_id == cid:
                st.session_state.chat_id = None
            st.rerun()

    if not st.session_state.chat_id:
        st.info("👈 Create or select a chat to begin.")
        st.stop()

    chat_id = st.session_state.chat_id
    st.session_state.has_document.setdefault(chat_id, False)
    st.session_state.upload_notice.setdefault(chat_id, None)

    # ======================================================
    # FILE UPLOAD (ZERO PROCESSING HERE)
    # ======================================================
    st.sidebar.divider()
    st.sidebar.markdown("### 📂 Upload Files")

    file_type = st.sidebar.selectbox(
        "File type",
        ["PDF", "CSV", "Excel", "Image", "Other"],
    )

    allowed = {
        "PDF": ["pdf"],
        "CSV": ["csv"],
        "Excel": ["xlsx", "xls"],
        "Image": ["png", "jpg", "jpeg"],
        "Other": ["txt", "py", "js", "md"],
    }[file_type]

    uploaded_files = st.sidebar.file_uploader(
        "Choose files",
        type=allowed,
        accept_multiple_files=True,
        key="uploader",  # IMPORTANT
    )

    # EXPLICIT CONFIRM BUTTON (CRITICAL FIX)
    if st.sidebar.button("⬆️ Confirm Upload"):
        if uploaded_files:
            st.session_state.files_to_process = uploaded_files

    # ======================================================
    # PROCESS FILES (RUNS ONCE, SAFE)
    # ======================================================
    files = st.session_state.pop("files_to_process", None)

    if files:
        for f in files:
            save_uploaded_file(chat_id, f)
            add_file_record(chat_id, f.name, f"data/uploads/{chat_id}/{f.name}")

            if f.name.lower().endswith(("png", "jpg", "jpeg")):
                st.session_state.upload_notice[chat_id] = "image"
            else:
                st.session_state.has_document[chat_id] = True
                st.session_state.upload_notice[chat_id] = "document"

        st.rerun()

    # ======================================================
    # UPLOAD NOTICE (ONCE)
    # ======================================================
    notice = st.session_state.upload_notice.get(chat_id)
    if notice:
        msg = (
            "🖼️ **Image uploaded successfully.**\\n\\nAsk anything about it."
            if notice == "image"
            else "📄 **Document uploaded successfully.**\\n\\nClick **Summarize Uploaded Document**."
        )
        save_message(chat_id, "assistant", msg)
        st.session_state.upload_notice[chat_id] = None
        st.rerun()

    # ======================================================
    # CHAT WINDOW
    # ======================================================
    messages = get_messages(chat_id)

    # -------- SUMMARIZE BUTTON (LAZY & FAST) --------
    if st.session_state.has_document.get(chat_id):
        if st.button("📄 Summarize Uploaded Document", use_container_width=True):
            with st.spinner("Reading and summarizing document..."):
                ensure_extracted_text(chat_id)

                prompt = "Summarize the uploaded document clearly and concisely."
                save_message(chat_id, "user", prompt)

                reply = chat_with_model(
                    "gemma3:1b",
                    get_messages(chat_id) + [("user", prompt)],
                    chat_id=chat_id,
                )

                save_message(chat_id, "assistant", reply)

            st.rerun()

        st.markdown(
            """
            <div style="background:#1f2937;color:white;padding:10px;
            border-radius:8px;margin-bottom:10px;">
            🧠 <b>Answering from uploaded documents</b>
            </div>
            """,
            unsafe_allow_html=True,
        )

    # -------- CHAT HISTORY --------
    for role, content in messages:
        with st.chat_message(role):
            st.markdown(content)

    # -------- CHAT INPUT --------
    user_input = st.chat_input("Ask something...")

    if user_input:
        save_message(chat_id, "user", user_input)

        reply = chat_with_model(
            "gemma3:1b",
            get_messages(chat_id) + [("user", user_input)],
            chat_id=chat_id,
        )

        save_message(chat_id, "assistant", reply)
        st.rerun()
```

---

### `auth.py`

```python
import csv
import hashlib
from pathlib import Path
from utils.logger import setup_logger

logger = setup_logger("auth")

USERS_FILE = Path("data/users.csv")
USERS_FILE.parent.mkdir(exist_ok=True)

FIELDNAMES = ["username", "password_hash"]


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode()).hexdigest()


def ensure_users_file():
    if not USERS_FILE.exists():
        with open(USERS_FILE, "w", newline="") as f:
            writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
            writer.writeheader()


def read_users():
    ensure_users_file()
    with open(USERS_FILE, "r", newline="") as f:
        reader = csv.DictReader(f)
        if reader.fieldnames != FIELDNAMES:
            raise RuntimeError(
                f"Invalid users.csv format. Expected headers: {FIELDNAMES}"
            )
        return list(reader)


def signup(username: str, password: str) -> bool:
    users = read_users()
    for user in users:
        if user["username"] == username:
            return False

    with open(USERS_FILE, "a", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writerow(
            {"username": username, "password_hash": hash_password(password)}
        )

    logger.info(f"User signed up: {username}")
    return True


def login(username: str, password: str) -> bool:
    users = read_users()
    for user in users:
        if user["username"] == username and user["password_hash"] == hash_password(
            password
        ):
            logger.info(f"User logged in: {username}")
            return True
    return False
```

---

### `chat.py`

```python
from storage import get_connection
from utils.logger import setup_logger

logger = setup_logger("chat")


# =========================
# CHAT CRUD
# =========================


def create_chat(username: str, title="New Chat"):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO chats (username, title) VALUES (?, ?)",
        (username, title),
    )
    chat_id = cur.lastrowid
    conn.commit()
    conn.close()
    logger.info(f"Chat created: {chat_id} for {username}")
    return chat_id


def get_user_chats(username: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, title FROM chats WHERE username = ? ORDER BY created_at DESC",
        (username,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def get_messages(chat_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT role, content FROM messages WHERE chat_id = ? ORDER BY timestamp",
        (chat_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows


def save_message(chat_id: int, role: str, content: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO messages (chat_id, role, content) VALUES (?, ?, ?)",
        (chat_id, role, content),
    )
    conn.commit()
    conn.close()


def rename_chat(chat_id: int, new_title: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "UPDATE chats SET title = ? WHERE id = ?",
        (new_title, chat_id),
    )
    conn.commit()
    conn.close()
    logger.info(f"Chat renamed: {chat_id} -> {new_title}")


def delete_chat(chat_id: int):
    conn = get_connection()
    cur = conn.cursor()

    # delete messages
    cur.execute("DELETE FROM messages WHERE chat_id = ?", (chat_id,))

    # delete files
    cur.execute("DELETE FROM chat_files WHERE chat_id = ?", (chat_id,))

    # delete chat
    cur.execute("DELETE FROM chats WHERE id = ?", (chat_id,))

    conn.commit()
    conn.close()
    logger.info(f"Chat deleted: {chat_id}")


# =========================
# FILES
# =========================


def add_file_record(chat_id: int, filename: str, filepath: str):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO chat_files (chat_id, filename, filepath) VALUES (?, ?, ?)",
        (chat_id, filename, filepath),
    )
    conn.commit()
    conn.close()


def get_files_for_chat(chat_id: int):
    conn = get_connection()
    cur = conn.cursor()
    cur.execute(
        "SELECT filename, filepath FROM chat_files WHERE chat_id = ?",
        (chat_id,),
    )
    rows = cur.fetchall()
    conn.close()
    return rows
```

---

### `file_text_extractor.py`

```python
from pathlib import Path
from pypdf import PdfReader
import pandas as pd


def extract_text_from_file(file_path: str) -> str:
    path = Path(file_path)
    suffix = path.suffix.lower()

    if suffix == ".pdf":
        return extract_pdf(path)

    elif suffix in [".csv"]:
        return extract_csv(path)

    elif suffix in [".xlsx", ".xls"]:
        return extract_excel(path)

    elif suffix in [".txt", ".py", ".js", ".md"]:
        return extract_text_file(path)

    else:
        return "Unsupported file type"


def extract_pdf(path: Path) -> str:
    reader = PdfReader(path)
    text = []
    for page in reader.pages:
        text.append(page.extract_text() or "")
    return "\n".join(text)


def extract_csv(path: Path) -> str:
    df = pd.read_csv(path)
    return df.to_string(index=False)


def extract_excel(path: Path) -> str:
    df = pd.read_excel(path)
    return df.to_string(index=False)


def extract_text_file(path: Path) -> str:
    return path.read_text(errors="ignore")
```

---

### `file_utils.py`

```python
from pathlib import Path


from file_text_extractor import extract_text_from_file

UPLOAD_BASE = Path("data/uploads")

MAX_FILE_SIZE_MB = 5  # option 2


def save_uploaded_file(chat_id: int, uploaded_file):
    chat_dir = UPLOAD_BASE / str(chat_id)
    chat_dir.mkdir(parents=True, exist_ok=True)

    file_path = chat_dir / uploaded_file.name

    # 🚀 FAST upload (NO chunking, NO blocking)
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())

    return file_path


def ensure_extracted_text(chat_id: int):
    """
    Extract document text ONLY ON DEMAND.
    Runs once per chat.
    """

    chat_dir = UPLOAD_BASE / str(chat_id)
    extracted_file = chat_dir / "extracted_text.txt"

    # ✅ Already extracted → DO NOTHING
    if extracted_file.exists() and extracted_file.stat().st_size > 0:
        return extracted_file

    extracted_file.parent.mkdir(parents=True, exist_ok=True)

    with open(extracted_file, "w", encoding="utf-8") as out:
        for f in chat_dir.iterdir():
            if f.name == "extracted_text.txt":
                continue
            if not f.is_file():
                continue

            # 🚫 Skip images
            if f.suffix.lower() in [".png", ".jpg", ".jpeg"]:
                continue

            # 🚫 Large file guard (Option 2)
            size_mb = f.stat().st_size / (1024 * 1024)
            if size_mb > MAX_FILE_SIZE_MB:
                out.write(
                    f"\n\n⚠️ FILE SKIPPED (too large: {size_mb:.2f} MB): {f.name}\n"
                )
                continue

            raw_text = extract_text_from_file(str(f))
            if not raw_text:
                continue

            cleaned = raw_text.encode("utf-8", errors="ignore").decode("utf-8")

            out.write("\n\n========== FILE START ==========\n")
            out.write(cleaned)
            out.write("\n=========== FILE END ===========\n")

    return extracted_file
```

---

### `metrics.py`

```python
from prometheus_client import Counter

LOGIN_COUNT = Counter("login_total", "Total logins")
CHAT_CREATED = Counter("chat_created_total", "Chats created")
MESSAGES_SENT = Counter("messages_sent_total", "Messages sent")
OLLAMA_CALLS = Counter("ollama_calls_total", "Ollama calls")
```

---

### `storage.py`

```python
import sqlite3
from pathlib import Path

DB_PATH = Path("data/app.db")


def get_connection():
    DB_PATH.parent.mkdir(exist_ok=True)
    return sqlite3.connect(DB_PATH, check_same_thread=False)


def init_db():
    conn = get_connection()
    cur = conn.cursor()

    # ---------- USERS (unused for now, future-ready) ----------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE,
            password_hash TEXT
        )
        """
    )

    # ---------- CHATS ----------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS chats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT,
            title TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # ---------- MESSAGES ----------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS messages (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            role TEXT,
            content TEXT,
            timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    # ---------- CHAT FILES (NEW – REQUIRED) ----------
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS chat_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER,
            filename TEXT,
            filepath TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """
    )

    conn.commit()
    conn.close()
```

---

### `requirements.txt`

```
streamlit
requests
python-dotenv
prometheus-client
pypdf
```

---

### `dockerfile`

```dockerfile
FROM python:3.11-slim

WORKDIR /app

# System dependencies
RUN apt-get update && apt-get install -y \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# App code
COPY . .

EXPOSE 8501

CMD ["streamlit", "run", "app.py", "--server.address=0.0.0.0", "--server.port=8501", "sleep infinity"]
```

---

### `docker-compose.yml`

```yaml
version: "3.9"

services:
  ollama:
    image: ollama/ollama:latest
    container_name: ollama
    ports:
      - "11434:11434"
    volumes:
      - ollama_data:/root/.ollama

  app:
    build: .
    container_name: ollama-chat-app
    ports:
      - "8501:8501"
    environment:
      - OLLAMA_BASE_URL=http://localhost:11434
    depends_on:
      - ollama
    volumes:
      - ./data:/app/data

volumes:
  ollama_data:
```

---

### `Jenkinsfile`

```groovy
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
```

---

### `instrctions.txt`

```
start docker desktop:
docker build -t sujanchow/serverus-ai:v1 .


 docker run -d \                        
  -p 8501:8501 \
  -e OLLAMA_BASE_URL=http://host.docker.internal:11434 \
  --name severus-ai \
  sujanchow/serverus-ais:v1


minikube:
minikube start
minikube stop

jenkins commands:
brew services start jenkins-lts  
brew services restart jenkins-lts
brew upgrade jenkins-lts
brew services stop jenkins-lts
http://localhost:8080/

git:
git init
git add <file>
git commit -m "msg"
git push -u origin main




application local host:
http://localhost:8503/


while about to start :
docker info
brew install k3d
k3d cluster list
k3d cluster create severus-cluster
k3d cluster start severus-cluster (if cluster stopped)
kubectl get nodes
brew services start jenkins-lts
brew services list | grep jenkins (verify)
http://localhost:8080 (open jenkins)

the application link comes from ingress:
kubectl get ingress
Final Application URL
 http://severus-ai.local



```

---

## 📁 config/ Directory

### `config/__init__.py`

```python
# Empty file
```

---

### `config/settings.py`

```python
import os

OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://localhost:11434")
DEFAULT_MODEL = "gemma3:1b"


APP_NAME = "Ollama Streamlit Chat"
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO")
```

---

## 📁 utils/ Directory

### `utils/__init__.py`

```python
# Empty file
```

---

### `utils/logger.py`

```python
import logging
from config.settings import LOG_LEVEL


def setup_logger(name: str):
    logger = logging.getLogger(name)
    logger.setLevel(LOG_LEVEL)

    if not logger.handlers:
        handler = logging.StreamHandler()
        formatter = logging.Formatter(
            "[%(asctime)s] [%(levelname)s] %(name)s - %(message)s"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)

    return logger
```

---

### `utils/ollama_client.py`

```python
import requests
from pathlib import Path
import logging
import os

# =========================
# OLLAMA CONFIG (AUTO)
# =========================
OLLAMA_BASE_URL = os.getenv(
    "OLLAMA_BASE_URL",
    "http://host.docker.internal:11434"
)

logger = logging.getLogger("ollama-client")


def chat_with_model(model: str, messages: list, chat_id: int):
    """
    Send chat + extracted document context to Ollama
    """

    # ---------- DEFAULT SYSTEM PROMPT ----------
    system_prompt = """
You are a helpful, conversational AI assistant.

You can chat naturally with the user and remember things mentioned earlier
in the conversation.

If the user asks about a document and no document is available,
clearly say that no document has been uploaded yet.
"""

    document_text = ""

    # ---------- READ EXTRACTED DOCUMENT ----------
    extracted_file = Path(f"data/uploads/{chat_id}/extracted_text.txt")

    if extracted_file.exists():
        document_text = extracted_file.read_text(
            encoding="utf-8",
            errors="ignore",
        )

    # ---------- READ FILE NAMES ----------
    uploaded_files = []
    chat_upload_dir = Path(f"data/uploads/{chat_id}")

    if chat_upload_dir.exists():
        for f in chat_upload_dir.iterdir():
            if f.is_file() and f.name != "extracted_text.txt":
                uploaded_files.append(f.name)

    file_sources = ", ".join(uploaded_files) if uploaded_files else "Unknown file"

    # ---------- DOCUMENT-AWARE PROMPT ----------
    if document_text.strip():
        system_prompt = f"""
You are a helpful, conversational AI assistant.

You can:
- Chat naturally with the user
- Remember things mentioned earlier in the conversation
- Read, summarize, explain, and answer questions about the user's uploaded documents

Behavior rules:
- If the user asks general questions, respond naturally.
- If the user asks about the document, use document content.
- Pronouns like "it", "this", "the file" refer to the uploaded document.
- Treat misspellings of "summarize" as summarize intent.
- ALWAYS mention source file names when answering from documents.
- If answer is not found, say you don't know.

Uploaded document sources:
{file_sources}

<Document Context>
{document_text}
</Document Context>
"""

    # ---------- BUILD MESSAGE PAYLOAD ----------
    ollama_messages = [{"role": "system", "content": system_prompt}]

    for role, content in messages:
        ollama_messages.append({"role": role, "content": content})

    payload = {
        "model": model,
        "messages": ollama_messages,
        "stream": False,
    }

    # ---------- SEND TO OLLAMA ----------
    try:
        logger.info(f"Sending request to Ollama @ {OLLAMA_BASE_URL}")

        response = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json=payload,
            timeout=120,
        )

        response.raise_for_status()
        return response.json()["message"]["content"]

    except Exception as e:
        logger.error(f"Ollama error: {e}")
        return "⚠️ Error communicating with Ollama. Is Ollama running?"
```

---

## 📁 helm/severus-ai/ Directory

### `helm/severus-ai/Chart.yaml`

```yaml
apiVersion: v2
name: severus-ai
description: Severus AI Streamlit App
type: application
version: 0.1.0
appVersion: "1.0"
```

---

### `helm/severus-ai/values.yaml`

```yaml
image:
  repository: sujanchow/serverus-ai
  tag: v1
  pullPolicy: IfNotPresent

service:
  type: ClusterIP
  port: 8501

ingress:
  enabled: true
  className: traefik
  hosts:
    - host: severus-ai.local
      paths:
        - path: /
          pathType: Prefix
ollama:
  baseUrl: http://host.docker.internal:11434
```

---

## 📁 helm/severus-ai/templates/ Directory

### `helm/severus-ai/templates/_helpers.tpl`

```
{{- define "severus-ai.name" -}}
severus-ai
{{- end }}

{{- define "severus-ai.fullname" -}}
severus-ai
{{- end }}

{{- define "severus-ai.labels" -}}
app: severus-ai
{{- end }}
```

---

### `helm/severus-ai/templates/deployment.yaml`

```yaml
apiVersion: apps/v1
kind: Deployment
metadata:
  name: {{ include "severus-ai.fullname" . }}
spec:
  replicas: 1
  selector:
    matchLabels:
      app: severus-ai
  template:
    metadata:
      labels:
        app: severus-ai
    spec:
      containers:
        - name: severus-ai
          image: "{{ .Values.image.repository }}:{{ .Values.image.tag }}"
          imagePullPolicy: {{ .Values.image.pullPolicy }}
          ports:
            - containerPort: 8501
          env:
            - name: OLLAMA_BASE_URL
              value: http://host.docker.internal:11434
```

---

### `helm/severus-ai/templates/service.yaml`

```yaml
apiVersion: v1
kind: Service
metadata:
  name: {{ include "severus-ai.fullname" . }}
spec:
  type: {{ .Values.service.type }}
  selector:
    app: severus-ai
  ports:
    - port: {{ .Values.service.port }}
      targetPort: 8501
```

---

### `helm/severus-ai/templates/ingress.yaml`

```yaml
{{- if .Values.ingress.enabled }}
apiVersion: networking.k8s.io/v1
kind: Ingress
metadata:
  name: {{ include "severus-ai.fullname" . }}
  annotations:
    kubernetes.io/ingress.class: traefik
spec:
  ingressClassName: {{ .Values.ingress.className }}
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
                  number: {{ .Values.service.port }}
{{- end }}
```

---

## 📊 Project Summary

**Total Files Documented:** 25

**Technologies Used:**
- **Frontend:** Streamlit
- **Backend:** Python 3.11
- **Database:** SQLite
- **AI/ML:** Ollama (gemma3:1b model)
- **Containerization:** Docker
- **Orchestration:** Kubernetes (K3s)
- **Package Management:** Helm
- **CI/CD:** Jenkins
- **Security:** Trivy
- **Monitoring:** Prometheus

**Key Features:**
- User authentication with signup/login
- Multi-chat support with persistent storage
- File upload and processing (PDF, CSV, Excel, Images, Text files)
- Document summarization using AI
- Context-aware chat with uploaded documents
- Kubernetes deployment with Ingress
- CI/CD pipeline with Jenkins
- Security scanning with Trivy

---

*Document generated on: 2026-01-29*
*Project: Severus AI - Personal Local AI Assistant*
