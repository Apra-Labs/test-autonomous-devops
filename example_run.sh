#!/bin/bash
# Example: Run autonomous agent on test build failures

set -e

echo "==============================================="
echo "Autonomous DevOps Agent - Example Run"
echo "==============================================="
echo ""

# Ensure we're in the right directory
cd "$(dirname "$0")"

echo "Example 1: Python Import Error (should succeed on attempt 1)"
echo "=============================================================="
python agent/autonomous_agent.py \
    --failure-log test-builds/python-import-error/build.log \
    --fix-id "example-001" \
    --platform "test" \
    --attempt 1 \
    --mock-mode \
    --output results/example-001-attempt-1.json

echo ""
echo "Result saved to: results/example-001-attempt-1.json"
cat results/example-001-attempt-1.json | python -m json.tool
echo ""

echo "==============================================="
echo ""

echo "Example 2: Simulating Attempt 5 (switches to Opus)"
echo "=================================================="
python agent/autonomous_agent.py \
    --failure-log test-builds/json-syntax-error/build.log \
    --fix-id "example-002" \
    --platform "test" \
    --attempt 5 \
    --mock-mode \
    --output results/example-002-attempt-5.json

echo ""
echo "Result saved to: results/example-002-attempt-5.json"
cat results/example-002-attempt-5.json | python -m json.tool
echo ""

echo "==============================================="
echo ""

echo "Example 3: Escalation (attempt 7)"
echo "=================================="
python agent/autonomous_agent.py \
    --failure-log test-builds/python-import-error/build.log \
    --fix-id "example-003" \
    --platform "test" \
    --attempt 7 \
    --mock-mode \
    --output results/example-003-attempt-7.json

echo ""
echo "Result saved to: results/example-003-attempt-7.json"
cat results/example-003-attempt-7.json | python -m json.tool
echo ""

echo "==============================================="
echo "All examples completed successfully!"
echo "==============================================="
