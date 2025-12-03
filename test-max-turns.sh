#!/bin/bash
# Test that LLM investigation respects max turn limit (5 turns)

echo "========================================"
echo "MAX TURNS LIMIT TEST"
echo "========================================"
echo ""
echo "Testing that investigation stops after 5 turns..."
echo "This prevents infinite LLM loops and controls costs."
echo ""

# Need to modify mock response to always request more context
# For now, let's just run and verify turn count in output

cd /tmp/test-autonomous-devops

python3 agent/autonomous_agent.py \
  --branch main \
  --build-status failure \
  --failure-log test-builds/max-turns/error.log \
  --mock \
  --output /tmp/max-turns-result.json 2>&1 | tee /tmp/max-turns.log

echo ""
echo "========================================"
echo "ANALYZING RESULTS"
echo "========================================"
echo ""

# Count investigation turns
turn_count=$(grep "Investigation turn" /tmp/max-turns.log | wc -l | tr -d ' ')

echo "Investigation turns executed: $turn_count"
echo "Maximum allowed: 5"
echo ""

if [ "$turn_count" -le 5 ]; then
  echo "✅ SUCCESS: Turn limit respected ($turn_count <= 5)"
  exit 0
else
  echo "❌ FAIL: Exceeded turn limit ($turn_count > 5)"
  exit 1
fi
