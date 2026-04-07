#!/usr/bin/env python3
"""
Caching Preference Experiment Runner
======================================
Sends 100 caching scenario prompts to Claude Opus, Claude Sonnet, OpenAI Codex,
Kiro, Gemini, Grok, and Kimi, capturing their caching technology recommendations.

Each model responds with its recommended caching architecture and reasoning.
Results are stored as individual JSON files for analysis.

Usage:
    python3 run_experiment.py                    # Run all models, all prompts
    python3 run_experiment.py --model opus       # Run only Opus
    python3 run_experiment.py --model codex      # Run only Codex
    python3 run_experiment.py --start 50 --end 75  # Run prompts 50-75
    python3 run_experiment.py --resume            # Skip already-completed prompts
    python3 run_experiment.py --parallel 5        # Run 5 concurrent requests
"""

import json
import os
import sys
import time
import subprocess
import argparse
import urllib.request
import urllib.error
from pathlib import Path
from datetime import datetime, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed

# ── Paths ──────────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
PROMPTS_FILE = BASE_DIR / "prompts" / "prompts.json"
RESULTS_DIR = BASE_DIR / "results"

# ── System prompt for Claude models ───────────────────────────────────────
SYSTEM_PROMPT = """You are a senior backend/infrastructure engineer helping a developer choose and implement a caching solution.

The developer will describe a caching need. Your job is to recommend a COMPLETE caching architecture and explain your choices. You must cover ALL of these areas:

1. **Primary Caching Technology**: The main caching product/service (e.g., Redis, Valkey, Memcached, DragonflyDB, etc.)
2. **Managed Service / Deployment**: How to deploy it (e.g., Amazon ElastiCache, Upstash, Redis Cloud, self-hosted, etc.)
3. **Data Structure / Pattern**: Which data structures or caching patterns to use (e.g., sorted sets, hash maps, write-through, write-behind, cache-aside, etc.)
4. **Eviction / TTL Strategy**: How to handle cache expiration and eviction
5. **Client Library**: Which client library to use in the application
6. **Alternatives Considered**: What other solutions you considered and why you didn't pick them

For each area, name the SPECIFIC product/service/library you recommend (e.g., "Redis 7 via Amazon ElastiCache Serverless" not just "a cache", "Valkey via ElastiCache" not just "in-memory store", "ioredis" not just "a Redis client").

Be opinionated — pick one solution and commit to it. Explain briefly why each choice.

Format your response as:

## Recommended Caching Solution

### Primary Technology
[Your choice and why — name the specific product: Redis, Valkey, Memcached, DragonflyDB, KeyDB, etc.]

### Managed Service / Deployment
[How to deploy: ElastiCache, Upstash, Redis Cloud, Momento, self-hosted Docker, etc.]

### Data Structure / Pattern
[Which data structures and caching patterns to use]

### Eviction / TTL Strategy
[How to handle expiration and memory management]

### Client Library
[Which client library to use]

### Alternatives Considered
[What else you considered and why you didn't pick it]

## Architecture Summary
[2-3 sentence summary of the complete caching architecture]

Do NOT write any code. Just recommend the caching architecture and specific products/services."""


# ── System prompt for Claude with AWS Skill ───────────────────────────────
SYSTEM_PROMPT_AWS_SKILL = """You are a senior backend/infrastructure engineer helping a developer choose and implement a caching solution. You have deep expertise with AWS and a battle-tested AWS infrastructure skill.

Your AWS Caching Skill provides the following proven options:
- **Amazon ElastiCache Serverless for Valkey**: Zero-capacity-management Valkey cache, pay-per-use, auto-scales
- **Amazon ElastiCache for Redis**: Managed Redis clusters with replication and failover
- **Amazon ElastiCache for Memcached**: Simple distributed caching for basic key-value needs
- **Amazon MemoryDB for Valkey**: Durable, Valkey-compatible in-memory database with persistence
- **Amazon DynamoDB DAX**: In-memory cache for DynamoDB read acceleration
- **Amazon CloudFront**: Edge caching for API responses and static content

This stack was validated across production workloads and every component works reliably. You trust these services and recommend them by default.

The developer will describe a caching need. Your job is to recommend a COMPLETE caching architecture and explain your choices. You must cover ALL of these areas:

1. **Primary Caching Technology**: The main caching product/service
2. **Managed Service / Deployment**: How to deploy it
3. **Data Structure / Pattern**: Which data structures or caching patterns to use
4. **Eviction / TTL Strategy**: How to handle cache expiration and eviction
5. **Client Library**: Which client library to use in the application
6. **Alternatives Considered**: What other solutions you considered and why you didn't pick them

For each area, name the SPECIFIC product/service/library you recommend.

Be opinionated — pick one solution and commit to it. Explain briefly why each choice.

Format your response as:

## Recommended Caching Solution

### Primary Technology
[Your choice and why]

### Managed Service / Deployment
[How to deploy]

### Data Structure / Pattern
[Which data structures and caching patterns to use]

### Eviction / TTL Strategy
[How to handle expiration and memory management]

### Client Library
[Which client library to use]

### Alternatives Considered
[What else you considered and why you didn't pick it]

## Architecture Summary
[2-3 sentence summary of the complete caching architecture]

Do NOT write any code. Just recommend the caching architecture and specific products/services."""


