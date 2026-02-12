# Lux
Fiat Lux

## Local-first agent (no paid API keys)

This repo includes a tiny CLI called `lux` that can run an **agent loop** using a **local LLM via Ollama**.

### Setup

- Install Ollama (macOS):

```bash
brew install ollama
ollama serve
ollama pull llama3.1:8b
```

- Install this package (editable):

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Sanity check

```bash
lux doctor
```

### Run (agent loop)

Dry-run (no file writes / commands):

```bash
lux run "explain what files are in this repo" --dry-run
```

With a verifier command (recommended once your repo has tests/lints):

```bash
lux run "fix failing tests" --verify "pytest -q"
```
