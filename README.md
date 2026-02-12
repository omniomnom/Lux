# Lux
Fiat Lux

## Local-first agent (no paid API keys)

This repo includes a tiny CLI called `lux` that can run an **agent loop** using a **local LLM via Ollama**.

### Setup

- Install Ollama (macOS):

```bash
brew install ollama
OLLAMA_HOST=127.0.0.1 ollama serve
ollama pull llama3.1:8b
```

- Install this package (editable):

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .
```

### Safe Ollama setup

Ollama is safe to use if you keep it local and up to date.

- **Default is already safe:** Ollama binds to `127.0.0.1` by default, so it only accepts connections from your machine. Don’t set `OLLAMA_HOST=0.0.0.0` unless you need other devices on your network to reach it (and then use a firewall or put it behind auth).
- **Force localhost (recommended):** To be explicit, start the server with:
  ```bash
  OLLAMA_HOST=127.0.0.1 ollama serve
  ```
  On macOS with the app, you can set the env before launching: `launchctl setenv OLLAMA_HOST "127.0.0.1"` then restart Ollama.
- **Keep it updated:** `brew upgrade ollama` (or update from the [official site](https://ollama.com)) so you get security patches.
- **Stick to official models:** Pull models with `ollama pull <name>` from the default library; avoid random `.gguf` files from untrusted sources.
- **Don’t expose it to the internet:** Don’t open Ollama’s port (usually 11434) to the public. If you need remote access, put it behind an authenticated reverse proxy instead of binding to `0.0.0.0`.

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
