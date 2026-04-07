#!/usr/bin/env python3
"""
Caching Preference Experiment — Analysis
==========================================
Parses all experiment results and produces:
1. Per-model caching technology rankings
2. Cross-model comparison (Redis vs Valkey vs others)
3. Detailed breakdown by caching use case category
4. Summary report with key findings

Usage:
    python3 analyze_results.py                # Full analysis
    python3 analyze_results.py --model opus   # Single model analysis
    python3 analyze_results.py --csv          # Also export CSV files
"""

import json
import re
import os
import sys
import argparse
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime

BASE_DIR = Path(__file__).parent
RESULTS_DIR = BASE_DIR / "results"
ANALYSIS_DIR = BASE_DIR / "analysis"
PROMPTS_FILE = BASE_DIR / "prompts" / "prompts.json"

# ── Layers we're extracting ─────────────────────────────────────────────
LAYERS = [
    "primary_technology",
    "managed_service",
    "data_structure",
    "eviction_strategy",
    "client_library",
    "alternatives",
]

LAYER_DISPLAY = {
    "primary_technology": "Primary Caching Technology",
    "managed_service": "Managed Service / Deployment",
    "data_structure": "Data Structure / Pattern",
    "eviction_strategy": "Eviction / TTL Strategy",
    "client_library": "Client Library",
    "alternatives": "Alternatives Considered",
}

# ── Product normalization map ─────────────────────────────────────────────
NORMALIZE = {
    # Primary technologies
    "redis": "Redis",
    "redis 7": "Redis",
    "redis 7.x": "Redis",
    "redis oss": "Redis",
    "redis open source": "Redis",
    "valkey": "Valkey",
    "valkey 7": "Valkey",
    "valkey 8": "Valkey",
    "memcached": "Memcached",
    "memcache": "Memcached",
    "dragonflydb": "DragonflyDB",
    "dragonfly": "DragonflyDB",
    "keydb": "KeyDB",
    "garnet": "Garnet",
    "microsoft garnet": "Garnet",
    "kvrocks": "Kvrocks",
    "apache kvrocks": "Kvrocks",
    "hazelcast": "Hazelcast",
    "apache ignite": "Apache Ignite",
    "ignite": "Apache Ignite",
    "aerospike": "Aerospike",
    "couchbase": "Couchbase",

    # Managed services
    "amazon elasticache": "Amazon ElastiCache",
    "elasticache": "Amazon ElastiCache",
    "aws elasticache": "Amazon ElastiCache",
    "elasticache serverless": "ElastiCache Serverless",
    "amazon elasticache serverless": "ElastiCache Serverless",
    "elasticache for redis": "ElastiCache for Redis",
    "amazon elasticache for redis": "ElastiCache for Redis",
    "elasticache for valkey": "ElastiCache for Valkey",
    "amazon elasticache for valkey": "ElastiCache for Valkey",
    "elasticache for memcached": "ElastiCache for Memcached",
    "amazon memorydb": "Amazon MemoryDB",
    "memorydb": "Amazon MemoryDB",
    "memorydb for redis": "Amazon MemoryDB",
    "memorydb for valkey": "Amazon MemoryDB",
    "amazon dynamodb dax": "DynamoDB DAX",
    "dynamodb dax": "DynamoDB DAX",
    "dax": "DynamoDB DAX",
    "upstash": "Upstash",
    "upstash redis": "Upstash",
    "redis cloud": "Redis Cloud",
    "redis enterprise": "Redis Cloud",
    "redis enterprise cloud": "Redis Cloud",
    "momento": "Momento",
    "momento cache": "Momento",
    "google cloud memorystore": "Google Memorystore",
    "memorystore": "Google Memorystore",
    "cloud memorystore": "Google Memorystore",
    "azure cache for redis": "Azure Cache for Redis",
    "azure cache": "Azure Cache for Redis",
    "aiven for redis": "Aiven",
    "aiven": "Aiven",
    "cloudflare workers kv": "Cloudflare KV",
    "cloudflare kv": "Cloudflare KV",
    "vercel kv": "Vercel KV",
    "railway": "Railway",
    "render": "Render",
    "fly.io": "Fly.io",
    "docker": "Docker (self-hosted)",

    # Client libraries
    "ioredis": "ioredis",
    "node-redis": "node-redis",
    "redis-py": "redis-py",
    "jedis": "Jedis",
    "lettuce": "Lettuce",
    "go-redis": "go-redis",
    "stackexchange.redis": "StackExchange.Redis",
    "phpredis": "phpredis",
    "predis": "Predis",
    "redis-rb": "redis-rb",
    "redis-rs": "redis-rs",

    # Caching patterns
    "cache-aside": "Cache-Aside",
    "cache aside": "Cache-Aside",
    "lazy loading": "Cache-Aside",
    "read-through": "Read-Through",
    "read through": "Read-Through",
    "write-through": "Write-Through",
    "write through": "Write-Through",
    "write-behind": "Write-Behind",
    "write behind": "Write-Behind",
    "write-back": "Write-Behind",

    # Data structures
    "sorted sets": "Sorted Sets",
    "sorted set": "Sorted Sets",
    "zset": "Sorted Sets",
    "hash": "Hashes",
    "hashes": "Hashes",
    "hash map": "Hashes",
    "hashmap": "Hashes",
    "strings": "Strings",
    "string": "Strings",
    "lists": "Lists",
    "list": "Lists",
    "sets": "Sets",
    "set": "Sets",
    "streams": "Streams",
    "stream": "Streams",
    "hyperloglog": "HyperLogLog",
    "bloom filter": "Bloom Filter",
    "pub/sub": "Pub/Sub",
    "pubsub": "Pub/Sub",

    # Other caching technologies
    "apache kafka": "Kafka",
    "kafka": "Kafka",
    "rabbitmq": "RabbitMQ",
    "amazon sqs": "Amazon SQS",
    "sqs": "Amazon SQS",
    "amazon sns": "Amazon SNS",
    "sns": "Amazon SNS",
    "cloudfront": "CloudFront",
    "amazon cloudfront": "CloudFront",
    "varnish": "Varnish",
    "nginx": "Nginx",
    "cdn": "CDN",

    # Framework caches
    "django cache": "Django Cache Framework",
    "rails cache": "Rails Cache",
    "spring cache": "Spring Cache",
    "caffeine": "Caffeine (Java)",
    "guava cache": "Guava Cache",
    "ehcache": "Ehcache",
    "node-cache": "node-cache",
    "lru-cache": "lru-cache",
}


