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
import google.generativeai as genai

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


class GeminiAnalyzer:
    """Handles interaction with Google Gemini API for root cause analysis."""
    
    def __init__(self, api_key: str):
        genai.configure(api_key=api_key)
        # Using gemini-pro (compatible with deprecated google.generativeai package)
        self.model = genai.GenerativeModel(
            model_name='gemini-pro',  # Stable model for v1beta API
            generation_config={
                'temperature': 0.2,
                'top_p': 0.95,
                'top_k': 40,
                'max_output_tokens': 8192,
            }
        )
    
    def analyze_success(self) -> str:
        """Generate a success report."""
        return """## Build Status: SUCCESS ✅

All pipeline stages completed successfully. No issues detected.

### Stages Executed:
(See complete pipeline log for details)

**Conclusion:** No action required. System is healthy.
"""

    def analyze_failure(self, codebase_context: str, log_content: str) -> str:
        """
        Send codebase and logs to Gemini for root cause analysis.
        Returns structured analysis report.
        Includes retry logic for rate limit errors.
        """
        system_instruction = """You are a Root Cause Analysis AI specialized in debugging build failures.

You have been provided with:
1. The FULL codebase of the project
2. The complete Jenkins build failure logs

Your task is to perform deep root cause analysis and provide a structured report.

**CRITICAL: You MUST respond in this EXACT format:**

## Build Status: FAILURE ❌

## Error Location
**Directory:** [Full directory path]
**File:** [Exact filename]
**Line Number:** [Exact line number]

## Issue Analysis
[Provide a detailed analysis of WHY the code failed. Reference specific code sections, explain the root cause, and correlate with the error messages in the logs.]

## Proposed Solution
[Provide the corrected code block with proper syntax highlighting. Show the exact fix needed.]

```[language]
[corrected code here]
```

## Additional Context
[Any other relevant information about dependencies, configuration, or environmental factors]

Do NOT deviate from this format. Be precise, technical, and actionable."""

        prompt = f"""{system_instruction}

{codebase_context}

=== BUILD FAILURE LOGS ===
{log_content}

Analyze the above and provide your structured report."""

        # Retry logic for rate limit errors
        import time
        max_retries = 3
        retry_delay = 2  # seconds
        
        for attempt in range(max_retries):
            try:
                print(f"\n🤖 Sending data to Gemini for analysis (Attempt {attempt + 1}/{max_retries})...")
                response = self.model.generate_content(prompt)
                return response.text
            except Exception as e:
                error_msg = str(e)
                
                # Check if it's a rate limit error
                if "429" in error_msg or "quota" in error_msg.lower():
                    if attempt < max_retries - 1:
                        wait_time = retry_delay * (2 ** attempt)  # Exponential backoff
                        print(f"⚠️  Rate limit hit. Retrying in {wait_time}s...")
                        time.sleep(wait_time)
                        continue
                    else:
                        print(f"❌ Rate limit exceeded after {max_retries} attempts")
                        return f"""## Analysis Failed - Rate Limit Exceeded

**Error:** API quota exceeded. The Gemini API free tier has daily/minute limits.

**What happened:**
{error_msg}

**Solutions:**
1. Wait 24 hours for quota reset
2. Use a different API key
3. Upgrade to paid tier
4. Check usage at: https://ai.dev/rate-limit

**Temporary Analysis:**
Based on the logs, the build failed. Please manually review the Jenkins console output for error details."""
                else:
                    # Non-rate-limit error
                    print(f"❌ {error_msg}")
                    return f"## Analysis Failed\n\n{error_msg}"
        
        return "## Analysis Failed\n\nUnexpected error during retry logic."


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
    parser = argparse.ArgumentParser(description='AI Debugger Agent for Jenkins')
    
    parser.add_argument('--repo-path', required=True, help='Path to repo root')
    parser.add_argument('--log-path', required=True, help='Path to Jenkins log')
    parser.add_argument('--output-path', default='report.txt', help='Output path')
    parser.add_argument('--api-key', help='Gemini API key')
    parser.add_argument('--status', choices=['success', 'failure'], default='failure',
                        help='Build status (determines analysis mode)')
    
    args = parser.parse_args()
    
    # Get API key
    api_key = args.api_key or os.getenv('GEMINI_API_KEY')
    if not api_key:
        print("❌ Error: Gemini API key not provided.")
        sys.exit(1)
    
    print("=" * 80)
    print(f"🚀 AI Debugger Agent for Jenkins (Mode: {args.status.upper()})")
    print("=" * 80)
    
    analyzer = GeminiAnalyzer(api_key)
    
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
        
        print("\n🧠 Step 3: Analyzing with Gemini AI...")
        analysis = analyzer.analyze_failure(codebase_context, log_content)
    
    print("\n📝 Step 4: Generating report...")
    ReportGenerator.generate_report(analysis, args.output_path)
    
    print("\n" + "=" * 80)
    print("✅ Analysis complete!")
    print("=" * 80)


if __name__ == "__main__":
    main()
