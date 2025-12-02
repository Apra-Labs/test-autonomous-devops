# Autonomous DevOps Agent - Testing Guide

## Test Coverage

This test repository provides comprehensive testing for the autonomous agent system before integration with real projects.

### What's Tested

#### 1. Model Switching Logic ✅
**File:** `tests/test_model_switching.py`

Tests that verify:
- Sonnet used for attempts 1-4
- Opus used for attempts 5-6
- Error raised for attempt 7+ (should escalate)
- Custom threshold configuration works

**Run:** `pytest tests/test_model_switching.py -v`

#### 2. Escalation Logic ✅
**File:** `tests/test_model_switching.py::TestEscalationLogic`

Tests that verify:
- No escalation for attempts 1-6
- Escalation triggered at attempt 7
- Custom escalation thresholds work

**Run:** `pytest tests/test_model_switching.py::TestEscalationLogic -v`

#### 3. Agent Orchestration ✅
**File:** `tests/test_agent.py`

Tests that verify:
- Agent initialization with mock mode
- Attempt detection from environment
- Failure log parsing
- Complete agent workflow
- Skill updates
- Result serialization

**Run:** `pytest tests/test_agent.py -v`

#### 4. Git Operations ✅
**File:** `agent/git_operations.py`

Mock-able Git operations:
- Branch creation (`autonomous-fix-{id}/attempt-{n}`)
- File changes (create/edit/delete)
- Structured commits with history
- PR creation with labels
- Previous attempt loading

#### 5. LLM Client ✅
**File:** `agent/llm_client.py`

Mock-able LLM client:
- Model selection based on attempt
- Prompt building with previous attempts
- Response parsing
- Mock responses for testing

## Running All Tests

```bash
# Quick test run
pytest tests/ -v

# With coverage
./run_tests.sh

# Specific test class
pytest tests/test_model_switching.py::TestModelSwitching -v

# Specific test method
pytest tests/test_agent.py::TestAgentRun::test_agent_run_attempt_1_mock -v
```

## Test Scenarios

### Scenario 1: First Attempt Success
```bash
python agent/autonomous_agent.py \
    --failure-log test-builds/python-import-error/build.log \
    --fix-id "scenario-1" \
    --platform "test" \
    --attempt 1 \
    --mock-mode

# Expected:
# - Uses Sonnet model
# - Creates autonomous-fix-scenario-1/attempt-1 branch
# - Applies fix
# - Creates PR
# - Updates skill
```

### Scenario 2: Multiple Attempts with Sonnet
```bash
# Simulate attempt 3 (still using Sonnet)
python agent/autonomous_agent.py \
    --failure-log test-builds/python-import-error/build.log \
    --fix-id "scenario-2" \
    --platform "test" \
    --attempt 3 \
    --mock-mode

# Expected:
# - Uses Sonnet model
# - Loads 2 previous attempts from git history
# - Creates attempt-3 branch
# - Learns from previous attempts
```

### Scenario 3: Switch to Opus
```bash
# Simulate attempt 5 (switches to Opus)
python agent/autonomous_agent.py \
    --failure-log test-builds/json-syntax-error/build.log \
    --fix-id "scenario-3" \
    --platform "test" \
    --attempt 5 \
    --mock-mode

# Expected:
# - Uses Opus model (more powerful)
# - Loads 4 previous attempts
# - Prompt emphasizes trying different approach
# - More sophisticated fix proposed
```

### Scenario 4: Escalation
```bash
# Simulate attempt 7 (escalates)
python agent/autonomous_agent.py \
    --failure-log test-builds/python-import-error/build.log \
    --fix-id "scenario-4" \
    --platform "test" \
    --attempt 7 \
    --mock-mode

# Expected:
# - Skips LLM analysis
# - Creates GitHub issue
# - Summarizes all 6 previous attempts
# - Returns escalated result
```

## Verifying Configuration

### Test Model Selection
```python
from agent.config import ModelConfig

config = ModelConfig()

# Test boundaries
assert config.get_model_for_attempt(1) == config.SONNET_MODEL
assert config.get_model_for_attempt(4) == config.SONNET_MODEL
assert config.get_model_for_attempt(5) == config.OPUS_MODEL
assert config.get_model_for_attempt(6) == config.OPUS_MODEL

# Test escalation
assert not config.should_escalate(6)
assert config.should_escalate(7)

print("✅ Configuration verified")
```

