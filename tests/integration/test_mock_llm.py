"""
Integration tests with Mock LLM

Tests the autonomous agent with mock LLM responses to avoid API costs.
Tests all code paths, iterative investigation, and edge cases for $0.
"""
import pytest
import tempfile
import json
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock
from agent.autonomous_agent import AutonomousAgent, AgentResult
from agent.llm_client import LLMClient, LLMResponse
from agent.config import AgentConfig


class MockLLMClient:
    """Mock LLM client that returns predefined responses"""
    
    def __init__(self, responses=None):
        """
        Initialize mock LLM
        
        Args:
            responses: List of mock responses (one per turn)
        """
        self.responses = responses or []
        self.call_count = 0
        self.calls_made = []
    
    def investigate_failure_iteratively(self, error_context, previous_attempts,
                                       context_fetcher, attempt, **kwargs):
        """Return mock response"""
        self.calls_made.append({
            'error_context': error_context,
            'previous_attempts': previous_attempts,
            'attempt': attempt
        })
        
        if self.call_count < len(self.responses):
            response = self.responses[self.call_count]
            self.call_count += 1
            return response
        
        # Default: simple fix
        return LLMResponse(
            action='propose_fix',
            confidence=0.90,
            root_cause='Mock error',
            reasoning='Mock reasoning',
            fix_description='Mock fix',
            files_to_change=[{
                'path': 'test.py',
                'action': 'replace',
                'new_content': 'print("fixed")'
            }],
            skill_updates=[],
            raw_response={'mock': True}
        )


class TestMockLLMSimpleFix:
    """Test simple 1-turn fix scenarios"""

    def test_case_1_simple_fix_high_confidence(self):
        """Test CASE 1 with simple fix and high confidence"""
        # Create test error log
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            f.write("ERROR: Test error\nBuild failed\n")
            log_path = f.name
        
        try:
            # Mock LLM response
            mock_llm = MockLLMClient([
                LLMResponse(
                    action='propose_fix',
                    confidence=0.95,
                    root_cause='Simple import error',
                    reasoning='Missing import statement',
                    fix_description='Add import json',
                    files_to_change=[{
                        'path': 'test.py',
                        'action': 'replace',
                        'new_content': 'import json\nprint("fixed")\n'
                    }],
                    skill_updates=[],
                    raw_response={}
                )
            ])
            
            # Run agent with mock LLM
            with patch.object(LLMClient, 'investigate_failure_iteratively',
                            side_effect=mock_llm.investigate_failure_iteratively):
                agent = AutonomousAgent(mock_mode=False)
                
                # Mock git operations
                with patch.object(agent.git, 'create_branch'):
                    with patch.object(agent.git, 'apply_file_changes', return_value=[]):
                        with patch.object(agent.git, 'commit_changes'):
                            with patch.object(agent.git, 'push_branch'):
                                result = agent.run(
                                    branch='main',
                                    build_status='failure',
                                    failure_log=log_path
                                )
            
            # Assertions
            assert result.success == True
            assert result.action_taken == 'first_failure'
            assert result.confidence >= 0.95
            assert mock_llm.call_count == 1  # Only one LLM call
            
        finally:
            Path(log_path).unlink()

    def test_case_2_retry_after_failure(self):
        """Test CASE 2: Retry after initial fix failed"""
        # Create test error log
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            f.write("ERROR: Test error still present\n")
            log_path = f.name
        
        try:
            mock_llm = MockLLMClient([
                LLMResponse(
                    action='propose_fix',
                    confidence=0.88,
                    root_cause='Different approach needed',
                    reasoning='Previous fix was incomplete',
                    fix_description='Try alternative fix',
                    files_to_change=[{
                        'path': 'test.py',
                        'action': 'replace',
                        'new_content': 'import json\nimport sys\nprint("fixed v2")\n'
                    }],
                    skill_updates=[],
                    raw_response={}
                )
            ])
            
            with patch.object(LLMClient, 'investigate_failure_iteratively',
                            side_effect=mock_llm.investigate_failure_iteratively):
                agent = AutonomousAgent(mock_mode=False)
                
                # Simulate previous attempt
                agent.previous_attempts = [{
                    'attempt': 1,
                    'fix_description': 'First attempt',
                    'files_changed': ['test.py']
                }]
                
                with patch.object(agent.git, 'create_branch'):
                    with patch.object(agent.git, 'apply_file_changes', return_value=[]):
                        with patch.object(agent.git, 'commit_changes'):
                            with patch.object(agent.git, 'push_branch'):
                                result = agent.run(
                                    branch='autonomous-fix-local-abc123',
                                    build_status='failure',
                                    failure_log=log_path
                                )
            
            # Should be retry
            assert result.action_taken == 'retry'
            assert result.attempt == 2
            
        finally:
            Path(log_path).unlink()


