# Caching Preference Experiment

## What This Is

An experiment measuring which caching products AI coding agents recommend when developers ask for help. 100 diverse caching prompts are sent to 8 model configurations, and the responses are analyzed to see whether agents default to Redis, Valkey, Memcached, or something else.

## Project Structure

```
prompts/prompts.json        — 100 caching scenario prompts (25+ categories)
run_experiment.py           — Sends prompts to models, saves JSON results
analyze_results.py          — Parses results, generates rankings and reports
results/{model}/prompt_NNN.json — Raw model responses (one file per trial)
analysis/report.txt         — Human-readable analysis report
analysis/results_structured.json — Machine-readable analysis
analysis/all_trials.csv     — Per-trial CSV export
website/                    — Interactive results website
```

## Models

| Name | Runner | Notes |
|------|--------|-------|
| `opus` | Claude CLI (`claude -p --model us.anthropic.claude-opus-4-6-v1`) | Baseline Claude |
| `sonnet` | Claude CLI (`claude -p --model global.anthropic.claude-sonnet-4-6-20250514-v1:0`) | Faster Claude |
| `codex` | OpenAI Codex CLI (`codex exec`) | OpenAI's agent |
| `opus-aws-skill` | Claude CLI (same as opus) | Uses a system prompt that pre-loads AWS caching knowledge including Valkey — tests whether "skills" shift recommendations |
| `kiro` | Kiro CLI (`/Applications/Kiro CLI.app/Contents/MacOS/kiro-cli`) | Amazon's agent |
| `gemini` | Gemini CLI (`gemini -p`) | Requires `GEMINI_API_KEY` env var |
| `grok` | xAI HTTP API (`https://api.x.ai/v1/chat/completions`) | Requires `GROK_API_KEY` env var |
| `kimi` | Kimi CLI (`kimi --print`) | Moonshot's agent |

## How to Run the Experiment

### Full run (all models, all 100 prompts)
```bash
python3 run_experiment.py
```

### Single model
```bash
python3 run_experiment.py --model opus
python3 run_experiment.py --model sonnet
python3 run_experiment.py --model codex
python3 run_experiment.py --model kiro
python3 run_experiment.py --model gemini
python3 run_experiment.py --model grok
python3 run_experiment.py --model kimi
python3 run_experiment.py --model opus-aws-skill
```

### Prompt range
```bash
python3 run_experiment.py --start 1 --end 10 --model opus
```

### Resume (skip already-completed prompts)
```bash
python3 run_experiment.py --resume
```

### Parallel requests (default is 3)
```bash
python3 run_experiment.py --parallel 5
```

### Dry run
```bash
python3 run_experiment.py --dry-run
```

## How to Analyze Results

```bash
# Full report (all models)
python3 analyze_results.py

# Single model
python3 analyze_results.py --model opus

# Export CSV
python3 analyze_results.py --csv
```

## Environment Requirements

- Python 3.10+
- `claude` CLI installed and authenticated
- `codex` CLI installed and authenticated (for codex model)
- Kiro CLI installed at `/Applications/Kiro CLI.app/` (for kiro model)
- `gemini` CLI installed + `GEMINI_API_KEY` set (for gemini model)
- `GROK_API_KEY` set (for grok model)
- `kimi` CLI installed and authenticated (for kimi model)

## How Results Work

Each trial produces a JSON file in `results/{model}/prompt_NNN.json` with:
- `model`, `model_id`, `prompt_id`, `prompt` — identifiers
- `response` — the full model response text
- `status` — `"success"` or `"error"`
- `duration_seconds` — how long the call took
- `error` — error message if failed
- `timestamp` — UTC ISO timestamp

A trial is considered complete if `status == "success"` and `len(response) > 100`. The `--resume` flag skips completed trials.

## How Analysis Works

The analyzer extracts caching product recommendations from each response using:
1. **Section parsing** — looks for markdown headers like `### Primary Technology`
2. **Keyword scoring** — counts mentions of known products (Redis, Valkey, Memcached, etc.) with section mentions weighted 10x over full-response mentions
3. **Normalization** — maps variants ("redis 7", "redis oss") to canonical names

It produces:
- Per-model rankings of primary technology, managed service, data structures, client libraries
- Cross-model comparison tables (% of trials recommending each product)
- Category breakdowns (which tech gets recommended for which use case)

## Common Tasks

### Check experiment progress
```bash
# Count completed trials per model
for model in opus sonnet codex opus-aws-skill kiro gemini grok kimi; do
  count=$(ls results/$model/prompt_*.json 2>/dev/null | wc -l)
  echo "$model: $count/100"
done
```

### Re-run failed prompts
```bash
python3 run_experiment.py --resume --model opus
```

### View a single result
```bash
cat results/opus/prompt_001.json | python3 -m json.tool
```

## Key Design Decisions

- **No code generation** — system prompt says "Do NOT write any code" to isolate product preference from implementation details
- **Clean workdir** — experiment runs from `/tmp/cachingpreference_clean_workdir` with no CLAUDE.md to prevent context contamination
- **Opinionated responses** — system prompt says "Be opinionated — pick one solution and commit to it" to force a clear recommendation
- **The opus-aws-skill variant** — tests whether giving a model an "AWS caching skill" system prompt (listing ElastiCache, MemoryDB, etc.) shifts its recommendations toward Valkey/AWS services
