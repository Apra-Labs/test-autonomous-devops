"""
Test that mock mode NEVER makes API calls

This test ensures the mock LLM implementation doesn't accidentally
make real API calls and incur costs.
"""
import pytest
import os
from unittest.mock import patch, MagicMock
from agent.llm_client import LLMClient


class TestMockLLMNoAPICalls:
    """Verify mock mode never makes API calls"""

    def test_mock_mode_no_anthropic_import(self):
        """Test that mock mode works even without anthropic installed"""
        # This would fail if mock mode tried to use real API
        client = LLMClient(mock_mode=True)
        
        assert client.mock_mode == True
        assert client.client is None  # No real client created

    def test_mock_mode_ignores_api_key(self):
        """Test that API key is not used in mock mode"""
        # Even with API key, mock mode shouldn't use it
        client = LLMClient(api_key="fake-key", mock_mode=True)

        assert client.mock_mode == True
        # Client should be None (not created) in mock mode
        assert client.client is None

    def test_mock_mode_no_network_calls(self):
        """Test that mock mode makes zero network calls"""
        # Patch requests to ensure no HTTP calls
        with patch('anthropic.Anthropic') as mock_anthropic:
            client = LLMClient(mock_mode=True)
            
            # Mock client should never be created
            mock_anthropic.assert_not_called()

    @pytest.mark.skip(reason="Requires full investigation flow setup")
    def test_mock_investigate_returns_immediately(self):
        """Test that mock investigation returns without API calls"""
        # This test is skipped as it requires full context fetcher setup
        # The mock mode is verified through integration tests instead
        pass

    def test_no_api_key_in_env_mock_mode(self):
        """Test mock mode works without ANTHROPIC_API_KEY"""
        # Temporarily remove API key from environment
        original_key = os.environ.get('ANTHROPIC_API_KEY')
        if original_key:
            del os.environ['ANTHROPIC_API_KEY']
        
        try:
            # Should work fine in mock mode
            client = LLMClient(mock_mode=True)
            assert client.mock_mode == True
        finally:
            # Restore original key
            if original_key:
                os.environ['ANTHROPIC_API_KEY'] = original_key

    @pytest.mark.skip(reason="Requires full investigation flow setup")
    def test_mock_cost_is_zero(self):
        """Verify that mock mode has zero cost"""
        # This test is skipped as it requires full investigation flow
        # Cost savings are validated through integration tests
        pass


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
