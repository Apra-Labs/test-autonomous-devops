#!/bin/bash
# Test CASE 5: Escalation after 7 failed attempts
# Also tests model switching (haiku -> sonnet -> opus)

echo "========================================="
echo "CASE 5: ESCALATION TEST"
echo "Simulating 7 consecutive failures"
echo "========================================="
echo ""

cd /tmp/test-autonomous-devops

# Create a branch that will simulate multiple failures
TEST_BRANCH="autonomous-fix-test-escalation-$(date +%s)"

echo "Test branch: $TEST_BRANCH"
echo ""
echo "This will test:"
echo "  - Model switching: attempts 1-4 use Sonnet, 5-6 use Opus"
echo "  - Escalation: attempt 7 creates GitHub Issue"
echo ""

# We need to simulate being on the autonomous-fix branch with previous failures
# For now, let's just check what happens at attempt 7

for attempt in 1 2 3 4 5 6 7; do
  echo "========================================="
  echo "Attempt $attempt"
  echo "========================================="

  # Expected model:
  if [ $attempt -le 4 ]; then
    expected_model="sonnet"
  elif [ $attempt -le 6 ]; then
    expected_model="opus"
  else
    expected_model="escalation"
  fi

  echo "Expected: $expected_model"

  # Run agent in mock mode
  python3 agent/autonomous_agent.py \
    --branch "$TEST_BRANCH" \
    --build-status failure \
    --failure-log test-project/error.log \
    --mock-llm \
    --mock-git \
    --output "/tmp/escalation-attempt-$attempt.json" 2>&1 \
    | grep -E "CASE|Model|escalat|attempt|opus|sonnet" | head -10

  result=$(cat "/tmp/escalation-attempt-$attempt.json" | python3 -c "import sys, json; r=json.load(sys.stdin); print(f\"action={r['action_taken']}, model={r.get('model_used', 'none')}\")")
  echo "Result: $result"
  echo ""

  # Check if escalated
  if grep -q "escalat" "/tmp/escalation-attempt-$attempt.json"; then
    echo "✅ Escalation triggered at attempt $attempt"
    break
  fi
done

echo ""
echo "========================================="
echo "SUMMARY"
echo "========================================="
echo ""
echo "To properly test CASE 5, we need:"
echo "1. Simulate being on autonomous-fix branch with commit history"
echo "2. Check model selection based on attempt number"
echo "3. Verify GitHub Issue creation at attempt 7"
echo ""
echo "Current limitation: Mock git mode doesn't track previous commits"
echo "Solution: Create real git commits in test repo to track attempts"