### Test Branch Naming
```python
from agent.config import GitConfig

config = GitConfig()

# Test branch names
branch = config.format_branch_name("12345", 3)
assert branch == "autonomous-fix-12345/attempt-3"

# Test labels
labels = config.format_labels("12345", 2, "linux", high_confidence=True)
assert "autonomous-fix-12345" in labels
assert "attempt-2" in labels
assert "platform-linux" in labels
assert "high-confidence" in labels

print("✅ Git configuration verified")
```

## Mock vs Real Testing

### Mock Mode (Default for Testing)
✅ Fast (no API calls)
✅ Free (no API costs)
✅ Deterministic (same inputs → same outputs)
✅ Safe (no actual Git operations)

**Use for:**
- Unit tests
- Integration tests
- CI/CD testing
- Development

### Real Mode (For Integration Testing)
⚠️ Slow (API calls take time)
⚠️ Costs money (API usage)
⚠️ Non-deterministic (LLM responses vary)
⚠️ Requires credentials

**Use for:**
- Final validation before production
- Testing with real LLM responses
- Verifying actual Git/GitHub operations

## Test Build Failures

The repository includes simple, fast-failing test builds:

### 1. Python Import Error
**Location:** `test-builds/python-import-error/`
**Error:** Missing `import datetime`
**Expected Fix:** Add import statement
**Confidence:** HIGH (0.90)

### 2. JSON Syntax Error
**Location:** `test-builds/json-syntax-error/`
**Error:** Missing comma in JSON
**Expected Fix:** Add comma
**Confidence:** HIGH (0.95)

### 3. Custom Test Builds
You can add your own test builds:

```bash
mkdir test-builds/my-custom-failure/
echo "ERROR: My test error" > test-builds/my-custom-failure/build.log

python agent/autonomous_agent.py \
    --failure-log test-builds/my-custom-failure/build.log \
    --fix-id "custom-test" \
    --platform "test" \
    --mock-mode
```

## Continuous Integration

To test in CI:

```yaml
# .github/workflows/test-agent.yml
name: Test Autonomous Agent

on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v4
        with:
          python-version: '3.11'

      - name: Install dependencies
        run: pip install -r requirements.txt

      - name: Run tests
        run: pytest tests/ --cov=agent --cov-report=xml

      - name: Run examples
        run: ./example_run.sh
```

## Debugging Tests

### Verbose Output
```bash
pytest tests/ -v -s  # -s shows print statements
```

### Debug Single Test
```bash
pytest tests/test_agent.py::TestAgentRun::test_agent_run_attempt_1_mock -v -s --pdb
```

### Check Test Coverage
```bash
pytest tests/ --cov=agent --cov-report=html
open htmlcov/index.html
```

## Next Steps

1. ✅ Verify all tests pass: `./run_tests.sh`
2. ✅ Run examples: `./example_run.sh`
3. ✅ Test with custom failures
4. ✅ Modify config and verify behavior changes
5. 🚀 Integrate with real project (ApraPipes)

## Common Issues

### Import Errors
```bash
# Fix: Install dependencies
pip install -r requirements.txt
```

### Tests Fail Due to Path Issues
```bash
# Fix: Run from repository root
cd /path/to/autonomous-devops-test
pytest tests/
```

### Mock Mode Not Working
```bash
# Verify mock mode is enabled
python -c "from agent.llm_client import MockLLMClient; print('✅ Mock mode available')"
```

## Success Criteria

Before integrating with real projects, ensure:

- [ ] All unit tests pass
- [ ] Model switching works correctly (Sonnet → Opus)
- [ ] Escalation triggers at attempt 7
- [ ] Agent can parse failure logs
- [ ] Branch naming follows convention
- [ ] PR creation works in mock mode
- [ ] Skill updates work
- [ ] Previous attempts are loaded correctly
- [ ] Configuration is easily customizable

Run: `./run_tests.sh && ./example_run.sh` to verify all criteria.