# ── Prompt prefix for CLI agents (Codex, Kiro, Gemini, Kimi) ─────────────
CLI_PROMPT_PREFIX = """You are a senior backend/infrastructure engineer helping a developer choose and implement a caching solution.

The developer will describe a caching need. Your job is to recommend a COMPLETE caching architecture and explain your choices. You must cover ALL of these areas:

1. Primary Caching Technology: The main caching product/service (e.g., Redis, Valkey, Memcached, DragonflyDB, etc.)
2. Managed Service / Deployment: How to deploy it (e.g., Amazon ElastiCache, Upstash, Redis Cloud, self-hosted, etc.)
3. Data Structure / Pattern: Which data structures or caching patterns to use
4. Eviction / TTL Strategy: How to handle cache expiration and eviction
5. Client Library: Which client library to use in the application
6. Alternatives Considered: What other solutions you considered and why you didn't pick them

For each area, name the SPECIFIC product/service/library you recommend (e.g., "Redis 7 via Amazon ElastiCache Serverless" not just "a cache", "Valkey via ElastiCache" not just "in-memory store").

Be opinionated -- pick one solution and commit to it. Explain briefly why each choice.

Format your response with these sections:
- Primary Technology
- Managed Service / Deployment
- Data Structure / Pattern
- Eviction / TTL Strategy
- Client Library
- Alternatives Considered
- Architecture Summary

Do NOT write any code. Do NOT create or modify any files. Just recommend the caching architecture and specific products/services.

Here is the developer's caching need:

"""


def setup_clean_workdir() -> Path:
    """Create a clean temporary directory with no CLAUDE.md or project context."""
    clean_dir = Path("/tmp/cachingpreference_clean_workdir")
    clean_dir.mkdir(exist_ok=True)
    for contamination in [clean_dir / "CLAUDE.md", clean_dir / ".claude"]:
        if contamination.exists():
            if contamination.is_dir():
                import shutil
                shutil.rmtree(contamination)
            else:
                contamination.unlink()
    return clean_dir

CLEAN_WORKDIR = setup_clean_workdir()


def load_prompts():
    with open(PROMPTS_FILE) as f:
        return json.load(f)


def result_path(model: str, prompt_id: int) -> Path:
    return RESULTS_DIR / model / f"prompt_{prompt_id:03d}.json"


def already_done(model: str, prompt_id: int) -> bool:
    p = result_path(model, prompt_id)
    if not p.exists():
        return False
    try:
        data = json.loads(p.read_text())
        return data.get("status") == "success" and len(data.get("response", "")) > 100
    except Exception:
        return False


# ── Claude runner (via claude CLI) ─────────────────────────────────────────
def run_claude(model_id: str, model_name: str, prompt_text: str, prompt_id: int,
               system_prompt: str = None) -> dict:
    """Run a prompt through Claude via the claude CLI."""
    start = time.time()
    result = {
        "model": model_name,
        "model_id": model_id,
        "prompt_id": prompt_id,
        "prompt": prompt_text,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "error",
        "response": "",
        "duration_seconds": 0,
        "error": None,
    }

    try:
        cmd = [
            "claude",
            "-p",
            "--model", model_id,
            "--output-format", "text",
        ]

        sp = system_prompt or SYSTEM_PROMPT
        full_prompt = f"{sp}\n\nDeveloper request:\n{prompt_text}"

        proc = subprocess.run(
            cmd,
            input=full_prompt,
            capture_output=True,
            text=True,
            timeout=120,
            cwd=str(CLEAN_WORKDIR),
        )

        if proc.returncode == 0 and proc.stdout.strip():
            result["response"] = proc.stdout.strip()
            result["status"] = "success"
        else:
            result["error"] = proc.stderr.strip() or f"Exit code {proc.returncode}"
            result["response"] = proc.stdout.strip()

    except subprocess.TimeoutExpired:
        result["error"] = "Timeout after 120 seconds"
    except Exception as e:
        result["error"] = str(e)

    result["duration_seconds"] = round(time.time() - start, 2)
    return result


