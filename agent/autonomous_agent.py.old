"""
Autonomous DevOps Agent - Main Entry Point

Orchestrates failure analysis, fix application, and skill updates.
"""
import argparse
import json
import logging
import os
import sys
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass, asdict

# Handle both package import and direct script execution
try:
    from .config import AgentConfig, DEFAULT_CONFIG
    from .llm_client import LLMClient
    from .git_operations import GitOperations
except ImportError:
    from config import AgentConfig, DEFAULT_CONFIG
    from llm_client import LLMClient
    from git_operations import GitOperations

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class AgentResult:
    """Result of agent execution"""
    success: bool
    action_taken: str  # 'pr_created', 'escalated', 'error'
    attempt: int
    model_used: str
    confidence: float
    fix_description: Optional[str] = None
    pr_url: Optional[str] = None
    branch_name: Optional[str] = None
    skill_updated: bool = False
    error_message: Optional[str] = None

    def to_dict(self) -> Dict:
        return asdict(self)


class AutonomousAgent:
    """
    Main autonomous agent

    Orchestrates the complete fix workflow:
    1. Detect attempt number from branch/environment
    2. Load previous attempts from git history
    3. Analyze failure with appropriate model (Sonnet/Opus)
    4. Apply fix to new branch
    5. Commit with detailed message
    6. Create PR with skill updates
    7. Or escalate to human if max attempts reached
    """

    def __init__(self,
                 config: Optional[AgentConfig] = None,
                 mock_mode: bool = False):
        """
        Initialize autonomous agent

        Args:
            config: Agent configuration
            mock_mode: If True, use mock clients (no real API/Git calls)
        """
        self.config = config or DEFAULT_CONFIG
        self.mock_mode = mock_mode

        # Initialize clients
        api_key = os.getenv('ANTHROPIC_API_KEY') if not mock_mode else None
        github_token = os.getenv('GITHUB_TOKEN') if not mock_mode else None
        github_repo = os.getenv('GITHUB_REPOSITORY') if not mock_mode else None

        self.llm = LLMClient(
            api_key=api_key,
            mock_mode=mock_mode,
            config=self.config.model
        )

        self.git = GitOperations(
            repo_path=".",
            github_token=github_token,
            github_repo=github_repo,
            mock_mode=mock_mode,
            config=self.config.git
        )

    def run(self,
            failure_log: str,
            fix_id: str,
            platform: str = "unknown",
            attempt: Optional[int] = None) -> AgentResult:
        """
        Run autonomous agent

        Args:
            failure_log: Path to failure log file or log content
            fix_id: Unique identifier for this fix sequence
            platform: Platform identifier (windows, linux, etc.)
            attempt: Attempt number (auto-detected if None)

        Returns:
            AgentResult with execution details
        """
        logger.info(f"""
╔══════════════════════════════════════════════════════════╗
║        Autonomous DevOps Agent Starting                  ║
║                                                          ║
║  Fix ID: {fix_id:<48}║
║  Platform: {platform:<46}║
║  Mock Mode: {str(self.mock_mode):<44}║
╚══════════════════════════════════════════════════════════╝
        """)

        try:
            # Step 1: Detect attempt number
            if attempt is None:
                attempt = self._detect_attempt_number(fix_id)

            logger.info(f"Attempt: {attempt}")

            # Step 2: Check if should escalate
            if self.config.model.should_escalate(attempt):
                return self._escalate_to_human(fix_id, attempt, platform)

            # Step 3: Load previous attempts
            previous_attempts = []
            if attempt > 1:
                previous_attempts = self.git.load_previous_attempts(fix_id, attempt)
                logger.info(f"Loaded {len(previous_attempts)} previous attempts")

            # Step 4: Parse failure log
            failure_context = self._parse_failure_log(failure_log, platform)

            # Step 5: Analyze with LLM
            skill_knowledge = self._load_skill_knowledge(platform)

            llm_response = self.llm.analyze_failure(
                failure_context=failure_context,
                previous_attempts=previous_attempts,
                skill_knowledge=skill_knowledge,
                attempt=attempt
            )

            logger.info(f"LLM Analysis complete (confidence: {llm_response.analysis['confidence']:.2f})")

            # Step 6: Create fix branch
            branch_info = self.git.create_fix_branch(fix_id, attempt)

            # Step 7: Apply file changes
            change_results = self.git.apply_file_changes(
                llm_response.fix['files_to_change']
            )

            # Check if all changes succeeded
            all_success = all(r['success'] for r in change_results)
            if not all_success:
                failed = [r for r in change_results if not r['success']]
                logger.error(f"Failed to apply {len(failed)} changes")
                return AgentResult(
                    success=False,
                    action_taken='error',
                    attempt=attempt,
                    model_used=llm_response.model_used,
                    confidence=llm_response.analysis['confidence'],
                    error_message=f"Failed to apply changes: {failed}"
                )

            # Step 8: Commit fix
            commit_sha = self.git.commit_fix(
                fix_id=fix_id,
                attempt=attempt,
                fix_info={
                    'analysis': llm_response.analysis,
                    'fix': llm_response.fix,
                    'model_used': llm_response.model_used
                },
                previous_attempts=previous_attempts
            )

            # Step 9: Push branch
            self.git.push_branch(branch_info.name, force=True)

            # Step 10: Update skill if needed
            skill_updated = False
            skill_update_content = None

            if (llm_response.skill_update.get('needs_update') and
                    self.config.ENABLE_SKILL_UPDATES):
                skill_update_content = self._update_skill(llm_response.skill_update)
                skill_updated = True
                logger.info("Skill updated")

            # Step 11: Create PR
            pr_info = None
            if self.config.ENABLE_PR_CREATION:
                pr_info = self.git.create_pr(
                    fix_id=fix_id,
                    attempt=attempt,
                    fix_info={
                        'analysis': llm_response.analysis,
                        'fix': llm_response.fix,
                        'model_used': llm_response.model_used
                    },
                    previous_attempts=previous_attempts,
                    skill_updates=skill_update_content,
                    platform=platform
                )

            logger.info(f"✅ Agent completed successfully")

            return AgentResult(
                success=True,
                action_taken='pr_created' if pr_info else 'fix_committed',
                attempt=attempt,
                model_used=llm_response.model_used,
                confidence=llm_response.analysis['confidence'],
                fix_description=llm_response.fix['description'],
                pr_url=pr_info.url if pr_info else None,
                branch_name=branch_info.name,
                skill_updated=skill_updated
            )

        except Exception as e:
            logger.error(f"❌ Agent failed: {e}", exc_info=True)
            return AgentResult(
                success=False,
                action_taken='error',
                attempt=attempt if attempt else 0,
                model_used='none',
                confidence=0.0,
                error_message=str(e)
            )

    def _detect_attempt_number(self, fix_id: str) -> int:
        """
        Detect current attempt number from environment or branch

        Returns:
            Attempt number (1-indexed)
        """
        # Check environment variable
        attempt_env = os.getenv('ATTEMPT_NUM')
        if attempt_env:
            return int(attempt_env)

        # Try to detect from current branch
        if not self.mock_mode and self.git.git_repo:
            branch_name = self.git.git_repo.active_branch.name
            if f"autonomous-fix-{fix_id}" in branch_name:
                import re
                match = re.search(r'attempt-(\d+)', branch_name)
                if match:
                    return int(match.group(1))

        # Default to attempt 1
        return 1

    def _parse_failure_log(self, failure_log: str, platform: str) -> Dict:
        """
        Parse failure log to extract errors

        Args:
            failure_log: Path to log file or log content
            platform: Platform identifier

        Returns:
            Failure context dictionary
        """
        # Check if it's a file path
        log_path = Path(failure_log)
        if log_path.exists():
            log_content = log_path.read_text()
        else:
            log_content = failure_log

        # Extract errors (simple heuristic)
        errors = []
        for line in log_content.split('\n'):
            if any(keyword in line.lower() for keyword in
                   ['error:', 'failed', 'exception', 'traceback']):
                errors.append(line.strip())

        return {
            'platform': platform,
            'phase': 'build',  # Could be detected from context
            'errors': errors[:20],  # Limit to first 20 errors
            'log_excerpt': log_content[:5000]  # First 5k chars
        }

    def _load_skill_knowledge(self, platform: str) -> str:
        """
        Load skill knowledge files

        Args:
            platform: Platform identifier

        Returns:
            Combined skill knowledge as string
        """
        skill_dir = Path(__file__).parent.parent / 'skills'

        if not skill_dir.exists():
            logger.warning(f"Skill directory not found: {skill_dir}")
            return "No skill knowledge available"

        knowledge = []

        # Load main skill
        main_skill = skill_dir / 'SKILL.md'
        if main_skill.exists():
            knowledge.append(main_skill.read_text())

        # Load platform-specific troubleshooting
        platform_guide = skill_dir / f'troubleshooting.{platform}.md'
        if platform_guide.exists():
            knowledge.append(platform_guide.read_text())
        elif (skill_dir / 'troubleshooting.md').exists():
            knowledge.append((skill_dir / 'troubleshooting.md').read_text())

        return '\n\n---\n\n'.join(knowledge)

    def _update_skill(self, skill_update: Dict) -> str:
        """
        Update skill files

        Args:
            skill_update: Skill update information from LLM

        Returns:
            Updated skill content
        """
        skill_dir = Path(__file__).parent.parent / 'skills'
        skill_file = skill_dir / 'SKILL.md'

        if not skill_file.exists():
            logger.warning("Skill file not found, creating new one")
            skill_file.parent.mkdir(parents=True, exist_ok=True)
            skill_file.write_text("# Autonomous DevOps Skills\n\n")

        current_content = skill_file.read_text()

        # Add new pattern to end
        new_content = skill_update['content']
        timestamp = self._get_timestamp()

        updated_section = f"""

---

## {skill_update['pattern_name']}

**Added:** {timestamp}
**Rationale:** {skill_update['rationale']}

{new_content}
"""

        updated_content = current_content + updated_section

        # Write back
        if not self.mock_mode:
            skill_file.write_text(updated_content)
            # Stage for commit
            self.git.git_repo.git.add(str(skill_file))

        return updated_section

    def _escalate_to_human(self, fix_id: str, attempt: int, platform: str) -> AgentResult:
        """
        Escalate to human after max attempts

        Args:
            fix_id: Fix identifier
            attempt: Attempt number
            platform: Platform identifier

        Returns:
            AgentResult with escalation details
        """
        logger.warning(f"⚠️  Escalating to human after {attempt - 1} attempts")

        # Load previous attempts for summary
        previous_attempts = self.git.load_previous_attempts(fix_id, attempt)

        # Create GitHub issue with summary
        issue_title = f"🚨 Build Failure: Manual Intervention Required (Fix {fix_id})"

        issue_body = f"""## Autonomous Agent Could Not Fix This Issue

**Fix ID:** {fix_id}
**Platform:** {platform}
**Attempts Made:** {attempt - 1}

## Previous Attempts

"""
        for prev in previous_attempts:
            issue_body += f"""
### Attempt {prev['attempt_num']}
- **Model:** {prev.get('model_used', 'Unknown')}
- **Fix:** {prev.get('fix_applied', 'Unknown')}
- **Reasoning:** {prev.get('reasoning', 'Unknown')}
- **Result:** ❌ Failed

"""

        issue_body += f"""

## Next Steps

1. Review previous attempts to understand what was tried
2. Analyze root cause manually
3. Apply fix and document in skill files
4. Update agent configuration if needed

## Related Branches

"""
        for i in range(1, attempt):
            branch = self.config.git.format_branch_name(fix_id, i)
            issue_body += f"- `{branch}`\n"

        # Create issue (if not in mock mode)
        if not self.mock_mode and self.git.github_repo:
            issue = self.git.github_repo.create_issue(
                title=issue_title,
                body=issue_body,
                labels=[self.config.git.LABEL_NEEDS_HUMAN, f'platform-{platform}']
            )
            issue_url = issue.html_url
            logger.info(f"Created escalation issue: {issue_url}")
        else:
            issue_url = "mock_issue_url"

        return AgentResult(
            success=True,
            action_taken='escalated',
            attempt=attempt,
            model_used='none',
            confidence=0.0,
            fix_description=f"Escalated after {attempt - 1} attempts",
            pr_url=issue_url
        )

    def _get_timestamp(self) -> str:
        """Get current timestamp"""
        from datetime import datetime
        return datetime.now().strftime('%Y-%m-%d')


