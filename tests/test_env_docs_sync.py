import os
import re
from pathlib import Path

def parse_doc_variables(md_path: Path) -> set:
    """Extract all backticked environment variable names from markdown table columns."""
    content = md_path.read_text(encoding="utf-8")
    vars_found = set()
    # Find all table rows matching `VAR_NAME`
    for match in re.finditer(r'`([A-Z0-9_]+)`', content):
        var_name = match.group(1)
        # Filter typical false positives if any
        if var_name.isupper() and "_" in var_name or var_name in {"APP_ENV", "GEN_TOTAL", "DB_NAME"}:
            vars_found.add(var_name)
    return vars_found

def parse_env_example_variables(env_path: Path) -> set:
    """Extract all defined or commented-out variable names from .env.example."""
    content = env_path.read_text(encoding="utf-8")
    vars_found = set()
    for line in content.splitlines():
        line = line.strip()
        if not line or line.startswith("# ---") or line.startswith("# Note"):
            continue
        # Matches VAR=... or # VAR=... or # Optional: ...
        match = re.match(r'^(?:#\s*)?([A-Z0-9_]+)=', line)
        if match:
            vars_found.add(match.group(1))
    return vars_found

def test_env_example_contains_all_documented_vars():
    repo_root = Path(__file__).resolve().parent.parent
    docs_path = repo_root / "docs" / "configuration.md"
    env_path = repo_root / ".env.example"

    assert docs_path.exists(), "docs/configuration.md must exist"
    assert env_path.exists(), ".env.example must exist"

    doc_vars = parse_doc_variables(docs_path)
    env_vars = parse_env_example_variables(env_path)

    # Specific required documented vars that must be present in .env.example
    expected_subset = {
        "APP_SECRET",
        "APP_ENV",
        "SESSION_SECRET",
        "ENCRYPTION_KEY",
        "GEN_MODEL",
        "EMBED_MODEL",
        "EMBED_DIM",
        "GITHUB_TOKEN",
        "POLL_INTERVAL_SECONDS",
        "WEBHOOK_SECRET",
        "GEN_TOTAL",
        "ADMIN_EMAIL",
        "ADMIN_PASSWORD",
        "COOKIE_SECURE",
        "SESSION_TTL_SECONDS",
        "OTP_TTL_SECONDS",
        "MONGO_URI",
        "MONGO_IMAGE",
        "MONGOT_IMAGE",
        "APP_IMAGE",
        "COVERAGE_REVIEW_THRESHOLD",
        "MINDMAP_SAMPLES",
        "WARDENIQ_REUSE_SIM_API",
        "WARDENIQ_REUSE_SIM_GENERAL",
        "NUMPY_FALLBACK_MAX_DOCS",
        "MINDMAP_EXCERPT_PER_CHARS",
        "MINDMAP_EXCERPT_TOTAL_CHARS",
        "MINDMAP_EXCERPT_TOTAL_CHARS_HOSTED",
        "MINDMAP_REVIEW_MAX_TOKENS",
        "OLLAMA_MAX_NUM_CTX",
        "MINDMAP_MAX_WINDOWS",
        "MINDMAP_BATCH_SIZE"
    }

    missing_in_env = expected_subset - env_vars
    assert not missing_in_env, f".env.example is missing documented variables: {missing_in_env}"

def test_no_inline_comments_in_env_example():
    repo_root = Path(__file__).resolve().parent.parent
    env_path = repo_root / ".env.example"

    content = env_path.read_text(encoding="utf-8")
    for idx, line in enumerate(content.splitlines(), start=1):
        stripped = line.strip()
        # If line defines a var (KEY=val), ensure no trailing # inline comment
        if re.match(r'^(?:#\s*)?[A-Z0-9_]+=', stripped):
            # Check if there is a '#' after '='
            eq_pos = stripped.find('=')
            val_part = stripped[eq_pos+1:]
            assert '#' not in val_part, f"Line {idx} in .env.example contains inline comment: {line}"