class TestMockLLMIterativeInvestigation:
    """Test multi-turn iterative investigation"""

    def test_multi_turn_file_requests(self):
        """Test LLM requesting files across multiple turns"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            f.write("ERROR: Unknown error in module\n")
            log_path = f.name
        
        try:
            # Turn 1: Request file
            turn1 = LLMResponse(
                action='need_more_context',
                requests=[{
                    'type': 'file',
                    'target': 'test.py',
                    'reason': 'Need to see implementation'
                }],
                confidence=0.0,
                root_cause='',
                reasoning='',
                fix_description='',
                files_to_change=[],
                skill_updates=[],
                raw_response={}
            )
            
            # Turn 2: Request another file
            turn2 = LLMResponse(
                action='need_more_context',
                requests=[{
                    'type': 'file',
                    'target': 'lib/helper.py',
                    'reason': 'Need helper module'
                }],
                confidence=0.0,
                root_cause='',
                reasoning='',
                fix_description='',
                files_to_change=[],
                skill_updates=[],
                raw_response={}
            )
            
            # Turn 3: Propose fix
            turn3 = LLMResponse(
                action='propose_fix',
                confidence=0.92,
                root_cause='Missing function in helper',
                reasoning='After reviewing both files, found issue',
                fix_description='Add missing function',
                files_to_change=[{
                    'path': 'lib/helper.py',
                    'action': 'replace',
                    'new_content': 'def helper():\n    return True\n'
                }],
                skill_updates=[],
                raw_response={}
            )
            
            mock_llm = MockLLMClient([turn1, turn2, turn3])
            
            # Mock context fetcher to return file content
            mock_fetcher = Mock()
            mock_fetcher.fetch_requests.return_value = [
                {'type': 'file', 'content': 'file content', 'status': 'success'}
            ]
            
            with patch.object(LLMClient, 'investigate_failure_iteratively',
                            side_effect=mock_llm.investigate_failure_iteratively):
                with patch('agent.context_fetcher.ContextFetcher', return_value=mock_fetcher):
                    agent = AutonomousAgent(mock_mode=False)
                    
                    with patch.object(agent.git, 'create_branch'):
                        with patch.object(agent.git, 'apply_file_changes', return_value=[]):
                            with patch.object(agent.git, 'commit_changes'):
                                with patch.object(agent.git, 'push_branch'):
                                    result = agent.run(
                                        branch='main',
                                        build_status='failure',
                                        failure_log=log_path
                                    )
            
            # Should have called LLM 3 times
            assert mock_llm.call_count == 3
            assert result.success == True
            
        finally:
            Path(log_path).unlink()

    def test_low_confidence_triggers_more_investigation(self):
        """Test that low confidence triggers more context gathering"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            f.write("ERROR: Complex error\n")
            log_path = f.name
        
        try:
            # Turn 1: Low confidence fix
            turn1 = LLMResponse(
                action='propose_fix',
                confidence=0.60,  # Below threshold (0.85)
                root_cause='Uncertain',
                reasoning='Not enough info',
                fix_description='Guess fix',
                files_to_change=[{
                    'path': 'test.py',
                    'action': 'replace',
                    'new_content': 'guess\n'
                }],
                skill_updates=[],
                raw_response={}
            )
            
            # Turn 2: Request more context
            turn2 = LLMResponse(
                action='need_more_context',
                requests=[{
                    'type': 'file',
                    'target': 'config.json',
                    'reason': 'Need config'
                }],
                confidence=0.0,
                root_cause='',
                reasoning='',
                fix_description='',
                files_to_change=[],
                skill_updates=[],
                raw_response={}
            )
            
            # Turn 3: High confidence fix
            turn3 = LLMResponse(
                action='propose_fix',
                confidence=0.91,
                root_cause='Config error',
                reasoning='Found in config',
                fix_description='Fix config',
                files_to_change=[{
                    'path': 'config.json',
                    'action': 'replace',
                    'new_content': '{"fixed": true}\n'
                }],
                skill_updates=[],
                raw_response={}
            )
            
            mock_llm = MockLLMClient([turn1, turn2, turn3])
            mock_fetcher = Mock()
            mock_fetcher.fetch_requests.return_value = [
                {'type': 'file', 'content': '{}', 'status': 'success'}
            ]
            
            with patch.object(LLMClient, 'investigate_failure_iteratively',
                            side_effect=mock_llm.investigate_failure_iteratively):
                with patch('agent.context_fetcher.ContextFetcher', return_value=mock_fetcher):
                    agent = AutonomousAgent(mock_mode=False)
                    
                    with patch.object(agent.git, 'create_branch'):
                        with patch.object(agent.git, 'apply_file_changes', return_value=[]):
                            with patch.object(agent.git, 'commit_changes'):
                                with patch.object(agent.git, 'push_branch'):
                                    result = agent.run(
                                        branch='main',
                                        build_status='failure',
                                        failure_log=log_path
                                    )
            
            # Should have investigated until high confidence
            assert mock_llm.call_count == 3
            assert result.confidence >= 0.85
            
        finally:
            Path(log_path).unlink()