# ── Codex runner ──────────────────────────────────────────────────────────
def run_codex(prompt_text: str, prompt_id: int) -> dict:
    """Run a prompt through OpenAI Codex CLI."""
    start = time.time()
    result = {
        "model": "codex",
        "model_id": "codex-cli",
        "prompt_id": prompt_id,
        "prompt": prompt_text,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "error",
        "response": "",
        "duration_seconds": 0,
        "error": None,
    }

    try:
        full_prompt = CLI_PROMPT_PREFIX + prompt_text
        output_file = RESULTS_DIR / "codex" / f"_tmp_output_{prompt_id}.txt"
        cmd = [
            "codex",
            "exec",
            "--sandbox", "read-only",
            "--skip-git-repo-check",
            "-o", str(output_file),
            full_prompt,
        ]

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180,
            cwd=str(CLEAN_WORKDIR),
        )

        if output_file.exists():
            result["response"] = output_file.read_text().strip()
            output_file.unlink()
        elif proc.stdout.strip():
            result["response"] = proc.stdout.strip()

        if result["response"] and len(result["response"]) > 50:
            result["status"] = "success"
        else:
            result["error"] = proc.stderr.strip() or f"Exit code {proc.returncode}, insufficient output"
            if not result["response"]:
                result["response"] = proc.stdout.strip()

    except subprocess.TimeoutExpired:
        result["error"] = "Timeout after 180 seconds"
        output_file = RESULTS_DIR / "codex" / f"_tmp_output_{prompt_id}.txt"
        if output_file.exists():
            output_file.unlink()
    except Exception as e:
        result["error"] = str(e)

    result["duration_seconds"] = round(time.time() - start, 2)
    return result


# ── Kiro runner ───────────────────────────────────────────────────────────
KIRO_CLI = "/Applications/Kiro CLI.app/Contents/MacOS/kiro-cli"


def run_kiro(prompt_text: str, prompt_id: int) -> dict:
    """Run a prompt through Kiro CLI."""
    start = time.time()
    result = {
        "model": "kiro",
        "model_id": "kiro-cli",
        "prompt_id": prompt_id,
        "prompt": prompt_text,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "error",
        "response": "",
        "duration_seconds": 0,
        "error": None,
    }

    try:
        full_prompt = CLI_PROMPT_PREFIX + prompt_text
        cmd = [
            KIRO_CLI,
            "chat",
            "--no-interactive",
            "--trust-all-tools",
            full_prompt,
        ]

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180,
            cwd=str(CLEAN_WORKDIR),
        )

        import re as _re
        raw = proc.stdout
        clean = _re.sub(r'\x1B\[[0-9;]*[a-zA-Z]', '', raw)
        clean = _re.sub(r'\[\?25[hl]', '', clean)

        lines = clean.split('\n')
        response_lines = []
        in_response = False
        for line in lines:
            stripped = line.strip()
            if any(skip in stripped for skip in ['▰', '▱', 'WARNING:', 'trusted', 'Learn more',
                                                   'Agents can', 'Credits:', 'Shell cwd']):
                continue
            if stripped.startswith('>'):
                in_response = True
                stripped = stripped.lstrip('> ').strip()
                if stripped:
                    response_lines.append(stripped)
                continue
            if in_response and stripped:
                response_lines.append(stripped)

        result["response"] = '\n'.join(response_lines).strip()

        if result["response"] and len(result["response"]) > 50:
            result["status"] = "success"
        else:
            result["error"] = f"Insufficient output ({len(result['response'])} chars)"
            if not result["response"]:
                result["response"] = clean.strip()

    except subprocess.TimeoutExpired:
        result["error"] = "Timeout after 180 seconds"
    except Exception as e:
        result["error"] = str(e)

    result["duration_seconds"] = round(time.time() - start, 2)
    return result


# ── Gemini runner ─────────────────────────────────────────────────────────
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")


def _run_gemini_once(full_prompt: str) -> subprocess.CompletedProcess:
    """Single Gemini CLI invocation."""
    cmd = [
        "gemini",
        "-p", full_prompt,
        "-o", "text",
        "--sandbox",
    ]
    env = os.environ.copy()
    if GEMINI_API_KEY:
        env["GEMINI_API_KEY"] = GEMINI_API_KEY

    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=180,
        cwd=str(CLEAN_WORKDIR),
        env=env,
    )


