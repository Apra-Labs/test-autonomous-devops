# Comprehensive Testing Guide

## Overview

This guide covers **unit tests**, **integration tests**, and **mock LLM scenarios** to thoroughly test the autonomous agent **without incurring API costs**.

**Goal:** Test all code paths, edge cases, and LLM interaction patterns using mock mode.

---

## Table of Contents

1. [Testing Philosophy](#testing-philosophy)
2. [Mock LLM Architecture](#mock-llm-architecture)
3. [Unit Tests](#unit-tests)
4. [Integration Tests](#integration-tests)
5. [Test Scenarios](#test-scenarios)
6. [Running Tests](#running-tests)
7. [Coverage Goals](#coverage-goals)

---

## Testing Philosophy

### Why Mock LLM?

```
Real API Testing:
- $0.50 per test run
- 100 tests = $50
- Slow (network latency)
- Non-deterministic
- Expensive to iterate

Mock LLM Testing:
- $0 per test run ✅
- 1000 tests = $0
- Fast (no network)
- Deterministic ✅
- Free iteration ✅
```

### What We Test

1. **Logic flows** (5 cases, retry logic, escalation)
2. **LLM interaction patterns** (multi-turn, file requests)
3. **File operations** (git, file fetching, replacements)
4. **Edge cases** (timeouts, malformed responses, budget limits)
5. **Coordination** (multi-flavor builds)

### What We Don't Test with Mocks

- Actual LLM quality (that's Anthropic's job)
- Real GitHub API (use test repo for that)
- Network failures (handled by retry logic)

---

## Mock LLM Architecture

### How It Works

```python
# Real LLM
llm_client = LLMClient(api_key=key)
# Makes actual API calls → costs money

# Mock LLM
llm_client = LLMClient(mock_mode=True)
# Returns predefined responses → free!
```

### Mock Response Types

#### 1. Simple Fix (1-turn)

```python
{
  "action": "propose_fix",
  "confidence": 0.90,
  "analysis": {
    "root_cause": "Missing import",
    "reasoning": "Error shows json not imported"
  },
  "fix": {
    "files_to_change": [{
      "path": "test.py",
      "action": "replace",
      "new_content": "import json\n..."
    }]
  }
}
```

#### 2. Multi-Turn Investigation

```python
# Turn 1: Request file
{
  "action": "need_more_context",
  "requests": [{
    "type": "file",
    "target": "src/main.py",
    "reason": "Need to see implementation"
  }]
}

# Turn 2: Propose fix
{
  "action": "propose_fix",
  ...
}
```

#### 3. Low Confidence

```python
{
  "action": "propose_fix",
  "confidence": 0.50,  # Below threshold (0.85)
  ...
}
# Agent should reject and request more context
```

### Customizable Mock Responses

```python
class CustomMockLLM(LLMClient):
    def __init__(self, custom_responses):
        super().__init__(mock_mode=True)
        self.responses = custom_responses
        self.call_count = 0

    def investigate_failure_iteratively(self, ...):
        response = self.responses[self.call_count]
        self.call_count += 1
        return response
```

---

## Unit Tests

### Test Structure

```
tests/unit/
├── test_log_extractor.py       # SmartLogExtractor
├── test_context_fetcher.py     # ContextFetcher
├── test_coordination.py        # FlavorCoordinator
├── test_git_operations.py      # GitOperations
├── test_config.py              # Configuration
└── test_llm_client.py          # LLMClient (mock mode)
```

### Example: test_log_extractor.py

```python
import pytest
from agent.log_extractor import SmartLogExtractor

def test_extract_compilation_error():
    """Test extraction of C++ compilation error"""
    log = """
    ... 1000 lines of build output ...
    src/FramesMuxer.cpp:45:10: error: 'mOutput' was not declared
    ... more output ...
    """

    extractor = SmartLogExtractor(max_excerpt_lines=500)
    context = extractor.extract_relevant_error(log, platform="linux")

    assert context['error_type'] == 'compilation_error'
    assert 'mOutput' in context['error_excerpt']
    assert context['excerpt_lines'] <= 500

def test_extract_python_import_error():
    """Test extraction of Python import error"""
    log = """
    Traceback (most recent call last):
      File "main.py", line 10, in <module>
        import json
    ModuleNotFoundError: No module named 'json'
    """

    extractor = SmartLogExtractor()
    context = extractor.extract_relevant_error(log, platform="python")

    assert context['error_type'] == 'python_import_error'
    assert 'Traceback' in context['error_excerpt']

def test_extract_from_massive_log():
    """Test handling of 50MB log file"""
    # Generate huge log
    log = "build output\n" * 1000000  # ~10MB
    log += "ERROR: Build failed\n"

    extractor = SmartLogExtractor(max_excerpt_lines=1000)
    context = extractor.extract_relevant_error(log, platform="test")

    # Should extract relevant portion, not crash
    assert context['excerpt_lines'] <= 1000
    assert 'ERROR' in context['error_excerpt']
```

### Example: test_coordination.py

```python
from agent.coordination import FlavorCoordinator

def test_first_flavor_should_analyze():
    """First failing flavor should analyze"""
    coordinator = FlavorCoordinator(
        github_client=MockGitHub(),
        repo="test/repo",
        commit_sha="abc123"
    )

    decision = coordinator.should_analyze(
        flavor="linux-x64",
        error_signature="sig123"
    )

    assert decision['should_analyze'] == True
    assert decision['reason'] == 'first_flavor'

def test_second_flavor_waits():
    """Second flavor should wait for first"""
    # Mock: issue already exists
    coordinator = FlavorCoordinator(
        github_client=MockGitHubWithExistingIssue(),
        repo="test/repo",
        commit_sha="abc123"
    )

    decision = coordinator.should_analyze(
        flavor="linux-arm64",
        error_signature="sig123"
    )

    assert decision['should_analyze'] == False
    assert decision['reason'] == 'fix_in_progress'
```

---

## Integration Tests

### Test Structure

```
tests/integration/
├── test_case_1_first_failure.py
├── test_case_2_retry.py
├── test_case_3_pr_creation.py
├── test_case_4_success.py
├── test_case_5_escalation.py
├── test_iterative_investigation.py
└── test_multi_flavor_coordination.py
```

### Example: test_case_1_first_failure.py

```python
import pytest
from agent.autonomous_agent import AutonomousAgent
from pathlib import Path

def test_case_1_simple_fix():
    """Test CASE 1: First failure on main with simple fix"""
    # Setup
    agent = AutonomousAgent(mock_mode=True)

    # Create test failure log
    log_path = Path("test-output.log")
    log_path.write_text("""
    Traceback (most recent call last):
      File "test.py", line 5
        import json
    NameError: name 'json' is not defined
    """)

    # Run agent
    result = agent.run(
        branch="main",
        build_status="failure",
        failure_log=str(log_path)
    )

    # Assertions
    assert result.success == True
    assert result.action_taken == 'first_failure'
    assert result.attempt == 1
    assert result.model_used == 'claude-sonnet-4-5-20250929'
    assert result.branch_name == 'autonomous-fix-local-*'

    # Cleanup
    log_path.unlink()

def test_case_1_multi_turn_investigation():
    """Test CASE 1 with multi-turn file requests"""
    # Custom mock that requires 3 turns
    class MultiTurnMock(AutonomousAgent):
        def __init__(self):
            super().__init__(mock_mode=True)
            self.turn_count = 0

        def _mock_llm_response(self, turn):
            if turn == 1:
                return {
                    "action": "need_more_context",
                    "requests": [{"type": "file", "target": "src/main.cpp"}]
                }
            elif turn == 2:
                return {
                    "action": "need_more_context",
                    "requests": [{"type": "file", "target": "include/main.h"}]
                }
            else:
                return {
                    "action": "propose_fix",
                    "confidence": 0.90,
                    ...
                }

    agent = MultiTurnMock()
    result = agent.run(...)

    assert agent.turn_count == 3
    assert result.success == True
```

### Example: test_iterative_investigation.py

```python
def test_low_confidence_forces_more_turns():
    """Test that low confidence triggers more investigation"""
    # Mock LLM returns low confidence first
    responses = [
        {
            "action": "propose_fix",
            "confidence": 0.60,  # Below 0.85 threshold
            ...
        },
        # Agent should request more context
        {
            "action": "need_more_context",
            ...
        },
        {
            "action": "propose_fix",
            "confidence": 0.90,  # Now high enough
            ...
        }
    ]

    agent = AgentWithCustomResponses(responses)
    result = agent.run(...)

    # Should have used 3 turns
    assert len(agent.llm_calls) == 3

def test_token_budget_exhaustion():
    """Test behavior when token budget runs out"""
    # Mock that uses all tokens
    agent = AutonomousAgent(mock_mode=True)
    agent.config.model.MAX_TOTAL_TOKENS = 5000  # Low budget

    # Each turn uses 2000 tokens
    result = agent.run(...)

    # Should stop at 2 turns (4000 tokens)
    assert agent.turns_used <= 3
    # Should force best guess
    assert "budget" in result.fix_description.lower()

def test_max_turns_reached():
    """Test that investigation stops at max turns"""
    agent = AutonomousAgent(mock_mode=True)
    agent.config.model.MAX_INVESTIGATION_TURNS = 3

    # Mock always requests more context
    # ...

    result = agent.run(...)

    assert agent.turns_used == 3
    # Should make best guess
    assert result.confidence < 0.85  # Forced guess
```

---

## Test Scenarios

Complex end-to-end scenarios simulating real-world cases.

```
tests/scenarios/
├── scenario_1_simple_import_error.py
├── scenario_2_vcpkg_dependency.py
├── scenario_3_cmake_configuration.py
├── scenario_4_regression_revert.py
├── scenario_5_multi_flavor_coordination.py
└── scenario_6_escalation_after_retries.py
```

### Scenario 1: Simple Import Error

```python
def test_scenario_simple_import():
    """
    Scenario: Python script missing import
    Expected: 1-turn fix, high confidence
    """
    # Create failing test file
    test_file = Path("test.py")
    test_file.write_text("""
def main():
    data = json.dumps({"key": "value"})
    print(data)
""")

    # Create error log
    error_log = """
Traceback (most recent call last):
  File "test.py", line 2
    data = json.dumps(...)
NameError: name 'json' is not defined
"""

    # Run agent (mock mode)
    agent = AutonomousAgent(mock_mode=True)
    result = agent.run("main", "failure", error_log)

    # Verify
    assert result.action_taken == 'first_failure'
    assert result.confidence >= 0.85

    # Check fix was applied
    fixed_content = test_file.read_text()
    assert 'import json' in fixed_content
```

### Scenario 4: Regression with Revert

```python
def test_scenario_regression_revert():
    """
    Scenario: Recent commit broke build, should revert
    Expected: LLM sees git history, proposes revert
    """
    # Setup git history
    # Commit 1: Working code
    # Commit 2: Broke something
    # Current: Failed build

    # Mock git history shows recent breaking change
    git_history = """
---COMMIT---
abc123
Developer <dev@email.com>
2 hours ago
Update dependency version

vcpkg.json | 2 +-
"""

    # Run agent
    agent = AutonomousAgent(mock_mode=True)
    # Mock should see regression in git history

    result = agent.run(...)

    # LLM should identify regression
    assert 'regression' in result.fix_description.lower()
    # May revert or fix the introduced issue
```

### Scenario 5: Multi-Flavor Coordination

```python
def test_scenario_multi_flavor():
    """
    Scenario: 7 flavors fail simultaneously
    Expected: Only first analyzes, others skip
    """
    # Simulate 7 parallel workflows
    flavors = [
        "linux-x64", "linux-arm64", "jetson",
        "windows", "wsl", "docker", "macos"
    ]

    results = []
    for flavor in flavors:
        os.environ['BUILD_FLAVOR'] = flavor
        agent = AutonomousAgent(mock_mode=True)
        result = agent.run(...)
        results.append((flavor, result))

    # First should analyze
    assert results[0][1].action_taken == 'first_failure'
    assert results[0][1].model_used != 'none'

    # Others should skip
    for flavor, result in results[1:]:
        assert result.action_taken == 'coordination_skip'
        assert result.model_used == 'none'

    # Cost calculation
    analyzing = sum(1 for _, r in results if r.action_taken == 'first_failure')
    assert analyzing == 1  # Only one analyzed
    # Saved: 6 × $0.50 = $3.00
```

---

## Running Tests

### All Tests

```bash
# Run everything
pytest tests/ -v

# With coverage
pytest tests/ --cov=agent --cov-report=html --cov-report=term

# View coverage
open htmlcov/index.html
```

### Specific Test Categories

```bash
# Unit tests only (fast)
pytest tests/unit/ -v

# Integration tests
pytest tests/integration/ -v

# Scenarios
pytest tests/scenarios/ -v

# Specific test
pytest tests/unit/test_log_extractor.py::test_extract_compilation_error -v
```

### Test Markers

```python
# In tests
@pytest.mark.unit
def test_something():
    ...

@pytest.mark.integration
def test_end_to_end():
    ...

@pytest.mark.slow
def test_large_file():
    ...
```

```bash
# Run only unit tests
pytest -m unit

# Skip slow tests
pytest -m "not slow"
```

---

## Coverage Goals

### Target Coverage

| Component | Target | Status |
|-----------|--------|--------|
| log_extractor.py | 90%+ | ⏳ |
| context_fetcher.py | 85%+ | ⏳ |
| coordination.py | 80%+ | ⏳ |
| autonomous_agent.py | 85%+ | ⏳ |
| llm_client.py | 80%+ | ⏳ |
| git_operations.py | 75%+ | ⏳ |

### Critical Paths (Must be 100%)

- ✅ CASE routing logic
- ✅ Model selection (Sonnet → Opus)
- ✅ Escalation trigger
- ✅ Coordination decision logic
- ✅ File replacement application

---

## Test Implementation Plan

### Phase 1: Unit Tests (Week 1)
- [ ] test_log_extractor.py (10 tests)
- [ ] test_context_fetcher.py (15 tests)
- [ ] test_coordination.py (12 tests)
- [ ] test_git_operations.py (10 tests)

### Phase 2: Integration Tests (Week 2)
- [ ] test_case_1_first_failure.py (8 tests)
- [ ] test_case_2_retry.py (6 tests)
- [ ] test_case_3_pr_creation.py (4 tests)
- [ ] test_iterative_investigation.py (10 tests)

### Phase 3: Scenarios (Week 3)
- [ ] 6 complex end-to-end scenarios
- [ ] Edge case scenarios
- [ ] Performance tests

### Phase 4: Coverage & Polish (Week 4)
- [ ] Achieve 85%+ coverage
- [ ] Fix flaky tests
- [ ] Add missing edge cases
- [ ] Documentation

---

## Mock Test Data

### Test Logs

Create realistic test logs in `tests/fixtures/logs/`:

```
logs/
├── python_import_error.log
├── cpp_linker_error.log
├── cmake_config_error.log
├── vcpkg_install_error.log
├── test_failure.log
└── massive_log_50mb.log
```

### Test Files

Create test projects in `tests/fixtures/projects/`:

```
projects/
├── python-simple/
│   ├── main.py (with bug)
│   └── requirements.txt
├── cpp-cmake/
│   ├── CMakeLists.txt
│   ├── src/main.cpp (with bug)
│   └── include/main.h
└── vcpkg-deps/
    ├── vcpkg.json (with issues)
    └── CMakeLists.txt
```

---

## Next Steps

1. **Start with unit tests** - Fast, isolated, builds confidence
2. **Add integration tests** - Test component interaction
3. **Create scenarios** - Realistic end-to-end cases
4. **Measure coverage** - Aim for 85%+
5. **Iterate** - Fix issues, add missing tests

**Remember: Mock mode is free - test everything!**
