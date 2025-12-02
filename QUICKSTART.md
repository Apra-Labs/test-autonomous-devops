# Quick Start Guide

## Installation

```bash
# Install dependencies
pip install -r requirements.txt
```

## Running Tests

```bash
# Run all unit tests
./run_tests.sh

# Run specific test file
pytest tests/test_model_switching.py -v

# Run with coverage
pytest tests/ --cov=agent --cov-report=html
```

## Running Examples

```bash
# Run all examples (mock mode - no API calls)
./example_run.sh

# Run single example
python agent/autonomous_agent.py \
    --failure-log test-builds/python-import-error/build.log \
    --fix-id "test-123" \
    --platform "test" \
    --mock-mode
```

## Key Test Scenarios

### 1. Model Switching (Sonnet → Opus)

Tests that agent correctly switches models based on attempt number:
- Attempts 1-4: Claude Sonnet 4.5
- Attempts 5-6: Claude Opus 4.5
- Attempt 7+: Escalate to human

```bash
pytest tests/test_model_switching.py::TestModelSwitching -v
```

### 2. Escalation Logic

Tests that agent escalates after max attempts:

```bash
pytest tests/test_model_switching.py::TestEscalationLogic -v
```

### 3. End-to-End Agent Run

Tests complete agent workflow in mock mode:

```bash
pytest tests/test_agent.py::TestAgentRun -v
```

## Configuration

Edit `agent/config.py` to customize:

```python
# Model switching thresholds
SONNET_MAX_ATTEMPTS = 4  # Use Sonnet for attempts 1-4
OPUS_MAX_ATTEMPTS = 6    # Use Opus for attempts 5-6
ESCALATION_THRESHOLD = 7  # Escalate after attempt 6

# Model names
SONNET_MODEL = "claude-sonnet-4-5-20250929"
OPUS_MODEL = "claude-opus-4-5-20250820"

# Branch naming
BRANCH_PREFIX = "autonomous-fix"
BRANCH_FORMAT = "{prefix}-{fix_id}/attempt-{attempt}"

# Skill update settings
AUTO_UPDATE_SKILL = True
INCLUDE_SKILL_IN_PR = True
```

## Mock Mode vs Real Mode

**Mock Mode** (recommended for testing):
- No API calls to Anthropic
- No Git/GitHub operations
- Returns simulated responses
- Fast and free

```bash
python agent/autonomous_agent.py --mock-mode ...
```

**Real Mode** (requires API keys):
- Makes actual Anthropic API calls
- Performs real Git/GitHub operations
- Requires environment variables

```bash
export ANTHROPIC_API_KEY="your-key"
export GITHUB_TOKEN="your-token"
export GITHUB_REPOSITORY="owner/repo"

python agent/autonomous_agent.py ...
```

## Verifying Model Switching

Run this test to verify correct model selection:

```bash
python -c "
from agent.config import ModelConfig

config = ModelConfig()

print('Attempt 1:', config.get_model_for_attempt(1))  # Sonnet
print('Attempt 4:', config.get_model_for_attempt(4))  # Sonnet
print('Attempt 5:', config.get_model_for_attempt(5))  # Opus
print('Attempt 6:', config.get_model_for_attempt(6))  # Opus
print('Should escalate at 7:', config.should_escalate(7))  # True
"
```

Expected output:
```
Attempt 1: claude-sonnet-4-5-20250929
Attempt 4: claude-sonnet-4-5-20250929
Attempt 5: claude-opus-4-5-20250820
Attempt 6: claude-opus-4-5-20250820
Should escalate at 7: True
```

## Next Steps

1. ✅ Run tests: `./run_tests.sh`
2. ✅ Run examples: `./example_run.sh`
3. ✅ Verify model switching logic
4. ✅ Test with real API (optional)
5. 🚀 Integrate with your CI/CD pipeline

## Integration with CI/CD

See the main README.md for instructions on integrating this agent with:
- GitHub Actions
- GitLab CI
- Jenkins
- Other CI systems

The key integration points are:
1. Detect build failures
2. Call agent with failure logs
3. Agent creates fix branch + commits
4. Agent creates PR with fix + skill updates
5. CI runs again on new branch
6. Repeat up to 6 times or escalate
