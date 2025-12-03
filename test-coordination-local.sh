#!/bin/bash
# Local simulation of multi-flavor coordination
# Simulates 3 parallel flavors all hitting the same error

set -e

echo "========================================="
echo "MULTI-FLAVOR COORDINATION TEST (LOCAL)"
echo "========================================="
echo ""
echo "Simulating 3 flavors running in parallel..."
echo "Expected: Only 1 investigates, 2 skip via coordination"
echo ""

# Create temp directory for results
rm -rf /tmp/coordination-test
mkdir -p /tmp/coordination-test

# Run 3 "flavors" in parallel (background processes)
echo "Starting flavor-linux-x64..."
(cd /tmp/test-autonomous-devops && python3 agent/autonomous_agent.py \
  --branch main \
  --build-status failure \
  --failure-log test-project/error.log \
  --mock \
  --output /tmp/coordination-test/result-linux-x64.json 2>&1 \
  | grep -E "CASE|coordination|MOCK MODE" > /tmp/coordination-test/log-linux-x64.txt) &
PID1=$!

# Small delay to simulate near-simultaneous start
sleep 0.5

echo "Starting flavor-linux-arm64..."
(cd /tmp/test-autonomous-devops && python3 agent/autonomous_agent.py \
  --branch main \
  --build-status failure \
  --failure-log test-project/error.log \
  --mock \
  --output /tmp/coordination-test/result-linux-arm64.json 2>&1 \
  | grep -E "CASE|coordination|MOCK MODE" > /tmp/coordination-test/log-linux-arm64.txt) &
PID2=$!

sleep 0.5

echo "Starting flavor-windows..."
(cd /tmp/test-autonomous-devops && python3 agent/autonomous_agent.py \
  --branch main \
  --build-status failure \
  --failure-log test-project/error.log \
  --mock \
  --output /tmp/coordination-test/result-windows.json 2>&1 \
  | grep -E "CASE|coordination|MOCK MODE" > /tmp/coordination-test/log-windows.txt) &
PID3=$!

echo ""
echo "All flavors started, waiting for completion..."
wait $PID1 $PID2 $PID3

echo ""
echo "========================================="
echo "RESULTS"
echo "========================================="
echo ""

# Analyze results
investigated=0
skipped=0

for flavor in linux-x64 linux-arm64 windows; do
  result="/tmp/coordination-test/result-$flavor.json"
  if [ -f "$result" ]; then
    action=$(cat $result | python3 -c "import sys, json; print(json.load(sys.stdin).get('action_taken', 'unknown'))" 2>/dev/null || echo "error")
    echo "Flavor $flavor: action=$action"

    if [ "$action" = "coordination_skip" ]; then
      skipped=$((skipped + 1))
    elif [ "$action" = "first_failure" ]; then
      investigated=$((investigated + 1))
    fi
  else
    echo "Flavor $flavor: ERROR (no result file)"
  fi
done

echo ""
echo "Summary:"
echo "  Investigated: $investigated"
echo "  Skipped (coordinated): $skipped"
echo ""

# Verify coordination worked
if [ $investigated -eq 1 ] && [ $skipped -eq 2 ]; then
  echo "✅ SUCCESS: Coordination working!"
  echo "   - 1 flavor did LLM investigation"
  echo "   - 2 flavors skipped via coordination"
  echo "   - Cost savings: 66% (would be 85% with 7 flavors)"
  exit 0
elif [ $investigated -eq 3 ]; then
  echo "❌ COORDINATION DISABLED OR BROKEN"
  echo "   - All 3 flavors investigated independently"
  echo "   - No cost savings achieved"
  exit 1
else
  echo "⚠️  UNEXPECTED RESULT"
  echo "   - This shouldn't happen"
  exit 1
fi
