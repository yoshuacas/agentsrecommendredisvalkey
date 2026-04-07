# Agents Recommend: Redis vs Valkey vs Caching Solutions

When developers ask AI coding agents to add caching to their applications, which solutions do agents recommend? Redis? Valkey? Memcached? DragonflyDB? ElastiCache? Framework-level caching?

## Hypothesis

AI coding agents are a critical distribution channel for infrastructure products. When a developer says "I need caching", the agent's recommendation determines what gets adopted. This experiment measures which caching products agents recommend across diverse real-world use cases.

## Design

- **100 prompts**: Diverse caching scenarios spanning 25+ categories (DB query caching, session stores, rate limiting, vector caching, leaderboards, distributed locks, pub/sub, etc.)
- **7+ models**: Claude Opus, Claude Sonnet, OpenAI Codex, Amazon Kiro, Google Gemini, xAI Grok, Moonshot Kimi
- **700+ total trials**: Each prompt x each model
- **Pure recommendation**: Models recommend architecture and specific products only (no code generation) to isolate product preference

## Caching Categories Measured

| Category | Example Use Case |
|----------|-----------------|
| DB Query Caching | Cache PostgreSQL/MySQL/DynamoDB query results |
| Session Store | Distributed session storage for web apps |
| Rate Limiting | API rate limiting across server clusters |
| Vector Caching | Cache embedding lookups and similarity results |
| API Response Cache | Cache third-party API or BFF responses |
| Leaderboard | Real-time sorted sets and rankings |
| Shopping Cart | Temporary fast-access cart data |
| Full-Page Cache | Server-rendered page caching |
| Pub/Sub | Real-time message broadcasting |
| Distributed Lock | Cross-process mutual exclusion |
| Real-time Analytics | Live metrics and counters |
| Feature Flags | Fast feature flag evaluation |
| Feed/Timeline | Pre-computed social feeds |
| Geospatial | Location-based queries and caching |
| Job Queue | Background task processing |
| Streaming | Event stream processing and buffering |
| ML/LLM Caching | Cache model inference results |
| Search Cache | Cache search/autocomplete results |
| Write-Behind | Buffer high-volume writes |
| Counters | High-throughput atomic counters |

## Products We're Tracking

| Product | Type |
|---------|------|
| Redis | In-memory data store |
| Valkey | Redis fork (Linux Foundation) |
| Amazon ElastiCache | Managed Redis/Valkey |
| Amazon MemoryDB | Durable Redis-compatible |
| Memcached | Simple key-value cache |
| DragonflyDB | Redis-compatible, multi-threaded |
| KeyDB | Redis fork, multi-threaded |
| Upstash | Serverless Redis |
| Momento | Serverless cache |
| Redis Cloud | Managed Redis (Redis Inc.) |
| Framework caches | Rails cache, Spring Cache, Django cache, etc. |

## Running

```bash
# Full experiment (all models, all 100 prompts)
python3 run_experiment.py

# Single model
python3 run_experiment.py --model opus

# Range of prompts
python3 run_experiment.py --start 1 --end 10 --model opus

# Resume (skip completed)
python3 run_experiment.py --resume

# Dry run (see what would execute)
python3 run_experiment.py --dry-run

# Parallel requests
python3 run_experiment.py --parallel 5
```

## Analysis

```bash
# Full report
python3 analyze_results.py

# Export CSV for spreadsheet analysis
python3 analyze_results.py --csv

# Single model
python3 analyze_results.py --model opus
```

## Output Structure

```
agentsrecommendredisvalkey/
├── prompts/
│   └── prompts.json              # 100 caching scenario prompts
├── results/
│   ├── opus/
│   │   └── prompt_001.json       # Full response + metadata
│   ├── codex/
│   ├── gemini/
│   ├── kiro/
│   ├── grok/
│   ├── kimi/
│   └── opus-aws-skill/
├── analysis/
│   ├── report.txt                # Human-readable rankings
│   ├── results_structured.json   # Machine-readable
│   └── all_trials.csv            # Per-trial CSV export
├── website/                      # Interactive results website
├── run_experiment.py             # Experiment runner
├── analyze_results.py            # Analysis & reporting
└── README.md
```

## Key Questions This Answers

1. **Do agents recommend Redis or Valkey?** When agents say "use Redis", do any recommend Valkey instead?
2. **Which managed service wins?** ElastiCache? Upstash? Redis Cloud? Momento?
3. **Does use case matter?** Do agents recommend different solutions for session caching vs leaderboards vs rate limiting?
4. **Does the model matter?** Do different AI agents have different caching preferences?
5. **How often is "Redis" the default answer?** Is it the automatic recommendation regardless of use case?
6. **When do agents NOT recommend Redis/Valkey?** What use cases get Memcached, Kafka, or framework-level caching?
7. **Do agents know about Valkey?** Since Valkey forked from Redis in 2024, do agents recommend it by name?