def main():
    """CLI entry point"""
    parser = argparse.ArgumentParser(
        description='Autonomous DevOps Agent for Build Failure Analysis and Fixes'
    )

    parser.add_argument(
        '--failure-log',
        required=True,
        help='Path to failure log file or log content'
    )

    parser.add_argument(
        '--fix-id',
        required=True,
        help='Unique fix identifier (e.g., GitHub run ID)'
    )

    parser.add_argument(
        '--platform',
        default='unknown',
        help='Platform identifier (windows, linux, docker, etc.)'
    )

    parser.add_argument(
        '--attempt',
        type=int,
        help='Attempt number (auto-detected if not provided)'
    )

    parser.add_argument(
        '--mock-mode',
        action='store_true',
        help='Run in mock mode (no real API/Git calls)'
    )

    parser.add_argument(
        '--config-file',
        help='Path to custom config JSON file'
    )

    parser.add_argument(
        '--output',
        default='agent-result.json',
        help='Output file for agent result'
    )

    args = parser.parse_args()

    # Load config
    if args.config_file:
        # TODO: Load custom config from JSON
        config = DEFAULT_CONFIG
    else:
        config = DEFAULT_CONFIG

    # Initialize agent
    agent = AutonomousAgent(config=config, mock_mode=args.mock_mode)

    # Run agent
    result = agent.run(
        failure_log=args.failure_log,
        fix_id=args.fix_id,
        platform=args.platform,
        attempt=args.attempt
    )

    # Save result
    output_path = Path(args.output)
    output_path.write_text(json.dumps(result.to_dict(), indent=2))

    logger.info(f"Result saved to: {output_path}")

    # Print summary
    print("\n" + "=" * 60)
    print("AUTONOMOUS AGENT RESULT")
    print("=" * 60)
    print(f"Action: {result.action_taken}")
    print(f"Success: {result.success}")
    print(f"Attempt: {result.attempt}")
    print(f"Model: {result.model_used}")
    print(f"Confidence: {result.confidence:.2f}")
    if result.fix_description:
        print(f"Fix: {result.fix_description}")
    if result.pr_url:
        print(f"PR/Issue: {result.pr_url}")
    if result.error_message:
        print(f"Error: {result.error_message}")
    print("=" * 60)

    # Exit with appropriate code
    sys.exit(0 if result.success else 1)


if __name__ == '__main__':
    main()
