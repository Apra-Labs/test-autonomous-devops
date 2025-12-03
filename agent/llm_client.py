"""
LLM Client for Autonomous DevOps Agent

Handles interaction with Anthropic Claude models with mock support for testing.
"""
import json
import logging
import os
from typing import Dict, Optional, List
from dataclasses import dataclass

# Import anthropic with fallback for testing
try:
    from anthropic import Anthropic
except ImportError:
    Anthropic = None

# Handle both package import and direct script execution
try:
    from .config import ModelConfig
except ImportError:
    from config import ModelConfig

logger = logging.getLogger(__name__)


@dataclass
class LLMResponse:
    """Structured LLM response"""
    analysis: Dict
    fix: Dict
    skill_update: Dict
    raw_response: str
    model_used: str
    tokens_used: int


class LLMClient:
    """
    Client for interacting with Claude models

    Supports both real API calls and mock mode for testing.
    """

    def __init__(self, api_key: Optional[str] = None, mock_mode: bool = False,
                 config: Optional[ModelConfig] = None, prompts_path: Optional[str] = None):
        """
        Initialize LLM client

        Args:
            api_key: Anthropic API key (required if not in mock mode)
            mock_mode: If True, return mock responses without API calls
            config: Model configuration
            prompts_path: Path to prompts.json file (defaults to agent/prompts.json)
        """
        self.mock_mode = mock_mode
        self.config = config or ModelConfig()

        # Load prompts from JSON file
        if prompts_path is None:
            # Auto-detect prompts.json location
            script_dir = os.path.dirname(os.path.abspath(__file__))
            prompts_path = os.path.join(script_dir, 'prompts.json')

        self.prompts = self._load_prompts(prompts_path)
        logger.info(f"Loaded prompts from {prompts_path}")

        if not mock_mode:
            if not api_key:
                raise ValueError("API key required when not in mock mode")
            if Anthropic is None:
                raise ImportError("anthropic package required for real API calls")
            self.client = Anthropic(api_key=api_key)
        else:
            self.client = None
            logger.info("LLM Client initialized in MOCK MODE")

    def _load_prompts(self, path: str) -> Dict:
        """
        Load prompt templates from JSON file

        Args:
            path: Path to prompts.json file

        Returns:
            Dictionary of prompt templates
        """
        try:
            with open(path, 'r') as f:
                prompts = json.load(f)
                logger.info(f"Loaded {len(prompts)} prompt templates")
                return prompts
        except FileNotFoundError:
            logger.error(f"Prompts file not found: {path}")
            raise
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in prompts file: {e}")
            raise

    def analyze_failure(self,
                       failure_context: Dict,
                       previous_attempts: List[Dict],
                       skill_knowledge: str,
                       attempt: int) -> LLMResponse:
        """
        Analyze failure and propose fix

        Args:
            failure_context: Current failure information
            previous_attempts: List of previous fix attempts
            skill_knowledge: Skill file content
            attempt: Current attempt number

        Returns:
            LLMResponse with analysis and fix proposal
        """
        model = self.config.get_model_for_attempt(attempt)

        logger.info(f"Analyzing failure with {model} (attempt {attempt})")

        prompt = self._build_prompt(failure_context, previous_attempts,
                                    skill_knowledge, attempt)

        if self.mock_mode:
            return self._mock_response(attempt, model)

        # Real API call
        response = self.client.messages.create(
            model=model,
            max_tokens=self.config.MAX_TOKENS,
            temperature=self.config.TEMPERATURE,
            messages=[{"role": "user", "content": prompt}]
        )

        # Parse response
        parsed = self._parse_response(response.content[0].text)

        return LLMResponse(
            analysis=parsed['analysis'],
            fix=parsed['fix'],
            skill_update=parsed.get('skill_update', {}),
            raw_response=response.content[0].text,
            model_used=model,
            tokens_used=response.usage.input_tokens + response.usage.output_tokens
        )

    def _build_prompt(self,
                     failure_context: Dict,
                     previous_attempts: List[Dict],
                     skill_knowledge: str,
                     attempt: int) -> str:
        """Build prompt for LLM"""

        previous_attempts_section = ""
        if previous_attempts:
            previous_attempts_section = "## 🔄 Previous Fix Attempts\n\n"
            for prev in previous_attempts:
                previous_attempts_section += f"""
### Attempt {prev['attempt_num']}
**Model:** {prev.get('model_used', 'Unknown')}
**What was tried:** {prev['fix_applied']}
**Reasoning:** {prev['reasoning']}
**Result:** ❌ FAILED

---
"""

        model_note = ""
        if attempt > self.config.SONNET_MAX_ATTEMPTS:
            model_note = f"""
⚠️ **IMPORTANT**: This is attempt {attempt}. Previous {self.config.SONNET_MAX_ATTEMPTS} attempts with Sonnet FAILED.
You are now Claude Opus - use your advanced reasoning to solve this harder problem.
"""

        prompt = f"""You are an autonomous DevOps agent fixing build failures.

{model_note}

## 📚 Skill Knowledge

{skill_knowledge[:10000]}  # Truncated for prompt size

{previous_attempts_section}

## 🔍 Current Failure

**Platform:** {failure_context.get('platform', 'Unknown')}
**Build Phase:** {failure_context.get('phase', 'Unknown')}

**Errors:**
```
{failure_context.get('errors', 'No errors extracted')}
```

**Build Log (excerpt):**
```
{failure_context.get('log_excerpt', 'No log available')[:5000]}
```

## 🎯 Your Task

{'**CRITICAL**: Previous attempts failed. Try a DIFFERENT approach.' if previous_attempts else 'Analyze and fix this failure.'}

1. **Root Cause Analysis**: What's actually broken?
2. **Fix Proposal**: Provide EXACT file changes needed
3. **Reasoning**: Why will this work{' when previous attempts failed?' if previous_attempts else '?'}
4. **Skill Update**: Should we add this to our knowledge base?

## 📤 Output Format (JSON)

```json
{{
  "analysis": {{
    "root_cause": "Clear description of what's broken",
    "why_previous_failed": "Why earlier attempts didn't work (if applicable)",
    "confidence": 0.85,
    "new_approach": "What's different about this fix"
  }},
  "fix": {{
    "description": "One-line summary of the fix",
    "files_to_change": [
      {{
        "path": "path/to/file",
        "action": "edit|create|delete",
        "content": "Full file content or changes"
      }}
    ],
    "reasoning": "Why this will work",
    "test_plan": "How to verify the fix"
  }},
  "skill_update": {{
    "needs_update": true,
    "pattern_name": "Name for this pattern",
    "content": "Markdown content to add to skill",
    "rationale": "Why this is worth documenting"
  }}
}}
```

**Important:**
- Attempt {attempt} of {self.config.ESCALATION_THRESHOLD - 1}
- Be specific and actionable
- Learn from previous failures
"""

        return prompt

    def _parse_response(self, response_text: str) -> Dict:
        """Parse JSON response from LLM"""
        # Try to extract JSON from response
        json_match = None
        if '```json' in response_text:
            # Extract from code block
            import re
            pattern = r'```json\s*(\{.*?\})\s*```'
            match = re.search(pattern, response_text, re.DOTALL)
            if match:
                json_match = match.group(1)
        else:
            # Try to find JSON object directly
            json_match = response_text

        if json_match:
            try:
                return json.loads(json_match)
            except json.JSONDecodeError as e:
                logger.error(f"Failed to parse JSON: {e}")
                logger.debug(f"Response text: {response_text[:500]}")

        # Fallback: return structured error
        return {
            'analysis': {
                'root_cause': 'Failed to parse LLM response',
                'confidence': 0.0
            },
            'fix': {
                'description': 'Manual intervention required',
                'files_to_change': [],
                'reasoning': 'Could not extract fix from LLM response'
            },
            'skill_update': {
                'needs_update': False
            }
        }

    def _mock_response(self, attempt: int, model: str) -> LLMResponse:
        """Generate mock response for testing"""
        logger.info(f"Generating MOCK response for attempt {attempt}")

        # Simulate different responses based on attempt
        if attempt == 1:
            # First attempt - simple fix
            mock_data = {
                'analysis': {
                    'root_cause': 'Missing import statement in module',
                    'confidence': 0.90,
                    'new_approach': 'Add missing import'
                },
                'fix': {
                    'description': 'Add missing import for datetime module',
                    'files_to_change': [
                        {
                            'path': 'src/main.py',
                            'action': 'edit',
                            'content': 'import datetime\nimport sys\n\nprint("Hello")'
                        }
                    ],
                    'reasoning': 'Error indicates datetime is used but not imported',
                    'test_plan': 'Run python src/main.py and verify no import errors'
                },
                'skill_update': {
                    'needs_update': True,
                    'pattern_name': 'Python Missing Import',
                    'content': '### Pattern: Missing Python Import\n**Symptom:** NameError: name X is not defined\n**Fix:** Add import statement',
                    'rationale': 'Common error pattern worth documenting'
                }
            }
        elif attempt <= 3:
            # Attempt 2-3 - more complex fix
            mock_data = {
                'analysis': {
                    'root_cause': 'Import added but module not in requirements.txt',
                    'why_previous_failed': 'Previous attempt added import but did not add dependency',
                    'confidence': 0.80,
                    'new_approach': 'Add to requirements.txt'
                },
                'fix': {
                    'description': 'Add datetime to requirements.txt',
                    'files_to_change': [
                        {
                            'path': 'requirements.txt',
                            'action': 'edit',
                            'content': 'pytest\ndatetime-utils\n'
                        }
                    ],
                    'reasoning': 'Module exists but not installed as dependency',
                    'test_plan': 'pip install -r requirements.txt && python src/main.py'
                },
                'skill_update': {
                    'needs_update': True,
                    'pattern_name': 'Missing Dependency',
                    'content': '### Pattern: Missing Dependency\n**Fix:** Add to requirements.txt or package.json',
                    'rationale': 'Follow-up to import errors'
                }
            }
        else:
            # Opus attempts (4+) - sophisticated fix
            mock_data = {
                'analysis': {
                    'root_cause': 'Environment-specific issue with Python version compatibility',
                    'why_previous_failed': 'Previous attempts addressed symptoms not root cause',
                    'confidence': 0.95,
                    'new_approach': 'Fix Python version compatibility issue'
                },
                'fix': {
                    'description': 'Use built-in datetime instead of datetime-utils',
                    'files_to_change': [
                        {
                            'path': 'src/main.py',
                            'action': 'edit',
                            'content': 'from datetime import datetime\nimport sys\n\nprint(datetime.now())'
                        },
                        {
                            'path': 'requirements.txt',
                            'action': 'edit',
                            'content': 'pytest\n'
                        }
                    ],
                    'reasoning': 'datetime is built-in, no external dependency needed',
                    'test_plan': 'Verify works on all Python versions'
                },
                'skill_update': {
                    'needs_update': True,
                    'pattern_name': 'Prefer Built-in Modules',
                    'content': '### Best Practice: Use Built-in Modules\nPrefer built-in modules over external dependencies',
                    'rationale': 'Reduces dependency complexity'
                }
            }

        return LLMResponse(
            analysis=mock_data['analysis'],
            fix=mock_data['fix'],
            skill_update=mock_data['skill_update'],
            raw_response=json.dumps(mock_data, indent=2),
            model_used=model,
            tokens_used=1000  # Mock token count
        )

    def summarize_for_pr(self,
                        original_error: str,
                        final_diff: str,
                        attempt_count: int,
                        platform: str) -> Dict:
        """
        CASE 3: Create human-friendly PR summary

        Called when build passes on autonomous-fix branch.
        LLM creates a clear explanation of the original problem and final solution.

        Args:
            original_error: The original build error from attempt 1
            final_diff: Git diff of all changes from main to fix branch
            attempt_count: Number of attempts it took
            platform: Platform where build failed

        Returns:
            Dictionary with 'title' and 'body' for PR
        """
        logger.info(f"Creating PR summary (attempt count: {attempt_count})")

        if self.mock_mode:
            return {
                'title': f'Fix {platform} build failure after {attempt_count} attempt(s)',
                'body': f'''## Problem

{original_error[:200]}...

## Solution

Applied fix after {attempt_count} attempt(s). The final changeset resolves the issue.

## Changes

```diff
{final_diff[:500]}...
```

**Mock PR summary - real LLM would provide detailed explanation**
'''
            }

        # Use prompts.json template
        template = self.prompts['summarize_for_pr']

        prompt = template['user_template'].format(
            original_error=original_error,
            final_diff=final_diff,
            attempt_count=attempt_count,
            platform=platform
        )

        # Always use Sonnet for summaries (fast and capable)
        response = self.client.messages.create(
            model=self.config.SONNET_MODEL,
            max_tokens=4096,
            temperature=0.0,
            system=template['system'],
            messages=[{"role": "user", "content": prompt}]
        )

        # Parse JSON response
        response_text = response.content[0].text
        try:
            # Extract JSON from response
            if '```json' in response_text:
                import re
                pattern = r'```json\s*(\{.*?\})\s*```'
                match = re.search(pattern, response_text, re.DOTALL)
                if match:
                    return json.loads(match.group(1))
            return json.loads(response_text)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse PR summary JSON: {e}")
            # Fallback to basic summary
            return {
                'title': f'Fix {platform} build failure',
                'body': f'Original error:\n\n```\n{original_error[:500]}\n```\n\nResolved after {attempt_count} attempts.'
            }

    def create_escalation_summary(self,
                                  original_error: str,
                                  all_attempts: List[Dict],
                                  attempt_count: int) -> Dict:
        """
        CASE 5: Summarize failures for human

        Called when agent exhausts all attempts (7+).
        LLM analyzes what was tried and suggests next steps for human.

        Args:
            original_error: The original build error
            all_attempts: List of all fix attempts with details
            attempt_count: Total number of attempts made

        Returns:
            Dictionary with escalation summary
        """
        logger.warning(f"Creating escalation summary after {attempt_count} failed attempts")

        if self.mock_mode:
            return {
                'summary': f'Autonomous agent attempted {attempt_count} fixes but could not resolve the issue.',
                'patterns': [
                    'Multiple import-related fixes attempted',
                    'Dependency installation issues persist'
                ],
                'suggested_investigation': [
                    'Check environment configuration',
                    'Verify Python version compatibility',
                    'Review platform-specific requirements'
                ],
                'next_steps': [
                    'Manual debugging required',
                    'Consider consulting platform documentation',
                    'May require custom environment setup'
                ]
            }

        # Use prompts.json template
        template = self.prompts['escalation_summary']

        # Format all attempts for prompt
        attempts_text = ""
        for i, attempt in enumerate(all_attempts, 1):
            attempts_text += f"""
### Attempt {i}
**Model:** {attempt.get('model_used', 'Unknown')}
**Fix Applied:** {attempt.get('fix_description', 'No description')}
**Reasoning:** {attempt.get('reasoning', 'No reasoning')}
**Result:** FAILED

"""

        prompt = template['user_template'].format(
            original_error=original_error,
            all_attempts=attempts_text,
            attempt_count=attempt_count
        )

        # Use Opus for escalation analysis (more sophisticated)
        response = self.client.messages.create(
            model=self.config.OPUS_MODEL,
            max_tokens=4096,
            temperature=0.0,
            system=template['system'],
            messages=[{"role": "user", "content": prompt}]
        )

        # Parse JSON response
        response_text = response.content[0].text
        try:
            if '```json' in response_text:
                import re
                pattern = r'```json\s*(\{.*?\})\s*```'
                match = re.search(pattern, response_text, re.DOTALL)
                if match:
                    return json.loads(match.group(1))
            return json.loads(response_text)
        except json.JSONDecodeError as e:
            logger.error(f"Failed to parse escalation summary JSON: {e}")
            # Fallback
            return {
                'summary': f'{attempt_count} automated fix attempts failed',
                'patterns': ['Unable to analyze'],
                'suggested_investigation': ['Manual review required'],
                'next_steps': ['Debug manually']
            }


class MockLLMClient(LLMClient):
    """Convenience class for mock client"""

    def __init__(self, config: Optional[ModelConfig] = None):
        super().__init__(api_key=None, mock_mode=True, config=config)