def normalize_product(name: str) -> str:
    if not name:
        return name
    lower = name.strip().lower()
    return NORMALIZE.get(lower, name.strip())


def extract_section(text: str, section_name: str) -> str:
    patterns = [
        rf"###\s*{re.escape(section_name)}[:\s]*\n(.*?)(?=\n###|\n##|\Z)",
        rf"\*\*{re.escape(section_name)}\*\*[:\s]*(.*?)(?=\n\*\*|\n###|\n##|\Z)",
        rf"^{re.escape(section_name)}[:\s]*(.*?)(?=\n[A-Z]|\n###|\n##|\n\*\*|\Z)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE | re.DOTALL | re.MULTILINE)
        if match:
            return match.group(1).strip()
    return ""


# ── Products to search for in each layer ──────────────────────────────────
LAYER_PRODUCTS = {
    "primary_technology": [
        "Redis", "Valkey", "Memcached", "DragonflyDB", "KeyDB", "Garnet",
        "Kvrocks", "Hazelcast", "Apache Ignite", "Aerospike", "Couchbase",
        "Kafka", "RabbitMQ", "Varnish", "Nginx",
    ],
    "managed_service": [
        "Amazon ElastiCache", "ElastiCache Serverless", "ElastiCache for Redis",
        "ElastiCache for Valkey", "ElastiCache for Memcached",
        "Amazon MemoryDB", "DynamoDB DAX",
        "Upstash", "Redis Cloud", "Momento",
        "Google Memorystore", "Azure Cache for Redis",
        "Cloudflare KV", "Vercel KV", "Aiven",
        "Railway", "Render", "Fly.io", "Docker (self-hosted)",
    ],
    "data_structure": [
        "Strings", "Hashes", "Lists", "Sets", "Sorted Sets",
        "Streams", "HyperLogLog", "Bloom Filter", "Pub/Sub",
        "JSON", "TimeSeries",
    ],
    "eviction_strategy": [
        "LRU", "LFU", "TTL", "allkeys-lru", "volatile-lru",
        "allkeys-lfu", "volatile-lfu", "noeviction",
        "Cache-Aside", "Read-Through", "Write-Through", "Write-Behind",
    ],
    "client_library": [
        "ioredis", "node-redis", "redis-py", "Jedis", "Lettuce",
        "go-redis", "StackExchange.Redis", "phpredis", "Predis",
        "redis-rb", "redis-rs",
    ],
}

# Keyword groups for detecting primary technology from full response
PRIMARY_TECH_KEYWORDS = {
    "Redis": [r"\bredis\b"],
    "Valkey": [r"\bvalkey\b"],
    "Memcached": [r"\bmemcached?\b"],
    "DragonflyDB": [r"\bdragonfly(?:db)?\b"],
    "KeyDB": [r"\bkeydb\b"],
    "Garnet": [r"\bgarnet\b"],
    "Kafka": [r"\bkafka\b"],
    "RabbitMQ": [r"\brabbitmq\b"],
    "Varnish": [r"\bvarnish\b"],
}

# Managed service keywords
MANAGED_SERVICE_KEYWORDS = {
    "Amazon ElastiCache": [r"\belasticache\b"],
    "Amazon MemoryDB": [r"\bmemorydb\b"],
    "DynamoDB DAX": [r"\bdax\b", r"\bdynamodb dax\b"],
    "Upstash": [r"\bupstash\b"],
    "Redis Cloud": [r"\bredis cloud\b", r"\bredis enterprise\b"],
    "Momento": [r"\bmomento\b"],
    "Google Memorystore": [r"\bmemorystore\b"],
    "Azure Cache for Redis": [r"\bazure cache\b"],
    "Cloudflare KV": [r"\bcloudflare.*kv\b", r"\bworkers kv\b"],
    "Vercel KV": [r"\bvercel kv\b"],
}


def extract_products_from_section(section_text: str, layer: str) -> list[str]:
    if not section_text:
        return []

    found = []
    text_lower = section_text.lower()

    candidates = LAYER_PRODUCTS.get(layer, [])
    for product in candidates:
        pattern = re.escape(product.lower())
        if re.search(rf"\b{pattern}\b", text_lower):
            found.append(product)

    return found


def detect_primary_technology(response_text: str) -> str:
    """Detect the primary caching technology recommended in the response."""
    text_lower = response_text.lower()

    # First try the Primary Technology section
    section_names = ["Primary Technology", "Primary Caching Technology", "Caching Technology",
                     "Technology", "Cache Technology"]
    section_text = ""
    for name in section_names:
        section_text = extract_section(response_text, name)
        if section_text:
            break

    # Count mentions in the primary section (weighted) + full response
    scores = Counter()
    for tech, patterns in PRIMARY_TECH_KEYWORDS.items():
        for pattern in patterns:
            # Section matches are worth 10 points
            if section_text:
                section_matches = len(re.findall(pattern, section_text.lower()))
                scores[tech] += section_matches * 10
            # Full response matches are worth 1 point
            full_matches = len(re.findall(pattern, text_lower))
            scores[tech] += full_matches

    if scores:
        return scores.most_common(1)[0][0]
    return "(Unknown)"


def detect_managed_service(response_text: str) -> str:
    """Detect the managed service recommended."""
    text_lower = response_text.lower()

    section_names = ["Managed Service / Deployment", "Managed Service", "Deployment",
                     "Infrastructure", "Hosting"]
    section_text = ""
    for name in section_names:
        section_text = extract_section(response_text, name)
        if section_text:
            break

    scores = Counter()
    for service, patterns in MANAGED_SERVICE_KEYWORDS.items():
        for pattern in patterns:
            if section_text:
                section_matches = len(re.findall(pattern, section_text.lower()))
                scores[service] += section_matches * 10
            full_matches = len(re.findall(pattern, text_lower))
            scores[service] += full_matches

    if scores:
        return scores.most_common(1)[0][0]
    return "(Self-hosted / Unknown)"


def extract_stack(response_text: str) -> dict:
    """Extract the full caching stack from a model's response."""
    stack = {}

    section_names = {
        "primary_technology": ["Primary Technology", "Primary Caching Technology",
                               "Caching Technology", "Technology", "Cache Technology",
                               "Recommended Caching Solution"],
        "managed_service": ["Managed Service / Deployment", "Managed Service",
                           "Deployment", "Infrastructure"],
        "data_structure": ["Data Structure / Pattern", "Data Structure",
                          "Data Structures", "Pattern", "Caching Pattern"],
        "eviction_strategy": ["Eviction / TTL Strategy", "Eviction Strategy",
                             "TTL Strategy", "Eviction", "TTL",
                             "Expiration", "Cache Expiration"],
        "client_library": ["Client Library", "Client", "Library",
                          "SDK", "Driver"],
        "alternatives": ["Alternatives Considered", "Alternatives",
                        "Other Options", "Why Not"],
    }

    for layer, names in section_names.items():
        section_text = ""
        for name in names:
            section_text = extract_section(response_text, name)
            if section_text:
                break

        if section_text:
            products = extract_products_from_section(section_text, layer)
            stack[layer] = {
                "raw_text": section_text[:500],
                "products": products,
                "primary": products[0] if products else None,
            }
        else:
            products = extract_products_from_section(response_text, layer)
            stack[layer] = {
                "raw_text": "",
                "products": products,
                "primary": products[0] if products else None,
            }

    # Add detected primary technology and managed service
    stack["_primary_technology"] = detect_primary_technology(response_text)
    stack["_managed_service"] = detect_managed_service(response_text)

    return stack


def load_results(model: str = None) -> list[dict]:
    results = []
    models = [model] if model else ["opus", "sonnet", "codex", "opus-aws-skill", "kiro", "gemini", "grok", "kimi"]

    for m in models:
        model_dir = RESULTS_DIR / m
        if not model_dir.exists():
            continue
        for f in sorted(model_dir.glob("prompt_*.json")):
            try:
                data = json.loads(f.read_text())
                if data.get("status") == "success":
                    results.append(data)
            except Exception:
                continue

    return results


def load_prompt_categories() -> dict:
    with open(PROMPTS_FILE) as f:
        prompts = json.load(f)
    return {p["id"]: p["category"] for p in prompts}


def compute_rankings(results: list[dict]) -> dict:
    layer_counts = defaultdict(Counter)
    layer_primary = defaultdict(Counter)

    for r in results:
        stack = extract_stack(r["response"])
        for layer in LAYERS:
            if layer in stack:
                info = stack[layer]
                for product in info.get("products", []):
                    layer_counts[layer][product] += 1
                if info.get("primary"):
                    layer_primary[layer][info["primary"]] += 1

    return {
        "all_mentions": dict(layer_counts),
        "primary_choice": dict(layer_primary),
    }


def compute_tech_rankings(results: list[dict]) -> Counter:
    counter = Counter()
    for r in results:
        stack = extract_stack(r["response"])
        tech = stack.get("_primary_technology", "(Unknown)")
        counter[tech] += 1
    return counter


def compute_service_rankings(results: list[dict]) -> Counter:
    counter = Counter()
    for r in results:
        stack = extract_stack(r["response"])
        service = stack.get("_managed_service", "(Unknown)")
        counter[service] += 1
    return counter


def compute_category_breakdown(results: list[dict], categories: dict) -> dict:
    cat_tech = defaultdict(Counter)
    for r in results:
        pid = r["prompt_id"]
        cat = categories.get(pid, "unknown")
        stack = extract_stack(r["response"])
        tech = stack.get("_primary_technology", "(Unknown)")
        cat_tech[cat][tech] += 1
    return dict(cat_tech)


def format_ranking(counter: Counter, total: int, top_n: int = 15) -> str:
    lines = []
    for rank, (product, count) in enumerate(counter.most_common(top_n), 1):
        pct = count / total * 100
        bar = "█" * int(pct / 2)
        lines.append(f"  {rank:2d}. {product:<35s} {count:4d} ({pct:5.1f}%) {bar}")
    return "\n".join(lines)


def generate_report(models: list[str] = None):
    if models is None:
        models = ["opus", "sonnet", "codex", "opus-aws-skill", "kiro", "gemini", "grok", "kimi"]

    categories = load_prompt_categories()
    lines = []

    def out(text=""):
        lines.append(text)

    out("=" * 80)
    out("CACHING PREFERENCE EXPERIMENT — ANALYSIS REPORT")
    out(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    out("=" * 80)
    out()

    all_results = {}
    for model in models:
        results = load_results(model)
        if not results:
            out(f"\n--- {model.upper()}: No results found ---\n")
            continue

        all_results[model] = results
        rankings = compute_rankings(results)
        tech = compute_tech_rankings(results)
        service = compute_service_rankings(results)
        n = len(results)

        out(f"\n{'='*80}")
        out(f"MODEL: {model.upper()} ({n} successful trials)")
        out(f"{'='*80}")

        out(f"\n--- Primary Caching Technology (Redis vs Valkey vs Others) ---")
        out(format_ranking(tech, n))

        out(f"\n--- Managed Service / Deployment ---")
        out(format_ranking(service, n))

        for layer in LAYERS:
            if layer in ("alternatives",):
                continue
            display = LAYER_DISPLAY.get(layer, layer)
            out(f"\n--- {display} (All Mentions) ---")
            all_m = rankings["all_mentions"].get(layer, Counter())
            if all_m:
                out(format_ranking(all_m, n, top_n=10))
            else:
                out("  (no data)")

    # Cross-model comparison
    if len(all_results) > 1:
        out(f"\n\n{'='*80}")
        out("CROSS-MODEL COMPARISON: Primary Caching Technology")
        out(f"{'='*80}")

        header = f"  {'Technology':<35s}"
        for model in models:
            if model in all_results:
                header += f"  {model.upper():>10s}"
        out(header)

        sep = f"  {'-'*35}"
        for model in models:
            if model in all_results:
                sep += f"  {'----------':>10s}"
        out(sep)

        all_techs = set()
        model_techs = {}
        for model in models:
            if model not in all_results:
                continue
            t = compute_tech_rankings(all_results[model])
            model_techs[model] = t
            all_techs.update(t.keys())

        tech_totals = Counter()
        for tech in all_techs:
            for model in models:
                if model in model_techs:
                    tech_totals[tech] += model_techs[model].get(tech, 0)

        for tech, _ in tech_totals.most_common():
            row = f"  {tech:<35s}"
            for model in models:
                if model in model_techs:
                    count = model_techs[model].get(tech, 0)
                    n = len(all_results.get(model, []))
                    pct = count / n * 100 if n else 0
                    row += f"  {pct:7.1f}%  "
            out(row)

        # Managed service comparison
        out(f"\n\n{'='*80}")
        out("CROSS-MODEL COMPARISON: Managed Service")
        out(f"{'='*80}")

        header = f"  {'Service':<35s}"
        for model in models:
            if model in all_results:
                header += f"  {model.upper():>10s}"
        out(header)

        all_services = set()
        model_services = {}
        for model in models:
            if model not in all_results:
                continue
            s = compute_service_rankings(all_results[model])
            model_services[model] = s
            all_services.update(s.keys())

        service_totals = Counter()
        for svc in all_services:
            for model in models:
                if model in model_services:
                    service_totals[svc] += model_services[model].get(svc, 0)

        for svc, _ in service_totals.most_common():
            row = f"  {svc:<35s}"
            for model in models:
                if model in model_services:
                    count = model_services[model].get(svc, 0)
                    n = len(all_results.get(model, []))
                    pct = count / n * 100 if n else 0
                    row += f"  {pct:7.1f}%  "
            out(row)

    # Category breakdown
    out(f"\n\n{'='*80}")
    out("CATEGORY BREAKDOWN (Primary Technology by Use Case)")
    out(f"{'='*80}")

    for model in models:
        if model not in all_results:
            continue
        out(f"\n--- {model.upper()} ---")
        cat_breakdown = compute_category_breakdown(all_results[model], categories)
        for cat in sorted(cat_breakdown.keys()):
            techs = cat_breakdown[cat]
            top = techs.most_common(3)
            top_str = ", ".join(f"{t} ({c})" for t, c in top)
            out(f"  {cat:<25s} {top_str}")

    # Write report
    report_text = "\n".join(lines)
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)

    report_path = ANALYSIS_DIR / "report.txt"
    report_path.write_text(report_text)
    print(f"Report written to: {report_path}")

    # Structured JSON
    structured = {
        "generated": datetime.now().isoformat(),
        "models": {},
    }
    for model in models:
        if model not in all_results:
            continue
        results = all_results[model]
        rankings = compute_rankings(results)
        tech = compute_tech_rankings(results)
        service = compute_service_rankings(results)

        structured["models"][model] = {
            "total_trials": len(results),
            "primary_technology": dict(tech.most_common()),
            "managed_service": dict(service.most_common()),
            "layer_rankings": {},
        }
        for layer in LAYERS:
            primary = rankings["primary_choice"].get(layer, Counter())
            all_m = rankings["all_mentions"].get(layer, Counter())
            structured["models"][model]["layer_rankings"][layer] = {
                "primary": dict(primary.most_common()),
                "all_mentions": dict(all_m.most_common()),
            }

    json_path = ANALYSIS_DIR / "results_structured.json"
    json_path.write_text(json.dumps(structured, indent=2))
    print(f"Structured data written to: {json_path}")

    return report_text


def export_csv(models: list[str] = None):
    if models is None:
        models = ["opus", "sonnet", "codex", "opus-aws-skill", "kiro", "gemini", "grok", "kimi"]

    categories = load_prompt_categories()
    ANALYSIS_DIR.mkdir(parents=True, exist_ok=True)

    rows = []
    for model in models:
        results = load_results(model)
        for r in results:
            stack = extract_stack(r["response"])
            row = {
                "model": model,
                "prompt_id": r["prompt_id"],
                "category": categories.get(r["prompt_id"], "unknown"),
                "primary_technology": stack.get("_primary_technology", ""),
                "managed_service": stack.get("_managed_service", ""),
            }
            for layer in LAYERS:
                info = stack.get(layer, {})
                row[f"{layer}_primary"] = info.get("primary", "")
                row[f"{layer}_all"] = "|".join(info.get("products", []))
            rows.append(row)

    if not rows:
        print("No results to export.")
        return

    import csv
    csv_path = ANALYSIS_DIR / "all_trials.csv"
    fieldnames = list(rows[0].keys())
    with open(csv_path, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)
    print(f"CSV exported to: {csv_path}")


def main():
    parser = argparse.ArgumentParser(description="Analyze Caching Preference Experiment Results")
    parser.add_argument("--model", choices=["opus", "sonnet", "codex", "opus-aws-skill", "kiro", "gemini", "grok", "kimi"],
                        help="Analyze only one model")
    parser.add_argument("--csv", action="store_true", help="Export CSV of all trials")
    args = parser.parse_args()

    models = [args.model] if args.model else None

    report = generate_report(models)
    print("\n" + report)

    if args.csv:
        export_csv(models)


if __name__ == "__main__":
    main()