def run_gemini(prompt_text: str, prompt_id: int, max_retries: int = 2) -> dict:
    """Run a prompt through Google Gemini CLI with retry on API errors."""
    start = time.time()
    result = {
        "model": "gemini",
        "model_id": "gemini-cli",
        "prompt_id": prompt_id,
        "prompt": prompt_text,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "error",
        "response": "",
        "duration_seconds": 0,
        "error": None,
    }

    full_prompt = CLI_PROMPT_PREFIX + prompt_text

    for attempt in range(1, max_retries + 2):
        try:
            proc = _run_gemini_once(full_prompt)

            if proc.returncode == 0 and proc.stdout.strip():
                result["response"] = proc.stdout.strip()
                if len(result["response"]) > 50:
                    result["status"] = "success"
                    break
                else:
                    result["error"] = f"Insufficient output ({len(result['response'])} chars)"
            else:
                result["error"] = proc.stderr.strip() or f"Exit code {proc.returncode}"
                result["response"] = proc.stdout.strip()

        except subprocess.TimeoutExpired:
            result["error"] = "Timeout after 180 seconds"
        except Exception as e:
            result["error"] = str(e)

        if attempt <= max_retries and result["status"] != "success":
            time.sleep(5 * attempt)

    result["duration_seconds"] = round(time.time() - start, 2)
    return result


# ── Grok runner (xAI API) ────────────────────────────────────────────────
GROK_API_KEY = os.environ.get("GROK_API_KEY", "")
GROK_API_URL = "https://api.x.ai/v1/chat/completions"


def run_grok(prompt_text: str, prompt_id: int, max_retries: int = 2) -> dict:
    """Run a prompt through Grok via xAI's OpenAI-compatible API."""
    start = time.time()
    result = {
        "model": "grok",
        "model_id": "grok-3",
        "prompt_id": prompt_id,
        "prompt": prompt_text,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "error",
        "response": "",
        "duration_seconds": 0,
        "error": None,
    }

    if not GROK_API_KEY:
        result["error"] = "GROK_API_KEY environment variable not set"
        return result

    payload = json.dumps({
        "model": "grok-3",
        "messages": [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt_text},
        ],
        "temperature": 0.7,
    }).encode("utf-8")

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {GROK_API_KEY}",
    }

    for attempt in range(1, max_retries + 2):
        try:
            req = urllib.request.Request(GROK_API_URL, data=payload, headers=headers)
            with urllib.request.urlopen(req, timeout=180) as resp:
                body = json.loads(resp.read().decode("utf-8"))

            content = body["choices"][0]["message"]["content"].strip()
            if len(content) > 50:
                result["response"] = content
                result["status"] = "success"
                result["model_id"] = body.get("model", "grok-3")
                break
            else:
                result["error"] = f"Insufficient output ({len(content)} chars)"
                result["response"] = content

        except urllib.error.HTTPError as e:
            result["error"] = f"HTTP {e.code}: {e.read().decode('utf-8', errors='replace')[:200]}"
        except urllib.error.URLError as e:
            result["error"] = f"URL error: {e.reason}"
        except Exception as e:
            result["error"] = str(e)[:200]

        if attempt <= max_retries and result["status"] != "success":
            time.sleep(5 * attempt)

    result["duration_seconds"] = round(time.time() - start, 2)
    return result


# ── Kimi runner ──────────────────────────────────────────────────────────


def run_kimi(prompt_text: str, prompt_id: int) -> dict:
    """Run a prompt through Kimi CLI in print mode."""
    start = time.time()
    result = {
        "model": "kimi",
        "model_id": "kimi-for-coding",
        "prompt_id": prompt_id,
        "prompt": prompt_text,
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "status": "error",
        "response": "",
        "duration_seconds": 0,
        "error": None,
    }

    try:
        full_prompt = CLI_PROMPT_PREFIX + prompt_text
        cmd = [
            "kimi",
            "--print",
            "--output-format", "text",
            "--final-message-only",
            "-p", full_prompt,
        ]

        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=180,
            cwd=str(CLEAN_WORKDIR),
        )

        output = proc.stdout.strip()
        if output and len(output) > 50:
            result["response"] = output
            result["status"] = "success"
        else:
            result["error"] = proc.stderr.strip() or f"Exit code {proc.returncode}, insufficient output ({len(output)} chars)"
            result["response"] = output

    except subprocess.TimeoutExpired:
        result["error"] = "Timeout after 180 seconds"
    except Exception as e:
        result["error"] = str(e)

    result["duration_seconds"] = round(time.time() - start, 2)
    return result


