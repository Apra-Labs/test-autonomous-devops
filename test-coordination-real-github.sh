#!/bin/bash
# Test multi-flavor coordination with:
# - MOCK LLM (zero API costs)
# - REAL GitHub API (create real issues for locks)

set -e

echo "========================================="
echo "MULTI-FLAVOR COORDINATION TEST"
echo "Mock LLM + Real GitHub API"
echo "========================================="
echo ""

# Get token from gh CLI if not already set
if [ -z "$GITHUB_TOKEN" ]; then
  echo "Getting GitHub token from gh CLI..."
  GITHUB_TOKEN=$(gh auth token 2>/dev/null)
  if [ -z "$GITHUB_TOKEN" ]; then
    echo "❌ ERROR: Could not get GitHub token from gh CLI"
    echo "   Run: gh auth login"
    exit 1
  fi
  export GITHUB_TOKEN
fi

export GITHUB_REPOSITORY="Apra-Labs/test-autonomous-devops"

echo "This will create REAL GitHub issues in $GITHUB_REPOSITORY"
echo "for coordination lock testing. Press Ctrl+C to cancel..."
sleep 3
echo ""

# Clean up old results
rm -rf /tmp/coordination-real-test
mkdir -p /tmp/coordination-real-test

# Run 3 flavors in parallel with DIFFERENT flavor names
echo "Starting 3 parallel flavors..."
echo "Expected: Only 1 creates lock and investigates, others skip"
echo ""

# Flavor 1: linux-x64
BUILD_FLAVOR="linux-x64" python3 /tmp/test-autonomous-devops/agent/autonomous_agent.py \
  --branch main \
  --build-status failure \
  --failure-log /tmp/test-autonomous-devops/test-project/error.log \
  --mock-llm \
  --output /tmp/coordination-real-test/result-linux-x64.json \
  2>&1 | tee /tmp/coordination-real-test/log-linux-x64.txt &
PID1=$!

# Small delay
sleep 1

# Flavor 2: linux-arm64
BUILD_FLAVOR="linux-arm64" python3 /tmp/test-autonomous-devops/agent/autonomous_agent.py \
  --branch main \
  --build-status failure \
  --failure-log /tmp/test-autonomous-devops/test-project/error.log \
  --mock-llm \
  --output /tmp/coordination-real-test/result-linux-arm64.json \
  2>&1 | tee /tmp/coordination-real-test/log-linux-arm64.txt &
PID2=$!

sleep 1

# Flavor 3: windows
BUILD_FLAVOR="windows" python3 /tmp/test-autonomous-devops/agent/autonomous_agent.py \
  --branch main \
  --build-status failure \
  --failure-log /tmp/test-autonomous-devops/test-project/error.log \
  --mock-llm \
  --output /tmp/coordination-real-test/result-windows.json \
  2>&1 | tee /tmp/coordination-real-test/log-windows.txt &
PID3=$!

echo "Waiting for all flavors to complete..."
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
  result="/tmp/coordination-real-test/result-$flavor.json"
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
echo "  Skipped (coordination): $skipped"
echo ""

# Check for coordination issues created
echo "Checking GitHub for coordination lock issue..."
cd /tmp/test-autonomous-devops
lock_issues=$(gh issue list --label "autonomous-coordination" --json number,title,labels | python3 -c "import sys, json; print(len(json.load(sys.stdin)))")
echo "Coordination lock issues found: $lock_issues"
echo ""

# Verify
if [ $investigated -eq 1 ] && [ $skipped -eq 2 ]; then
  echo "✅ SUCCESS: Coordination working!"
  echo "   - 1 flavor investigated (created lock)"
  echo "   - 2 flavors skipped (saw lock)"
  echo "   - Cost savings: 66% (would be 85% with 7 flavors)"
  echo ""
  echo "GitHub Issues created for coordination testing:"
  gh issue list --label "autonomous-coordination" --json number,title --jq '.[] | "  #\(.number): \(.title)"'
  exit 0
else
  echo "❌ COORDINATION NOT WORKING"
  echo "   - Expected: 1 investigated, 2 skipped"
  echo "   - Got: $investigated investigated, $skipped skipped"
  exit 1
fi
