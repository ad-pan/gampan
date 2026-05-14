#!/usr/bin/env bash
# record_cassettes.sh — record VCR cassettes for the integration test suite.
#
# Usage (from the gampan repo root):
#   VCR_RECORD=once bash scripts/record_cassettes.sh
#
# Requires a valid gampan auth token and a live GAM test network.
# See docs/runbook-v0.1-validation.md Steps 1-10 before running.
#
# The cassettes are written to tests/integration/cassettes/.
# Commit them afterwards so offline CI can replay them.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

VCR_RECORD="${VCR_RECORD:-once}" \
  uv run pytest tests/integration/ -v -m e2e --tb=short "$@"
