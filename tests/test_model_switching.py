"""
Unit tests for model switching logic

Tests that the agent correctly switches from Sonnet to Opus based on attempt number.
"""
import pytest
from agent.config import ModelConfig


class TestModelSwitching:
    """Test model selection based on attempt number"""

    def setup_method(self):
        """Setup test fixtures"""
        self.config = ModelConfig()

    def test_sonnet_for_attempt_1(self):
        """Should use Sonnet for attempt 1"""
        model = self.config.get_model_for_attempt(1)
        assert model == self.config.SONNET_MODEL
        assert "sonnet" in model.lower()

    def test_sonnet_for_attempts_2_to_4(self):
        """Should use Sonnet for attempts 2-4"""
        for attempt in [2, 3, 4]:
            model = self.config.get_model_for_attempt(attempt)
            assert model == self.config.SONNET_MODEL
            assert "sonnet" in model.lower()

    def test_opus_for_attempt_5(self):
        """Should switch to Opus for attempt 5"""
        model = self.config.get_model_for_attempt(5)
        assert model == self.config.OPUS_MODEL
        assert "opus" in model.lower()

    def test_opus_for_attempt_6(self):
        """Should use Opus for attempt 6"""
        model = self.config.get_model_for_attempt(6)
        assert model == self.config.OPUS_MODEL
        assert "opus" in model.lower()

    def test_error_for_attempt_7(self):
        """Should raise error for attempt 7 (should escalate instead)"""
        with pytest.raises(ValueError, match="exceeds max attempts"):
            self.config.get_model_for_attempt(7)

    def test_error_for_attempt_beyond_max(self):
        """Should raise error for attempts beyond max"""
        for attempt in [7, 8, 9, 10]:
            with pytest.raises(ValueError):
                self.config.get_model_for_attempt(attempt)

    def test_sonnet_max_attempts_config(self):
        """Test that Sonnet max attempts is configurable"""
        assert self.config.SONNET_MAX_ATTEMPTS == 4

    def test_opus_max_attempts_config(self):
        """Test that Opus max attempts is configurable"""
        assert self.config.OPUS_MAX_ATTEMPTS == 6

    def test_escalation_threshold_config(self):
        """Test that escalation threshold is configurable"""
        assert self.config.ESCALATION_THRESHOLD == 7

    def test_custom_thresholds(self):
        """Test with custom thresholds"""
        custom_config = ModelConfig()
        custom_config.SONNET_MAX_ATTEMPTS = 2
        custom_config.OPUS_MAX_ATTEMPTS = 4
        custom_config.ESCALATION_THRESHOLD = 5

        # Sonnet for 1-2
        assert custom_config.get_model_for_attempt(1) == custom_config.SONNET_MODEL
        assert custom_config.get_model_for_attempt(2) == custom_config.SONNET_MODEL

        # Opus for 3-4
        assert custom_config.get_model_for_attempt(3) == custom_config.OPUS_MODEL
        assert custom_config.get_model_for_attempt(4) == custom_config.OPUS_MODEL

        # Error for 5+
        with pytest.raises(ValueError):
            custom_config.get_model_for_attempt(5)


class TestEscalationLogic:
    """Test escalation decision logic"""

    def setup_method(self):
        """Setup test fixtures"""
        self.config = ModelConfig()

    def test_no_escalation_for_attempt_1(self):
        """Should not escalate on attempt 1"""
        assert not self.config.should_escalate(1)

    def test_no_escalation_for_attempts_2_to_6(self):
        """Should not escalate for attempts 2-6"""
        for attempt in [2, 3, 4, 5, 6]:
            assert not self.config.should_escalate(attempt)

    def test_escalation_for_attempt_7(self):
        """Should escalate on attempt 7"""
        assert self.config.should_escalate(7)

    def test_escalation_for_attempts_beyond_7(self):
        """Should escalate for attempts beyond 7"""
        for attempt in [7, 8, 9, 10]:
            assert self.config.should_escalate(attempt)

    def test_escalation_boundary(self):
        """Test exact boundary of escalation"""
        threshold = self.config.ESCALATION_THRESHOLD

        # Just before threshold
        assert not self.config.should_escalate(threshold - 1)

        # At threshold
        assert self.config.should_escalate(threshold)

        # After threshold
        assert self.config.should_escalate(threshold + 1)


class TestModelSwitchingIntegration:
    """Integration tests for model switching in context"""

    def test_typical_fix_sequence_success_on_first_try(self):
        """Test typical sequence: success on first attempt"""
        config = ModelConfig()

        # Attempt 1 with Sonnet
        attempt = 1
        assert config.get_model_for_attempt(attempt) == config.SONNET_MODEL
        assert not config.should_escalate(attempt)
        # Success - no more attempts needed

    def test_typical_fix_sequence_success_on_sonnet_retry(self):
        """Test typical sequence: success on attempt 3 (Sonnet)"""
        config = ModelConfig()

        attempts = [1, 2, 3]
        for attempt in attempts:
            model = config.get_model_for_attempt(attempt)
            assert model == config.SONNET_MODEL
            assert not config.should_escalate(attempt)
        # Success on attempt 3

    def test_typical_fix_sequence_needs_opus(self):
        """Test typical sequence: Sonnet fails, Opus succeeds"""
        config = ModelConfig()

        # Attempts 1-4 with Sonnet (all fail)
        for attempt in [1, 2, 3, 4]:
            model = config.get_model_for_attempt(attempt)
            assert model == config.SONNET_MODEL
            assert not config.should_escalate(attempt)

        # Attempt 5 switches to Opus
        model = config.get_model_for_attempt(5)
        assert model == config.OPUS_MODEL
        assert not config.should_escalate(5)
        # Success on attempt 5

    def test_typical_fix_sequence_opus_retry(self):
        """Test typical sequence: Opus needs retry"""
        config = ModelConfig()

        # Attempts 1-4 with Sonnet (fail)
        for attempt in [1, 2, 3, 4]:
            assert config.get_model_for_attempt(attempt) == config.SONNET_MODEL

        # Attempts 5-6 with Opus
        for attempt in [5, 6]:
            model = config.get_model_for_attempt(attempt)
            assert model == config.OPUS_MODEL
            assert not config.should_escalate(attempt)
        # Success on attempt 6

    def test_worst_case_escalation(self):
        """Test worst case: all attempts fail, escalate"""
        config = ModelConfig()

        # Attempts 1-4 with Sonnet
        for attempt in [1, 2, 3, 4]:
            assert config.get_model_for_attempt(attempt) == config.SONNET_MODEL
            assert not config.should_escalate(attempt)

        # Attempts 5-6 with Opus
        for attempt in [5, 6]:
            assert config.get_model_for_attempt(attempt) == config.OPUS_MODEL
            assert not config.should_escalate(attempt)

        # Attempt 7 - should escalate
        assert config.should_escalate(7)
        with pytest.raises(ValueError):
            config.get_model_for_attempt(7)


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
