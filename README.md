# Autonomous DevOps Agent - Test Repository

This is a test repository for developing and testing the autonomous DevOps agent system before integrating with ApraPipes.

## Purpose

- Test autonomous failure analysis and fixing
- Validate model switching (Sonnet → Opus)
- Test escalation logic
- Verify PR creation with skill updates
- Fast feedback loop (builds complete in seconds, not hours)

## Structure

```
autonomous-devops-test/
├── agent/                      # Core autonomous agent code
│   ├── config.py              # Configuration (models, thresholds)
│   ├── autonomous_agent.py    # Main agent logic
│   ├── git_operations.py      # Git/GitHub operations
│   ├── llm_client.py          # LLM interaction (Anthropic)
│   └── skill_manager.py       # Skill loading and updating
├── skills/                     # Test skill files (simplified)
│   ├── SKILL.md
│   └── troubleshooting.md
├── tests/                      # Unit and integration tests
│   ├── test_agent.py
│   ├── test_model_switching.py
│   ├── test_escalation.py
│   └── test_git_operations.py
├── test-builds/               # Simple failing builds for testing
│   ├── python-import-error/
│   ├── json-syntax-error/
│   └── missing-dependency/
└── requirements.txt
```

## Quick Start

```bash
# Install dependencies
pip install -r requirements.txt

# Run tests
pytest tests/ -v

# Run agent on test failure
python agent/autonomous_agent.py \
  --failure-log test-builds/python-import-error/build.log \
  --platform test \
  --attempt 1

# Run with mock mode (no actual API calls)
python agent/autonomous_agent.py --mock-mode --attempt 1
```

## Configuration

See `agent/config.py` for all configurable parameters:
- Model names and thresholds
- Max attempts before escalation
- Confidence thresholds
- Branch naming conventions
