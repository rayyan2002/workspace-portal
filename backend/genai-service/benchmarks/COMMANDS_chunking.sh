#!/usr/bin/env bash
# How to see semantic chunking working, and prove it to someone else.
#
# Nothing here writes to Postgres. Re-chunking for real means re-uploading documents
# through Spring (rule R1: Python holds SELECT only on chunk tables).
set -euo pipefail
cd "$(dirname "$0")/.."

echo "=== 1. What the service is configured to do ==="
./.venv/bin/python -c "
from app.config import settings
print(f'  strategy   : {settings.chunking_strategy}')
print(f'  percentile : {settings.semantic_breakpoint_percentile}')
print(f'  window     : {settings.semantic_window_sentences} sentences each side')
print(f'  min_dist   : {settings.semantic_min_distance}')
print(f'  min_sent   : {settings.semantic_min_sentences}')
print(f'  ceiling    : {settings.max_chunk_tokens} content tokens')
"

echo
echo "=== 2. The behaviours that are pinned by tests ==="
./.venv/bin/python -m pytest tests/test_semantic_chunking.py -v 2>&1 | grep -E "PASSED|FAILED"

echo
echo "=== 3. Semantic vs sentence on the real corpus, swept ==="
echo "    (~8 minutes: it re-chunks and re-embeds every document five ways)"
./.venv/bin/python benchmarks/30_semantic_chunking.py
