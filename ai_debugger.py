#!/usr/bin/env python3
"""
AI Debugger Agent for Jenkins
Analyzes build status, ingests codebase, and generates diagnostic reports using Gemini AI.
Supports both Success and Failure modes.
"""

import os
import sys
import argparse
import datetime
from pathlib import Path
from typing import List, Dict, Tuple
import requests
import json

# Configuration
SUPPORTED_EXTENSIONS = {
    '.py', '.js', '.java', '.ts', '.jsx', '.tsx', '.go', '.rs', '.c', '.cpp',
    '.h', '.hpp', '.cs', '.rb', '.php', '.swift', '.kt', '.scala', '.sh',
    '.bash', '.yaml', '.yml', '.json', '.xml', '.html', '.css', '.scss',
    '.sql', '.dockerfile', '.tf', '.md', '.txt', '.properties', '.conf',
    '.ini', '.toml', '.gradle', '.maven', '.pom', 'Jenkinsfile'
}

SKIP_DIRECTORIES = {
    '.git', 'node_modules', '__pycache__', '.pytest_cache', 'venv', 'env',
    '.venv', 'dist', 'build', 'target', '.idea', '.vscode', 'coverage',
    '.next', 'out', 'bin', 'obj', '.gradle', '.mvn', 'helm'
}

