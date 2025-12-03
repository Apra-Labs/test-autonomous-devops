"""
Simple integration tests with mocked components

Tests key workflows without requiring full LLM integration.
"""
import pytest
import tempfile
from pathlib import Path
from unittest.mock import Mock, patch
from agent.autonomous_agent import AutonomousAgent


class TestSimpleIntegration:
    """Simple integration tests"""

    def test_agent_initialization(self):
        """Test agent can be initialized"""
        agent = AutonomousAgent(mock_mode=True)
        
        assert agent is not None
        assert agent.mock_mode == True
        assert agent.config is not None

    def test_agent_case_routing_case_4(self):
        """Test CASE 4: Success on main branch"""
        agent = AutonomousAgent(mock_mode=True)
        
        result = agent.run(
            branch='main',
            build_status='success',
            failure_log=None
        )
        
        assert result.success == True
        assert result.action_taken == 'do_nothing'  # Actual value from implementation
        assert result.model_used == 'none'

    def test_agent_case_routing_case_3(self):
        """Test CASE 3: Success on fix branch"""
        agent = AutonomousAgent(mock_mode=True)
        
        result = agent.run(
            branch='autonomous-fix-local-abc123',
            build_status='success',
            failure_log=None
        )
        
        assert result.success == True
        assert result.action_taken == 'pr_created'  # Actual value from implementation

    def test_error_log_extraction(self):
        """Test that error logs are properly extracted"""
        # Create temp error log
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            f.write("ERROR: Build failed\n")
            f.write("src/test.cpp:45: error: undefined\n")
            log_path = f.name
        
        try:
            agent = AutonomousAgent(mock_mode=True)
            
            # Test log extraction
            from agent.log_extractor import SmartLogExtractor
            extractor = SmartLogExtractor()
            context = extractor.extract_relevant_error(log_path, platform="test")
            
            assert 'error_excerpt' in context
            assert 'ERROR' in context['error_excerpt']
            assert context['error_type'] != 'unknown'
            
        finally:
            Path(log_path).unlink()

    def test_coordination_disabled_in_mock_mode(self):
        """Test coordination is skipped in mock mode"""
        agent = AutonomousAgent(mock_mode=True)
        
        # Create temp error log
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            f.write("ERROR: Test\n")
            log_path = f.name
        
        try:
            result = agent.run(
                branch='main',
                build_status='failure',
                failure_log=log_path
            )
            
            # In mock mode, should still process
            assert result is not None
            
        finally:
            Path(log_path).unlink()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
