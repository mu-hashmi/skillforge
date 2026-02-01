# Skillforge

Generate AI agent skills from documentation. When Claude fails a task, Skillforge auto-discovers docs, crawls them, and produces a reusable SKILL.md file.

[![PyPI version](https://badge.fury.io/py/skillforge.svg)](https://badge.fury.io/py/skillforge)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

## Installation

### Using pip (recommended)

```bash
pip install skillforge
```

### From GitHub

```bash
pip install git+https://github.com/Ranoobaba/skillforge.git
```

### From source

```bash
git clone https://github.com/Ranoobaba/skillforge.git
cd skillforge
pip install -e .
```

## Quick Start

### 1. Initialize (set up API keys)

```bash
skillforge init
```

This creates a `.env` file with your API keys:
- **ANTHROPIC_API_KEY** - Get one at https://console.anthropic.com
- **FIRECRAWL_API_KEY** - Get one at https://firecrawl.dev

### 2. Verify setup

```bash
skillforge doctor
```

### 3. Generate a skill

```bash
# Auto-discover documentation
skillforge run "use the Stripe API to create subscriptions"

# Or provide a seed URL
skillforge run "build CUDA kernels" --seed https://docs.nvidia.com/cuda
```

## Commands

| Command | Description |
|---------|-------------|
| `skillforge init` | Set up API keys interactively |
| `skillforge doctor` | Verify configuration |
| `skillforge run "task"` | Generate a skill from a task description |
| `skillforge list` | List generated skills |

## Options for `run`

```bash
skillforge run "task" [OPTIONS]

Options:
  --seed URL           Seed documentation URL (auto-discovers if omitted)
  --model MODEL        Claude model to use (default: claude-sonnet-4-20250514)
  --max-attempts N     Max teacher retries (default: 10)
  --corpus-limit N     Max pages to crawl (default: 50)
  --stealth            Use stealth proxies for anti-bot sites (9x cost)
  --fast               Speed-optimized mode for demos
  --no-sandbox         Disable sandbox validation
  -v, --verbose        Verbose output
```

## Examples

```bash
# Basic usage - auto-discovers Stripe docs
skillforge run "use the Stripe API to create subscriptions"

# With explicit seed URL
skillforge run "build CUDA kernels" --seed https://docs.nvidia.com/cuda

# Fast mode for demos (smaller corpus)
skillforge run "use Firecrawl to crawl webpages" --fast -v

# For sites with anti-bot protection
skillforge run "use the GitHub API" --stealth
```

## Output

Generated skills are saved to `skills/<skill-name>/`:

```
skills/
└── use-the-stripe-api-to-create-subscriptions/
    ├── SKILL.md           # Main skill documentation
    ├── tests.json         # Verification test cases
    └── skill_manifest.json # Metadata
```

## How It Works

1. **Config Validation** - Checks API keys
2. **Source Discovery** - Auto-discovers docs via Firecrawl search OR maps seed URL
3. **Corpus Building** - Crawls sources, saves as markdown
4. **Teacher Session** - Claude attempts the task; on failure, searches for missing info
5. **Validation** - Static analysis + sandbox checks
6. **Skill Generation** - Synthesizes SKILL.md from successful trace

## Environment Variables

You can also set API keys via environment variables instead of `.env`:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
export FIRECRAWL_API_KEY=fc-...
```

## Requirements

- Python 3.12+
- Anthropic API key
- Firecrawl API key

## License

MIT