SKIP_FILES = {
    'package-lock.json', 'yarn.lock', 'poetry.lock', 'Pipfile.lock',
    'Gemfile.lock', 'composer.lock', '.DS_Store', 'ai_debugger.py'
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
        if file_path.suffix.lower() not in SUPPORTED_EXTENSIONS and file_path.name != 'Jenkinsfile':
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
            
            # Simple truncation if too large (Gemini has limits)
            if len(log_content) > 500000:
                 # Keep start and end for context
                 return log_content[:100000] + "\n... [LOG TRUNCATED] ...\n" + log_content[-300000:]
            return log_content
        except Exception as e:
            print(f"Error reading log file: {e}")
            return f"Error reading log file: {e}"


class OllamaAnalyzer:
    """Handles interaction with local Ollama API for root cause analysis."""
    
    def __init__(self, model_name: str = "qwen2.5-coder:7b", ollama_url: str = "http://localhost:11434"):
        self.model_name = model_name
        self.ollama_url = ollama_url
        self.api_endpoint = f"{ollama_url}/api/generate"
    
    def analyze_success(self) -> str:
        """Generate a success report."""
        return """## Build Status: SUCCESS ✅

All pipeline stages completed successfully. No issues detected.

### Stages Executed:
(See complete pipeline log for details)

**Conclusion:** No action required. System is healthy.
"""

    def find_error_in_codebase(self, log_content: str, codebase_context: str) -> str:
        """
        Extract error keywords from logs and search codebase for exact locations.
        Returns a formatted string with findings.
        """
        import re
        
        findings = []
        
        # Extract "command not found" errors
        cmd_not_found = re.findall(r'(\w+): command not found', log_content)
        
        for cmd in cmd_not_found:
            # Search codebase for this command
            for line in codebase_context.split('\n'):
                if f'FILE: ' in line:
                    current_file = line.replace('FILE: ', '').strip()
                elif cmd in line and '=' not in line:  # Found the command
                    findings.append(f"Found '{cmd}' in {current_file}")
        
        if findings:
            return "\n=== AUTOMATED ERROR LOCATION FINDINGS ===\n" + "\n".join(findings) + "\n\n"
        return ""

    def analyze_failure(self, codebase_context: str, log_content: str) -> str:
        """
        Send codebase and logs to Ollama for root cause analysis.
        Returns structured analysis report.
        """
        system_instruction = """You are a Root Cause Analysis AI specialized in debugging build failures.

You have been provided with:
1. The FULL codebase of the project (with file paths and content)
2. The complete Jenkins build failure logs

Your task is to perform deep root cause analysis and provide a structured report.

**CRITICAL INSTRUCTIONS:**
1. Read the error message from the logs carefully
2. Search through the codebase to find the EXACT file and line number where the error occurs
3. If the error mentions a command, string, or syntax error, grep through the codebase to locate it
4. Provide the ABSOLUTE file path (e.g., /workspace/Jenkinsfile or ./Jenkinsfile)
5. Provide the EXACT line number where the issue is located

**CRITICAL: You MUST respond in this EXACT format:**

## Build Status: FAILURE ❌

## Error Location
**File:** [EXACT file path from the codebase, e.g., ./Jenkinsfile or app.py]
**Line Number:** [EXACT line number where the error is - search the codebase to find it]
**Error String:** [The exact problematic code/command that caused the failure]

## Issue Analysis
[Explain WHY this specific line caused the failure. Reference the error message from the logs and explain how it relates to the code you found.]

## Proposed Solution
[Provide the exact fix - show what to remove or change on that specific line]

```[language]
# Before (line X):
[show the problematic line]

# After (line X):
[show the corrected line]
```

## Additional Context
[Any other relevant information]

**IMPORTANT**: You MUST search the codebase files to find the exact location. Do not give generic advice - give specific file paths and line numbers!"""

        # Preprocess: Find error locations automatically
        error_findings = self.find_error_in_codebase(log_content, codebase_context)
        
        prompt = f"""{system_instruction}

{error_findings}{codebase_context}

=== BUILD FAILURE LOGS ===
{log_content}

Analyze the above and provide your structured report."""

        print(f"\n🤖 Sending data to Ollama ({self.model_name}) for analysis...")
        
        try:
            response = requests.post(
                self.api_endpoint,
                json={
                    "model": self.model_name,
                    "prompt": prompt,
                    "stream": False,
                    "options": {
                        "temperature": 0.2,
                        "top_p": 0.95,
                        "top_k": 40,
                        "num_predict": 2048
                    }
                },
                timeout=300  # 5 minute timeout for large context
            )
            
            if response.status_code == 200:
                result = response.json()
                return result.get('response', '## Analysis Failed\n\nNo response from Ollama')
            else:
                error_msg = f"Ollama API returned status {response.status_code}: {response.text}"
                print(f"❌ {error_msg}")
                return f"""## Analysis Failed

**Error:** Failed to communicate with Ollama

**What happened:**
{error_msg}

**Solutions:**
1. Ensure Ollama is running: `ollama serve`
2. Check if model is installed: `ollama list`
3. Verify Ollama is accessible at {self.ollama_url}

**Temporary Analysis:**
Based on the logs, the build failed. Please manually review the Jenkins console output for error details."""
                
        except requests.exceptions.Timeout:
            return """## Analysis Failed - Timeout

**Error:** Ollama request timed out after 5 minutes.

**Solutions:**
1. The codebase might be too large for the model
2. Try a smaller model like `qwen2.5-coder:7b`
3. Reduce the context size in the script

**Temporary Analysis:**
Based on the logs, the build failed. Please manually review the Jenkins console output for error details."""
            
        except requests.exceptions.ConnectionError:
            return f"""## Analysis Failed - Connection Error

**Error:** Could not connect to Ollama at {self.ollama_url}

**Solutions:**
1. Start Ollama: `ollama serve`
2. Verify Ollama is running: `curl {self.ollama_url}`
3. Check if the model is installed: `ollama list`

**Temporary Analysis:**
Based on the logs, the build failed. Please manually review the Jenkins console output for error details."""
            
        except Exception as e:
            error_msg = str(e)
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
**Analyzer:** Ollama AI Root Cause Analysis Agent
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
    parser = argparse.ArgumentParser(description='AI Debugger Agent for Jenkins')
    
    parser.add_argument('--repo-path', required=True, help='Path to repo root')
    parser.add_argument('--log-path', required=True, help='Path to Jenkins log')
    parser.add_argument('--output-path', default='report.txt', help='Output path')
    parser.add_argument('--model', default='qwen2.5-coder:7b', help='Ollama model name')
    parser.add_argument('--ollama-url', default='http://localhost:11434', help='Ollama API URL')
    parser.add_argument('--status', choices=['success', 'failure'], default='failure',
                        help='Build status (determines analysis mode)')
    
    args = parser.parse_args()
    
    print("=" * 80)
    print(f"🚀 AI Debugger Agent for Jenkins (Mode: {args.status.upper()})")
    print("=" * 80)
    
    analyzer = OllamaAnalyzer(model_name=args.model, ollama_url=args.ollama_url)
    
    if args.status == 'success':
        print("\n✅ Build succeeded. Generating summary report...")
        analysis = analyzer.analyze_success()
    else:
        # Failure Mode: Full Analysis
        print("\n📂 Step 1: Ingesting codebase...")
        ingester = CodebaseIngester(args.repo_path)
        codebase_context = ingester.ingest_codebase()
        
        print("\n📋 Step 2: Parsing Jenkins logs...")
        log_content = LogParser.parse_log(args.log_path)
        print(f"✓ Log file loaded: {len(log_content)} characters")
        
        print(f"\n🧠 Step 3: Analyzing with Ollama ({args.model})...")
        analysis = analyzer.analyze_failure(codebase_context, log_content)
    
    print("\n📝 Step 4: Generating report...")
    ReportGenerator.generate_report(analysis, args.output_path)
    
    print("\n" + "=" * 80)
    print("✅ Analysis complete!")
    print("=" * 80)


if __name__ == "__main__":
    main()
