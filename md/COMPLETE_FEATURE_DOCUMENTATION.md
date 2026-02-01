# 🤖 AI Debugger for Jenkins - Complete Feature Documentation

> **Purpose:** This document contains EVERYTHING needed to add the AI Debugger feature to any project.  
> **Usage:** Give this document to an AI assistant to implement this feature in your project.

---

## 📋 Table of Contents

1. [Overview](#overview)
2. [Directory Structure](#directory-structure)
3. [Complete Code Files](#complete-code-files)
4. [Implementation Steps](#implementation-steps)
5. [Configuration Guide](#configuration-guide)
6. [Testing Instructions](#testing-instructions)

---

## Overview

### What This Feature Does

**AI Debugger for Jenkins** automatically analyzes build failures using Google's Gemini AI:

- ✅ **Automatic Trigger:** Runs only when Jenkins build fails (skipped on success)
- ✅ **Full Codebase Analysis:** Ingests entire Git repository for context
- ✅ **Log Analysis:** Parses Jenkins console logs for error traces
- ✅ **AI-Powered Root Cause:** Uses Gemini AI to identify exact error location
- ✅ **Detailed Reports:** Generates timestamped markdown reports with fixes
- ✅ **Email Notifications:** Optional email alerts with analysis attached

### Technology Stack

- **Language:** Python 3.8+
- **AI Model:** Google Gemini 2.5 Flash
- **CI/CD:** Jenkins Pipeline
- **Dependencies:** `google-generativeai`, `gitpython`

---

## Directory Structure

```
project-root/
├── ai_debugger.py              # Main AI debugger script
├── requirements.txt            # Python dependencies
├── Jenkinsfile                 # Jenkins pipeline with AI integration
├── setup.sh                    # Setup script (optional)
└── .gitignore                  # Git ignore rules (optional)
```

### File Descriptions

| File | Purpose | Required |
|------|---------|----------|
| `ai_debugger.py` | Core AI debugging logic | ✅ Yes |
| `requirements.txt` | Python package dependencies | ✅ Yes |
| `Jenkinsfile` | Jenkins pipeline configuration | ✅ Yes |
| `setup.sh` | Automated environment setup | ❌ Optional |
| `.gitignore` | Exclude generated reports | ❌ Optional |

---

## Complete Code Files

### 1. `ai_debugger.py`

**Full Python script for AI debugging:**

```python
#!/usr/bin/env python3
"""
AI Debugger Agent for Jenkins
A sophisticated Python script that ingests the entire Git repository,
analyzes Jenkins build failures, and generates timestamped diagnostic reports.
"""

import os
import sys
import argparse
import datetime
from pathlib import Path
from typing import List, Dict, Tuple
import google.generativeai as genai

# Configuration
SUPPORTED_EXTENSIONS = {
    '.py', '.js', '.java', '.ts', '.jsx', '.tsx', '.go', '.rs', '.c', '.cpp',
    '.h', '.hpp', '.cs', '.rb', '.php', '.swift', '.kt', '.scala', '.sh',
    '.bash', '.yaml', '.yml', '.json', '.xml', '.html', '.css', '.scss',
    '.sql', '.dockerfile', '.tf', '.md', '.txt', '.properties', '.conf',
    '.ini', '.toml', '.gradle', '.maven', '.pom'
}

SKIP_DIRECTORIES = {
    '.git', 'node_modules', '__pycache__', '.pytest_cache', 'venv', 'env',
    '.venv', 'dist', 'build', 'target', '.idea', '.vscode', 'coverage',
    '.next', 'out', 'bin', 'obj', '.gradle', '.mvn'
}

SKIP_FILES = {
    'package-lock.json', 'yarn.lock', 'poetry.lock', 'Pipfile.lock',
    'Gemfile.lock', 'composer.lock', '.DS_Store'
}

MAX_FILE_SIZE = 1024 * 1024  # 1MB per file limit


class CodebaseIngester:
    """Handles recursive ingestion of the entire codebase."""
    
    def __init__(self, repo_path: str):
        self.repo_path = Path(repo_path).resolve()
        self.files_processed = 0
        self.files_skipped = 0
        self.total_size = 0
        
    def is_text_file(self, file_path: Path) -> bool:
        """Check if file is a text-based source file."""
        if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS:
            return False
        if file_path.name in SKIP_FILES:
            return False
        if file_path.stat().st_size > MAX_FILE_SIZE:
            return False
        return True
    
    def read_file_safely(self, file_path: Path) -> Tuple[str, bool]:
        """Safely read file content, handling encoding issues."""
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return content, True
        except UnicodeDecodeError:
            try:
                with open(file_path, 'r', encoding='latin-1') as f:
                    content = f.read()
                return content, True
            except Exception:
                return "", False
        except Exception as e:
            print(f"Warning: Could not read {file_path}: {e}")
            return "", False
    
    def ingest_codebase(self) -> str:
        """
        Recursively walk through the repository and collect all source code.
        Returns a formatted string containing the entire codebase context.
        """
        codebase_context = "=== CURRENT CODEBASE STATE ===\n\n"
        
        for root, dirs, files in os.walk(self.repo_path):
            # Skip unwanted directories
            dirs[:] = [d for d in dirs if d not in SKIP_DIRECTORIES]
            
            root_path = Path(root)
            
            for file in files:
                file_path = root_path / file
                
                if not self.is_text_file(file_path):
                    self.files_skipped += 1
                    continue
                
                content, success = self.read_file_safely(file_path)
                if not success:
                    self.files_skipped += 1
                    continue
                
                # Get relative path for better readability
                try:
                    relative_path = file_path.relative_to(self.repo_path)
                except ValueError:
                    relative_path = file_path
                
                # Add file to context
                codebase_context += f"\n{'='*80}\n"
                codebase_context += f"FILE: {relative_path}\n"
                codebase_context += f"{'='*80}\n"
                codebase_context += content
                codebase_context += f"\n{'='*80}\n\n"
                
                self.files_processed += 1
                self.total_size += len(content)
        
        print(f"✓ Processed {self.files_processed} files")
        print(f"✗ Skipped {self.files_skipped} files")
        print(f"📊 Total context size: {self.total_size / 1024:.2f} KB")
        
        return codebase_context


class LogParser:
    """Handles parsing of Jenkins console logs."""
    
    @staticmethod
    def parse_log(log_path: str) -> str:
        """Read and parse the Jenkins log file."""
        try:
            with open(log_path, 'r', encoding='utf-8') as f:
                log_content = f.read()
            return log_content
        except Exception as e:
            print(f"Error reading log file: {e}")
            sys.exit(1)


class GeminiAnalyzer:
    """Handles interaction with Google Gemini API for root cause analysis."""
    
    def __init__(self, api_key: str):
        genai.configure(api_key=api_key)
        self.model = genai.GenerativeModel(
            model_name='gemini-2.5-flash',
            generation_config={
                'temperature': 0.2,
                'top_p': 0.95,
                'top_k': 40,
                'max_output_tokens': 8192,
            }
        )
    
    def analyze_failure(self, codebase_context: str, log_content: str) -> str:
        """
        Send codebase and logs to Gemini for root cause analysis.
        Returns structured analysis report.
        """
        system_instruction = """You are a Root Cause Analysis AI specialized in debugging build failures.

You have been provided with:
1. The FULL codebase of the project
2. The complete Jenkins build failure logs

Your task is to perform deep root cause analysis and provide a structured report.

**CRITICAL: You MUST respond in this EXACT format:**

## Error Location
**Directory:** [Full directory path, e.g., /src/backend/services]
**File:** [Exact filename, e.g., auth_service.py]
**Line Number:** [Exact line number where the error occurs, e.g., 42]

## Issue Analysis
[Provide a detailed analysis of WHY the code failed. Reference specific code sections, explain the root cause, and correlate with the error messages in the logs. Be technical and precise.]

## Proposed Solution
[Provide the corrected code block with proper syntax highlighting. Show the exact fix needed.]

```[language]
[corrected code here]
```

**Additional Context:** [Any other relevant information about dependencies, configuration, or environmental factors]

Do NOT deviate from this format. Be precise, technical, and actionable."""

        prompt = f"""{system_instruction}

{codebase_context}

=== BUILD FAILURE LOGS ===
{log_content}

Analyze the above and provide your structured report."""

        try:
            print("\n🤖 Sending data to Gemini for analysis...")
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            error_msg = f"Error during Gemini analysis: {e}"
            print(f"❌ {error_msg}")
            return f"## Analysis Failed\n\n{error_msg}"


class ReportGenerator:
    """Generates the final timestamped analysis report."""
    
    @staticmethod
    def generate_report(analysis: str, output_path: str) -> None:
        """Generate and save the final report with timestamp."""
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        report = f"""# AI Analysis Report - {timestamp}

---

{analysis}

---

**Report Generated:** {timestamp}
**Analyzer:** Gemini AI Root Cause Analysis Agent
"""
        
        try:
            with open(output_path, 'w', encoding='utf-8') as f:
                f.write(report)
            print(f"\n✅ Report saved to: {output_path}")
        except Exception as e:
            print(f"❌ Error saving report: {e}")
            sys.exit(1)


def main():
    """Main execution flow."""
    parser = argparse.ArgumentParser(
        description='AI Debugger Agent for Jenkins - Analyzes build failures using Gemini AI',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example usage:
  python ai_debugger.py --repo-path /path/to/repo --log-path jenkins.log
  python ai_debugger.py --repo-path . --log-path build.log --output-path analysis.md
        """
    )
    
    parser.add_argument(
        '--repo-path',
        required=True,
        help='Path to the root of the Git repository'
    )
    
    parser.add_argument(
        '--log-path',
        required=True,
        help='Path to the Jenkins console log file'
    )
    
    parser.add_argument(
        '--output-path',
        default='ai_report.md',
        help='Output path for the analysis report (default: ai_report.md)'
    )
    
    parser.add_argument(
        '--api-key',
        help='Gemini API key (or set GEMINI_API_KEY environment variable)'
    )
    
    args = parser.parse_args()
    
    # Get API key
    api_key = args.api_key or os.getenv('GEMINI_API_KEY')
    if not api_key:
        print("❌ Error: Gemini API key not provided.")
        print("   Use --api-key argument or set GEMINI_API_KEY environment variable")
        sys.exit(1)
    
    # Validate paths
    if not os.path.exists(args.repo_path):
        print(f"❌ Error: Repository path does not exist: {args.repo_path}")
        sys.exit(1)
    
    if not os.path.exists(args.log_path):
        print(f"❌ Error: Log file does not exist: {args.log_path}")
        sys.exit(1)
    
    print("=" * 80)
    print("🚀 AI Debugger Agent for Jenkins")
    print("=" * 80)
    
    # Step 1: Ingest codebase
    print("\n📂 Step 1: Ingesting codebase...")
    ingester = CodebaseIngester(args.repo_path)
    codebase_context = ingester.ingest_codebase()
    
    # Step 2: Parse logs
    print("\n📋 Step 2: Parsing Jenkins logs...")
    log_content = LogParser.parse_log(args.log_path)
    print(f"✓ Log file loaded: {len(log_content)} characters")
    
    # Step 3: Analyze with Gemini
    print("\n🧠 Step 3: Analyzing with Gemini AI...")
    analyzer = GeminiAnalyzer(api_key)
    analysis = analyzer.analyze_failure(codebase_context, log_content)
    
    # Step 4: Generate report
    print("\n📝 Step 4: Generating report...")
    ReportGenerator.generate_report(analysis, args.output_path)
    
    print("\n" + "=" * 80)
    print("✅ Analysis complete!")
    print("=" * 80)


if __name__ == "__main__":
    main()
```

---

### 2. `requirements.txt`

**Python dependencies:**

```txt
google-generativeai>=0.3.0
gitpython>=3.1.40
```

---

### 3. `Jenkinsfile`

**Complete Jenkins pipeline with AI debugger integration:**

```groovy
// Production Jenkinsfile with AI Debugger Integration
// This pipeline automatically runs AI analysis when ANY stage fails

pipeline {
    agent any
    
    environment {
        // Store API key in Jenkins credentials for security
        GEMINI_API_KEY = credentials('gemini-api-key')
        // Or use a hardcoded key for testing (NOT recommended for production)
        // GEMINI_API_KEY = 'YOUR_API_KEY_HERE'
    }
    
    stages {
        stage('Checkout') {
            steps {
                echo '📥 Checking out code from Git...'
                // Jenkins automatically pulls the code from Git
                checkout scm
            }
        }
        
        stage('Setup Environment') {
            steps {
                echo '🔧 Setting up environment...'
                sh '''
                    # Install Python dependencies if needed
                    if [ ! -d "venv" ]; then
                        python3 -m venv venv
                    fi
                    . venv/bin/activate
                    pip install -q -r requirements.txt || true
                '''
            }
        }
        
        stage('Build') {
            steps {
                echo '🏗️ Building application...'
                sh '''
                    # Your build commands here
                    # Example: npm install, mvn clean install, etc.
                    echo "Running build..."
                '''
            }
        }
        
        stage('Test') {
            steps {
                echo '🧪 Running tests...'
                sh '''
                    # Your test commands here
                    # Example: npm test, pytest, mvn test, etc.
                    echo "Running tests..."
                '''
            }
        }
        
        stage('Deploy') {
            steps {
                echo '🚀 Deploying application...'\n                sh '''
                    # Your deployment commands here
                    echo "Deploying..."
                '''
            }
        }
    }
    
    post {
        failure {
            script {
                echo '❌ Build failed! Running AI Debugger...'
                
                // Save Jenkins console log to file
                def logFile = "${WORKSPACE}/jenkins_console.log"
                def consoleLog = currentBuild.rawBuild.getLog(10000).join('\n')
                writeFile file: logFile, text: consoleLog
                
                // Run AI Debugger
                sh """
                    cd ${WORKSPACE}
                    
                    # Setup Python environment
                    if [ ! -d "venv" ]; then
                        python3 -m venv venv
                    fi
                    . venv/bin/activate
                    
                    # Install AI debugger dependencies
                    pip install -q google-generativeai gitpython
                    
                    # Run AI Debugger
                    python3 ai_debugger.py \\
                        --repo-path ${WORKSPACE} \\
                        --log-path ${logFile} \\
                        --output-path ai_analysis_\\$(date +%Y%m%d_%H%M%S).md
                """
                
                // Archive the AI analysis report
                archiveArtifacts artifacts: 'ai_analysis_*.md', allowEmptyArchive: false
                
                // Optional: Send email notification with report
                emailext(
                    subject: "🤖 AI Analysis: Build Failed - ${env.JOB_NAME} #${env.BUILD_NUMBER}",
                    body: """
                        Build failed for ${env.JOB_NAME} #${env.BUILD_NUMBER}
                        
                        🤖 AI Root Cause Analysis has been generated automatically.
                        
                        📊 View the detailed analysis report in the build artifacts:
                        ${env.BUILD_URL}artifact/
                        
                        📋 Console Output:
                        ${env.BUILD_URL}console
                    """,
                    to: "${env.CHANGE_AUTHOR_EMAIL}",
                    attachmentsPattern: 'ai_analysis_*.md'
                )
            }
        }
        
        success {
            echo '✅ Build succeeded! No AI analysis needed.'
        }
        
        always {
            echo '🧹 Cleaning up...'
            // Optional: Clean workspace
            // cleanWs()
        }
    }
}
```

---

### 4. `setup.sh` (Optional)

**Automated setup script:**

```bash
#!/bin/bash

# Setup script for AI Debugger
# This script creates a virtual environment and installs dependencies

echo "🚀 Setting up AI Debugger for Jenkins..."

# Check if Python 3 is installed
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.8 or higher."
    exit 1
fi

# Create virtual environment
echo "📦 Creating virtual environment..."
python3 -m venv venv

# Activate virtual environment
echo "✅ Activating virtual environment..."
source venv/bin/activate

# Upgrade pip
echo "⬆️  Upgrading pip..."
pip install --upgrade pip

# Install requirements
echo "📥 Installing dependencies..."
pip install -r requirements.txt

echo ""
echo "✅ Setup complete!"
echo ""
echo "To use the AI Debugger:"
echo "1. Activate the virtual environment:"
echo "   source venv/bin/activate"
echo ""
echo "2. Set your API key:"
echo "   export GEMINI_API_KEY='your-api-key-here'"
echo ""
echo "3. Run the debugger:"
echo "   python ai_debugger.py --repo-path /path/to/repo --log-path jenkins.log"
echo ""
```

---

### 5. `.gitignore` (Optional)

**Git ignore rules:**

```gitignore
# Python
__pycache__/
*.py[cod]
*$py.class
*.so
.Python
venv/
env/
ENV/
build/
develop-eggs/
dist/
downloads/
eggs/
.eggs/
lib/
lib64/
parts/
sdist/
var/
wheels/
*.egg-info/
.installed.cfg
*.egg

# AI Debugger outputs
ai_report*.md
ai_analysis*.md
jenkins_console.log

# IDE
.vscode/
.idea/
*.swp
*.swo
*~

# OS
.DS_Store
Thumbs.db
```

---

## Implementation Steps

### Step 1: Add Files to Your Project

Copy the following files to your project's root directory:

```bash
# Create the files in your project root
touch ai_debugger.py
touch requirements.txt
touch Jenkinsfile
touch setup.sh  # Optional
touch .gitignore  # Optional
```

Then copy the complete code from sections above into each file.

### Step 2: Make Scripts Executable

```bash
chmod +x ai_debugger.py
chmod +x setup.sh  # If using setup script
```

### Step 3: Configure Jenkins Credentials

**Option A: Using Jenkins Credentials Store (Recommended)**

1. Go to Jenkins → Manage Jenkins → Credentials
2. Click "Add Credentials"
3. Select "Secret text"
4. Fill in:
   - **Secret:** Your Gemini API key
   - **ID:** `gemini-api-key`
   - **Description:** Gemini API Key for AI Debugger
5. Click "OK"

**Option B: Hardcode for Testing (Not Recommended)**

Edit `Jenkinsfile` line 11:
```groovy
GEMINI_API_KEY = 'your-api-key-here'
```

⚠️ **Warning:** Never commit hardcoded API keys to Git!

### Step 4: Create Jenkins Pipeline Job

1. Go to Jenkins → New Item
2. Enter job name (e.g., "MyApp-with-AI-Debugger")
3. Select "Pipeline"
4. Click "OK"
5. Configure:
   - **Pipeline Definition:** Pipeline script from SCM
   - **SCM:** Git
   - **Repository URL:** Your Git repository URL
   - **Branch:** `*/main` or `*/master`
   - **Script Path:** `Jenkinsfile`
6. Click "Save"

### Step 5: Customize Build Stages

Edit the `Jenkinsfile` to match your project's build process:

**For Node.js projects:**
```groovy
stage('Build') {
    steps {
        sh 'npm install'
        sh 'npm run build'
    }
}

stage('Test') {
    steps {
        sh 'npm test'
    }
}
```

**For Python projects:**
```groovy
stage('Build') {
    steps {
        sh 'pip install -r requirements.txt'
    }
}

stage('Test') {
    steps {
        sh 'pytest tests/'
    }
}
```

**For Java/Maven projects:**
```groovy
stage('Build') {
    steps {
        sh 'mvn clean install'
    }
}

stage('Test') {
    steps {
        sh 'mvn test'
    }
}
```

### Step 6: Commit and Push

```bash
git add ai_debugger.py requirements.txt Jenkinsfile
git commit -m "Add AI Debugger integration"
git push origin main
```

### Step 7: Test the Integration

Trigger a build failure to test:

```python
# Add a failing test
def test_failure():
    assert 1 == 2  # This will fail
```

Commit and push, then check Jenkins for the AI analysis report in build artifacts.

---

## Configuration Guide

### Customize AI Model

Edit `ai_debugger.py` line 144:

```python
# For faster analysis (recommended)
model_name='gemini-2.5-flash',

# For more accurate analysis
model_name='gemini-2.5-pro',
```

### Filter File Types

Edit `ai_debugger.py` lines 17-23 to only analyze specific file types:

```python
SUPPORTED_EXTENSIONS = {
    '.py', '.js', '.yaml'  # Only Python, JavaScript, YAML
}
```

### Adjust Context Size

Edit `ai_debugger.py` line 36:

```python
MAX_FILE_SIZE = 1024 * 1024 * 2  # 2MB per file
```

### Custom Report Path

Edit `Jenkinsfile` line 97:

```groovy
--output-path custom/path/ai_analysis_\\$(date +%Y%m%d_%H%M%S).md
```

### Email Configuration

Edit `Jenkinsfile` lines 104-119 to customize email notifications:

```groovy
emailext(
    subject: "Custom Subject",
    body: "Custom body",
    to: "team@company.com",
    attachmentsPattern: 'ai_analysis_*.md'
)
```

---

## Testing Instructions

### Local Testing

**Test 1: Verify Script Works**

```bash
# Setup environment
source venv/bin/activate
export GEMINI_API_KEY="your-api-key"

# Create test files
mkdir -p test_project/src
echo "def broken(): return 1/0" > test_project/src/test.py
echo "Error: ZeroDivisionError" > test.log

# Run debugger
python ai_debugger.py \
    --repo-path test_project \
    --log-path test.log \
    --output-path test_report.md

# Check output
cat test_report.md
```

**Test 2: Check API Connectivity**

```python
# test_api.py
import google.generativeai as genai

genai.configure(api_key="your-api-key")

for model in genai.list_models():
    if 'generateContent' in model.supported_generation_methods:
        print(f"✓ {model.name}")
```

Run:
```bash
python test_api.py
```

### Jenkins Testing

**Test 1: Trigger Build Failure**

Add a failing test to your code:

```python
# test_example.py
def test_that_fails():
    assert False, "This test always fails"
```

Commit and push:
```bash
git add test_example.py
git commit -m "Test AI debugger"
git push
```

**Test 2: Verify Report Generation**

1. Go to Jenkins job
2. Click "Build Now"
3. Wait for build to fail
4. Check "Build Artifacts" for `ai_analysis_*.md`
5. Download and review the report

**Test 3: Check Email Notifications**

1. Configure email in Jenkins (Manage Jenkins → Configure System)
2. Trigger a build failure
3. Check email inbox for AI analysis report

---

## Expected Output

### Console Output

```
================================================================================
🚀 AI Debugger Agent for Jenkins
================================================================================

📂 Step 1: Ingesting codebase...
✓ Processed 15 files
✗ Skipped 3 files
📊 Total context size: 45.23 KB

📋 Step 2: Parsing Jenkins logs...
✓ Log file loaded: 1,234 characters

🧠 Step 3: Analyzing with Gemini AI...
🤖 Sending data to Gemini for analysis...

📝 Step 4: Generating report...
✅ Report saved to: ai_analysis_20260201_123456.md

================================================================================
✅ Analysis complete!
================================================================================
```

### Generated Report Format

```markdown
# AI Analysis Report - 2026-02-01 12:34:56

---

## Error Location
**Directory:** /src/backend/services
**File:** auth_service.py
**Line Number:** 42

## Issue Analysis
The build failed due to a TypeError in the authenticate() function.
The error occurs because...

## Proposed Solution
```python
def authenticate(user, password):
    # Fixed version
    if not user or not password:
        raise ValueError("User and password required")
    ...
```

**Additional Context:** 
Consider adding input validation and type hints...

---

**Report Generated:** 2026-02-01 12:34:56
**Analyzer:** Gemini AI Root Cause Analysis Agent
```

---

## Troubleshooting

### Common Issues

| Issue | Solution |
|-------|----------|
| `ModuleNotFoundError: No module named 'google'` | Run `pip install -r requirements.txt` |
| `API key not provided` | Set `GEMINI_API_KEY` environment variable |
| `404 model not found` | Update model name to `gemini-2.5-flash` |
| `403 API key leaked` | Generate new API key, keep it private |
| `429 Quota exceeded` | Wait 24h or switch to faster model |
| No report generated | Check Jenkins console for errors |

### Debug Mode

Add debug output to `ai_debugger.py`:

```python
# Add after line 14
import logging
logging.basicConfig(level=logging.DEBUG)
```

---

## API Key Setup

### Get Gemini API Key

1. Visit: https://makersuite.google.com/app/apikey
2. Click "Create API Key"
3. Copy the key
4. **Keep it private!**

### Set API Key

**Method 1: Environment Variable**
```bash
export GEMINI_API_KEY="your-key-here"
```

**Method 2: Jenkins Credentials**
```
Jenkins → Credentials → Add Secret Text
ID: gemini-api-key
```

**Method 3: Command Line**
```bash
python ai_debugger.py --api-key "your-key" --repo-path . --log-path log.txt
```

---

## Summary

### What You Get

✅ **Automatic AI debugging** when Jenkins builds fail  
✅ **Complete codebase analysis** for full context  
✅ **Detailed error reports** with exact locations and fixes  
✅ **Email notifications** with analysis attached  
✅ **Archived reports** in Jenkins build artifacts  

### Workflow

```
1. Jenkins pulls code from Git
2. Runs build stages (Build, Test, Deploy)
3. If ANY stage fails:
   → AI Debugger automatically triggers
   → Analyzes Git repo + Jenkins logs
   → Sends to Gemini AI
   → Generates detailed report
   → Archives in Jenkins
   → Sends email notification
4. If build succeeds:
   → AI Debugger is skipped
```

### Next Steps

1. ✅ Copy all files to your project
2. ✅ Configure Jenkins credentials
3. ✅ Create Jenkins pipeline job
4. ✅ Customize build stages
5. ✅ Test with a failing build
6. ✅ Review AI analysis report

---

**Version:** 1.0.0  
**Last Updated:** 2026-02-01  
**Compatible With:** Jenkins 2.x+, Python 3.8+, Any Git repository