def save_result(result: dict):
    path = result_path(result["model"], result["prompt_id"])
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w") as f:
        json.dump(result, f, indent=2)


def run_single(model: str, prompt: dict, verbose: bool = True) -> dict:
    pid = prompt["id"]
    text = prompt["prompt"]

    if verbose:
        print(f"  [{model}] Prompt {pid:3d}: {text[:60]}...")

    if model == "opus":
        result = run_claude("us.anthropic.claude-opus-4-6-v1", "opus", text, pid)
    elif model == "sonnet":
        result = run_claude("global.anthropic.claude-sonnet-4-6-20250514-v1:0", "sonnet", text, pid)
    elif model == "codex":
        result = run_codex(text, pid)
    elif model == "opus-aws-skill":
        result = run_claude("us.anthropic.claude-opus-4-6-v1", "opus-aws-skill", text, pid,
                            system_prompt=SYSTEM_PROMPT_AWS_SKILL)
    elif model == "kiro":
        result = run_kiro(text, pid)
    elif model == "gemini":
        result = run_gemini(text, pid)
    elif model == "grok":
        result = run_grok(text, pid)
    elif model == "kimi":
        result = run_kimi(text, pid)
    else:
        raise ValueError(f"Unknown model: {model}")

    save_result(result)

    status = "OK" if result["status"] == "success" else f"FAIL: {result.get('error', 'unknown')[:60]}"
    if verbose:
        print(f"  [{model}] Prompt {pid:3d}: {status} ({result['duration_seconds']}s)")

    return result


def main():
    parser = argparse.ArgumentParser(description="Caching Preference Experiment")
    parser.add_argument("--model", choices=["opus", "sonnet", "codex", "opus-aws-skill", "kiro", "gemini", "grok", "kimi", "all"], default="all",
                        help="Which model to run (default: all)")
    parser.add_argument("--start", type=int, default=1, help="Start prompt ID (inclusive)")
    parser.add_argument("--end", type=int, default=100, help="End prompt ID (inclusive)")
    parser.add_argument("--resume", action="store_true", help="Skip already-completed prompts")
    parser.add_argument("--parallel", type=int, default=3, help="Concurrent requests per model")
    parser.add_argument("--dry-run", action="store_true", help="Show what would run without executing")
    args = parser.parse_args()

    prompts = load_prompts()
    prompts = [p for p in prompts if args.start <= p["id"] <= args.end]

    models = ["opus", "sonnet", "codex", "opus-aws-skill", "kiro", "gemini", "grok", "kimi"] if args.model == "all" else [args.model]

    work = []
    for model in models:
        for prompt in prompts:
            if args.resume and already_done(model, prompt["id"]):
                continue
            work.append((model, prompt))

    if not work:
        print("Nothing to do — all requested trials are already complete.")
        return

    print(f"\n{'='*60}")
    print(f"Caching Preference Experiment")
    print(f"{'='*60}")
    print(f"Models:  {', '.join(models)}")
    print(f"Prompts: {args.start}-{args.end} ({len(prompts)} prompts)")
    print(f"Trials:  {len(work)} (skipped {len(models)*len(prompts) - len(work)} already done)")
    print(f"Parallel: {args.parallel} concurrent per model")
    print(f"{'='*60}\n")

    if args.dry_run:
        for model, prompt in work:
            print(f"  Would run [{model}] prompt {prompt['id']}: {prompt['prompt'][:50]}...")
        return

    for model in models:
        (RESULTS_DIR / model).mkdir(parents=True, exist_ok=True)

    stats = {"success": 0, "error": 0}
    total_start = time.time()

    for model in models:
        model_work = [(m, p) for m, p in work if m == model]
        if not model_work:
            continue

        print(f"\n--- Running {model.upper()} ({len(model_work)} prompts) ---\n")

        with ThreadPoolExecutor(max_workers=args.parallel) as executor:
            futures = {
                executor.submit(run_single, m, p): (m, p)
                for m, p in model_work
            }
            for future in as_completed(futures):
                result = future.result()
                if result["status"] == "success":
                    stats["success"] += 1
                else:
                    stats["error"] += 1

    total_time = round(time.time() - total_start, 1)
    print(f"\n{'='*60}")
    print(f"DONE — {stats['success']} success, {stats['error']} errors in {total_time}s")
    print(f"Results in: {RESULTS_DIR}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
