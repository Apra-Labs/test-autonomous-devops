# Comprehensive Test Scenarios for Autonomous Agent

## Test Matrix

### CASE 1: First Failure on Main ✅
**Setup:** Create bug in main.py
**Expected:** Creates autonomous-fix-* branch
**Status:** Tested - Working in mock mode

### CASE 2: Retry After Failure (Multiple Attempts)
**Setup:**
1. Create complex multi-bug scenario
2. First attempt fixes only some bugs
3. Second attempt should fix remaining
**Expected:** Multiple commits on same autonomous-fix-* branch
**Test multi-turn limits:** Use bug that requires >5 file fetches

### CASE 3: Success on Fix Branch (PR Creation)
**Setup:** Push passing tests to autonomous-fix-* branch
**Expected:** Creates pull request to main
**Status:** Need to test

### CASE 4: Success on Main (Do Nothing)
**Setup:** All tests pass on main
**Expected:** Agent exits early with "do_nothing"
**Status:** Should be working (early exit in workflow)

### CASE 5: Escalation (Max Attempts Exceeded)
**Setup:** Create un-fixable bug, let attempts exceed MAX_ATTEMPTS
**Expected:** Creates escalation issue
**Status:** Need to test

## Multi-Turn Conversation Tests

### Test 1: Max Turns Limit (5 turns)
**Setup:** Create bug that LLM keeps requesting more context for
**Expected:** After 5 turns, force best guess or fail

### Test 2: File Fetching
**Setup:** Bug requiring multiple file reads
**Expected:** Each turn fetches files, conversation history accumulates

## Model Switching Tests

### Test 1: Low Confidence → Model Upgrade
**Setup:** Mock response with confidence < 0.7
**Expected:** Switches from haiku → sonnet → opus

## Multi-Flavor Coordination Tests

### Test 1: Parallel Workflow Locking
**Setup:** Simulate 7 parallel workflows (like ApraPipes)
**Expected:** Only ONE flavor gets lock, others skip investigation

### Test 2: Lock Timeout
**Setup:** One flavor holds lock for >30 minutes
**Expected:** Lock expires, other flavors can proceed

### Test 3: Shared Fix Branch
**Setup:** Multiple flavors see same error
**Expected:** All use same autonomous-fix-* branch (coordination)

## Cost Control Tests

### Test 1: Token Budget
**Expected:** Track tokens across all LLM calls, stay within budget

### Test 2: Mock Mode Verification
**Expected:** No real API calls in CI/CD (verify via logs)
# Testing coordination workflow
