"""Claude Code CLI as an LLM backend -- an alternative to Ollama's HTTP /api/chat for callers
that want it (ingest's run_llm() opts in via LLM_WIKI_BACKEND=claude-code, see
DSI-Wiki-Ingest-Service-Class.py). Shells out to `claude -p ... --output-format json` rather
than an HTTP call, since that's the actual integration shape for a CLI coding agent -- there is
no bare chat endpoint to POST to. Real API cost per call; this is opt-in, never the default.
"""
import json
import shutil
import subprocess


class ClaudeCodeUnavailable(Exception):
    pass


def call_claude_code(prompt: str, model: str | None = None, timeout: int = 300) -> dict:
    """Runs `claude -p <prompt>` and returns a dict shaped like Ollama's /api/chat response
    (`{"message": {"content": "..."}}` on success, `{"error": "..."}` on failure) so existing
    call sites written against call_ollama()'s return shape work unchanged."""
    if shutil.which("claude") is None:
        raise ClaudeCodeUnavailable("claude CLI not found on PATH")

    cmd = ["claude", "-p", prompt, "--output-format", "json"]
    if model:
        cmd += ["--model", model]

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise TimeoutError(f"claude CLI timed out after {timeout}s") from e

    if proc.returncode != 0:
        return {"error": f"claude CLI exited {proc.returncode}: {proc.stderr[:500]}"}

    try:
        body = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        return {"error": f"claude CLI: could not parse JSON output ({e}): {proc.stdout[:300]}"}

    if body.get("is_error"):
        return {"error": body.get("result") or "claude CLI reported is_error=true"}

    return {"message": {"content": body.get("result", "")}}