class TestMockLLMEdgeCases:
    """Test edge cases and error scenarios"""

    def test_max_turns_exhausted(self):
        """Test behavior when max investigation turns reached"""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.log', delete=False) as f:
            f.write("ERROR: Very complex error\n")
            log_path = f.name
        
        try:
            # Always request more context (never confident)
            turn_response = LLMResponse(
                action='need_more_context',
                requests=[{'type': 'file', 'target': 'file.py', 'reason': 'need more'}],
                confidence=0.0,
                root_cause='',
                reasoning='',
                fix_description='',
                files_to_change=[],
                skill_updates=[],
                raw_response={}
            )
            
            # Repeat 10 times (more than MAX_INVESTIGATION_TURNS)
            mock_llm = MockLLMClient([turn_response] * 10)
            mock_fetcher = Mock()
            mock_fetcher.fetch_requests.return_value = [
                {'type': 'file', 'content': 'data', 'status': 'success'}
            ]
            
            with patch.object(LLMClient, 'investigate_failure_iteratively',
                            side_effect=mock_llm.investigate_failure_iteratively):
                with patch('agent.context_fetcher.ContextFetcher', return_value=mock_fetcher):
                    agent = AutonomousAgent(mock_mode=False)
                    agent.config.model.MAX_INVESTIGATION_TURNS = 3
                    
                    with patch.object(agent.git, 'create_branch'):
                        with patch.object(agent.git, 'apply_file_changes', return_value=[]):
                            with patch.object(agent.git, 'commit_changes'):
                                with patch.object(agent.git, 'push_branch'):
                                    result = agent.run(
                                        branch='main',
                                        build_status='failure',
                                        failure_log=log_path
                                    )
            
            # Should have stopped at max turns
            assert mock_llm.call_count <= 3
            
        finally:
            Path(log_path).unlink()


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
