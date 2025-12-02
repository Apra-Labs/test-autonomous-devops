"""
Unit tests for autonomous agent

Tests the main agent orchestration logic.
"""
import pytest
import json
from pathlib import Path
from agent.autonomous_agent import AutonomousAgent, AgentResult
from agent.config import AgentConfig


class TestAgentInitialization:
    """Test agent initialization"""

    def test_agent_creates_with_default_config(self):
        """Agent should initialize with default config"""
        agent = AutonomousAgent(mock_mode=True)
        assert agent is not None
        assert agent.config is not None
        assert agent.mock_mode is True

    def test_agent_creates_with_custom_config(self):
        """Agent should initialize with custom config"""
        config = AgentConfig.default()
        config.model.SONNET_MAX_ATTEMPTS = 2

        agent = AutonomousAgent(config=config, mock_mode=True)
        assert agent.config.model.SONNET_MAX_ATTEMPTS == 2

    def test_mock_mode_uses_mock_clients(self):
        """Mock mode should use mock LLM and Git clients"""
        agent = AutonomousAgent(mock_mode=True)
        assert agent.llm.mock_mode is True
        assert agent.git.mock_mode is True


class TestAgentAttemptDetection:
    """Test attempt number detection"""

    def test_detect_attempt_1_by_default(self):
        """Should default to attempt 1"""
        agent = AutonomousAgent(mock_mode=True)
        attempt = agent._detect_attempt_number("test-fix-123")
        assert attempt == 1

    def test_detect_attempt_from_environment(self, monkeypatch):
        """Should detect attempt from environment variable"""
        monkeypatch.setenv('ATTEMPT_NUM', '3')

        agent = AutonomousAgent(mock_mode=True)
        attempt = agent._detect_attempt_number("test-fix-123")
        assert attempt == 3


class TestAgentFailureLogParsing:
    """Test failure log parsing"""

    def test_parse_simple_error_log(self):
        """Should extract errors from log content"""
        agent = AutonomousAgent(mock_mode=True)

        log_content = """
Building project...
Compiling main.py...
ERROR: import error in main.py
Traceback (most recent call last):
  File "main.py", line 5
    import nonexistent_module
ModuleNotFoundError: No module named 'nonexistent_module'
Build failed with 1 error
"""

        failure_context = agent._parse_failure_log(log_content, "linux")

        assert failure_context['platform'] == 'linux'
        assert len(failure_context['errors']) > 0
        assert any('ERROR' in err or 'error' in err for err in failure_context['errors'])
        assert any('ModuleNotFoundError' in err for err in failure_context['errors'])

    def test_parse_log_from_file(self, tmp_path):
        """Should parse log from file path"""
        agent = AutonomousAgent(mock_mode=True)

        # Create temp log file
        log_file = tmp_path / "build.log"
        log_file.write_text("ERROR: build failed\nSome other line\nFAILED: test xyz")

        failure_context = agent._parse_failure_log(str(log_file), "windows")

        assert failure_context['platform'] == 'windows'
        assert len(failure_context['errors']) >= 2


class TestAgentRun:
    """Test main agent run logic"""

    def test_agent_run_attempt_1_mock(self, tmp_path):
        """Test agent run on attempt 1 in mock mode"""
        agent = AutonomousAgent(mock_mode=True)

        # Create simple failure log
        log_file = tmp_path / "failure.log"
        log_file.write_text("ERROR: Import error\nModuleNotFoundError: datetime")

        result = agent.run(
            failure_log=str(log_file),
            fix_id="test-123",
            platform="test",
            attempt=1
        )

        assert result.success is True
        assert result.attempt == 1
        assert "sonnet" in result.model_used.lower()
        assert result.action_taken in ['pr_created', 'fix_committed']
        assert result.confidence > 0

    def test_agent_run_attempt_5_switches_to_opus(self, tmp_path):
        """Test that attempt 5 uses Opus"""
        agent = AutonomousAgent(mock_mode=True)

        log_file = tmp_path / "failure.log"
        log_file.write_text("ERROR: Complex build issue")

        result = agent.run(
            failure_log=str(log_file),
            fix_id="test-456",
            platform="test",
            attempt=5
        )

        assert result.success is True
        assert result.attempt == 5
        assert "opus" in result.model_used.lower()

    def test_agent_escalates_on_attempt_7(self, tmp_path):
        """Test that attempt 7 escalates to human"""
        agent = AutonomousAgent(mock_mode=True)

        log_file = tmp_path / "failure.log"
        log_file.write_text("ERROR: Persistent failure")

        result = agent.run(
            failure_log=str(log_file),
            fix_id="test-789",
            platform="test",
            attempt=7
        )

        assert result.success is True
        assert result.action_taken == 'escalated'
        assert result.attempt == 7
        assert 'escalated' in result.fix_description.lower()


class TestAgentSkillUpdates:
    """Test skill update functionality"""

    def test_skill_update_creates_new_section(self, tmp_path):
        """Test that skill updates add content"""
        # Create skills directory in tmp
        skills_dir = tmp_path / "skills"
        skills_dir.mkdir()
        skill_file = skills_dir / "SKILL.md"
        skill_file.write_text("# Existing Skills\n\nSome content\n")

        # Create agent with tmp path
        from agent.autonomous_agent import AutonomousAgent
        agent_instance = AutonomousAgent(mock_mode=True)

        # Mock skill update
        skill_update = {
            'pattern_name': 'Test Pattern',
            'rationale': 'Testing skill updates',
            'content': '**Symptom:** Test error\n**Fix:** Test fix'
        }

        # Temporarily change skill directory
        import agent.autonomous_agent as agent_module
        from pathlib import Path
        original_file = agent_module.__file__

        # Create a temporary agent directory structure
        agent_dir = tmp_path / "agent"
        agent_dir.mkdir()
        agent_module.__file__ = str(agent_dir / "autonomous_agent.py")

        try:
            updated_content = agent_instance._update_skill(skill_update)

            assert 'Test Pattern' in updated_content
            assert 'Testing skill updates' in updated_content
            assert 'Test error' in updated_content
        finally:
            agent_module.__file__ = original_file


class TestAgentResultSerialization:
    """Test agent result serialization"""

    def test_agent_result_to_dict(self):
        """Test converting AgentResult to dictionary"""
        result = AgentResult(
            success=True,
            action_taken='pr_created',
            attempt=3,
            model_used='claude-sonnet-4-5',
            confidence=0.85,
            fix_description='Fixed import error',
            pr_url='https://github.com/test/test/pull/123',
            branch_name='autonomous-fix-123/attempt-3',
            skill_updated=True
        )

        result_dict = result.to_dict()

        assert result_dict['success'] is True
        assert result_dict['action_taken'] == 'pr_created'
        assert result_dict['attempt'] == 3
        assert result_dict['model_used'] == 'claude-sonnet-4-5'
        assert result_dict['confidence'] == 0.85
        assert result_dict['skill_updated'] is True

    def test_agent_result_to_json(self):
        """Test serializing AgentResult to JSON"""
        result = AgentResult(
            success=True,
            action_taken='escalated',
            attempt=7,
            model_used='none',
            confidence=0.0
        )

        json_str = json.dumps(result.to_dict())
        parsed = json.loads(json_str)

        assert parsed['success'] is True
        assert parsed['action_taken'] == 'escalated'
        assert parsed['attempt'] == 7


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
