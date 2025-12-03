"""
Autonomous DevOps Agent - Main Implementation

This agent follows a 5-case architecture:
1. First failure on main/other branch
2. Retry on autonomous-fix-* branch (failure)
3. Success on autonomous-fix-* branch
4. Success on main/other branch (do nothing)
5. Escalation (too many attempts)
"""
import os
import re
import sys
import json
import logging
import argparse
from pathlib import Path
from typing import Dict, List, Optional
from dataclasses import dataclass

# Handle both package import and direct script execution
try:
    from .config import AgentConfig, DEFAULT_CONFIG
    from .llm_client import LLMClient
    from .git_operations import GitOperations
    from .log_extractor import SmartLogExtractor
    from .context_fetcher import ContextFetcher
    from .coordination import FlavorCoordinator, CoordinationConfig
except ImportError:
    from config import AgentConfig, DEFAULT_CONFIG
    from llm_client import LLMClient
    from git_operations import GitOperations
    from log_extractor import SmartLogExtractor
    from context_fetcher import ContextFetcher
    from coordination import FlavorCoordinator, CoordinationConfig

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger(__name__)


@dataclass
class AgentResult:
    """Result from agent execution"""
    success: bool
    action_taken: str  # 'first_failure', 'retry', 'pr_created', 'do_nothing', 'escalated', 'stopped', 'coordination_skip'
    attempt: int
    model_used: str
    confidence: float = 0.0
    fix_description: Optional[str] = None
    pr_url: Optional[str] = None
    branch_name: Optional[str] = None
    skill_updated: bool = False
    error_message: Optional[str] = None
    coordination_issue: Optional[int] = None  # GitHub issue number for coordination

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        return {
            'success': self.success,
            'action_taken': self.action_taken,
            'attempt': self.attempt,
            'model_used': self.model_used,
            'confidence': self.confidence,
            'fix_description': self.fix_description,
            'pr_url': self.pr_url,
            'branch_name': self.branch_name,
            'skill_updated': self.skill_updated,
            'error_message': self.error_message
        }


class AutonomousAgent:
    """
    Autonomous DevOps Agent

    Analyzes build failures and attempts to fix them automatically.
    """

    def __init__(self, config: Optional[AgentConfig] = None, mock_mode: bool = False,
                 mock_llm: bool = None, mock_git: bool = None):
        """
        Initialize agent

        Args:
            config: Agent configuration
            mock_mode: If True, use mock clients (no real API/Git calls) - DEPRECATED, use mock_llm and mock_git
            mock_llm: If True, mock LLM API calls (overrides mock_mode for LLM)
            mock_git: If True, mock Git operations (overrides mock_mode for Git)
        """
        self.config = config or DEFAULT_CONFIG
        self.mock_mode = mock_mode  # Keep for backward compatibility

        # Allow separate control of LLM vs Git mocking
        self.mock_llm = mock_llm if mock_llm is not None else mock_mode
        self.mock_git = mock_git if mock_git is not None else mock_mode

        # Initialize clients
        api_key = os.getenv('ANTHROPIC_API_KEY') if not self.mock_llm else None
        github_token = os.getenv('GITHUB_TOKEN') if not self.mock_git else None
        github_repo = os.getenv('GITHUB_REPOSITORY') if not self.mock_git else None

        self.llm = LLMClient(
            api_key=api_key,
            mock_mode=self.mock_llm,
            config=self.config.model
        )

        self.git = GitOperations(
            repo_path=".",
            github_token=github_token,
            github_repo=github_repo,
            mock_mode=self.mock_git,
            config=self.config.git
        )

        # Initialize new components for iterative investigation
        self.log_extractor = SmartLogExtractor(
            max_excerpt_lines=self.config.model.MAX_LOG_EXCERPT_LINES
        )

        # Get current commit SHA for GitHub fetching
        try:
            import subprocess
            commit_sha = subprocess.check_output(
                ['git', 'rev-parse', 'HEAD'],
                cwd='.',
                text=True
            ).strip()
        except:
            commit_sha = None

        self.context_fetcher = ContextFetcher(
            repo_root=".",
            max_file_size=self.config.model.MAX_FILE_SIZE_BYTES,
            github_repo=github_repo,
            commit_sha=commit_sha
        )

    def run(self, branch: str, build_status: str, failure_log: Optional[str] = None) -> AgentResult:
        """
        Main entry point - routes to appropriate case

        Args:
            branch: Current branch name (e.g., "main" or "autonomous-fix-123")
            build_status: 'success' or 'failure'
            failure_log: Path to failure log (if build failed)

        Returns:
            AgentResult with action taken
        """
        logger.info(f"""
╔══════════════════════════════════════════════════════════╗
║        Autonomous DevOps Agent Starting                  ║
║                                                          ║
║  Branch: {branch[:40]:<40} ║
║  Status: {build_status:<40} ║
║  Mock Mode: {str(self.mock_mode):<40} ║
╚══════════════════════════════════════════════════════════╝
        """)

        try:
            # Determine which case we're in
            is_fix_branch = branch.startswith('autonomous-fix-')

            if not is_fix_branch:
                # On main or other branch
                if build_status == 'success':
                    return self._case_4_do_nothing(branch)
                else:
                    return self._case_1_first_failure(branch, failure_log)

            else:
                # On autonomous-fix-* branch
                fix_id = self._extract_fix_id(branch)
                current_attempt = self._detect_attempt_from_commits(fix_id)

                if build_status == 'success':
                    return self._case_3_success(fix_id, current_attempt)
                else:
                    return self._case_2_retry(fix_id, current_attempt, failure_log)

        except Exception as e:
            logger.error(f"❌ Agent failed: {e}", exc_info=True)
            return AgentResult(
                success=False,
                action_taken='error',
                attempt=0,
                model_used='none',
                error_message=str(e)
            )

    def _extract_fix_id(self, branch: str) -> str:
        """
        Extract fix ID from branch name

        Args:
            branch: Branch name like "autonomous-fix-123"

        Returns:
            Fix ID like "123"
        """
        return branch.replace('autonomous-fix-', '')

    def _detect_attempt_from_commits(self, fix_id: str) -> int:
        """
        Detect current attempt number from commit messages on branch

        Looks for commits with "Attempt N:" in message

        Args:
            fix_id: Fix identifier

        Returns:
            Highest attempt number found (0 if none)
        """
        branch_name = self.config.git.format_branch_name(fix_id)
        commits = self.git.get_commits_on_branch(branch_name)

        max_attempt = 0
        for commit in commits:
            # Look for "Attempt N:" pattern
            match = re.search(r'Attempt (\d+):', commit.message)
            if match:
                attempt = int(match.group(1))
                max_attempt = max(max_attempt, attempt)

        logger.info(f"Detected attempt number: {max_attempt} from {len(commits)} commits")
        return max_attempt

    def _detect_human_commits(self, fix_id: str) -> bool:
        """
        Check if human has committed to this branch

        Args:
            fix_id: Fix identifier

        Returns:
            True if non-agent commits detected
        """
        branch_name = self.config.git.format_branch_name(fix_id)
        commits = self.git.get_commits_on_branch(branch_name)

        for commit in commits:
            if commit.author.name != "Autonomous Agent":
                logger.warning(f"Human commit detected: {commit.hexsha[:8]} by {commit.author.name}")
                return True

        return False

    def _case_4_do_nothing(self, branch: str) -> AgentResult:
        """
        CASE 4: Build passed on non-fix branch

        No action needed.
        """
        logger.info(f"✅ CASE 4: Build passed on {branch}, no action needed")

        return AgentResult(
            success=True,
            action_taken='do_nothing',
            attempt=0,
            model_used='none'
        )

    def _case_1_first_failure(self, branch: str, failure_log: str) -> AgentResult:
        """
        CASE 1: First failure on main/other branch

        Create autonomous-fix branch with first fix attempt.
        """
        logger.info(f"🔍 CASE 1: First failure on {branch}")

        # Generate fix ID (use timestamp or workflow run ID)
        fix_id = os.getenv('GITHUB_RUN_ID', f"local-{int(os.times().elapsed * 1000)}")

        # Extract error context from log using smart extractor
        error_context = self.log_extractor.extract_relevant_error(failure_log, platform="unknown")

        logger.info(f"Extracted {error_context['excerpt_lines']} lines, type: {error_context['error_type']}")

        # COORDINATION CHECK: Avoid duplicate LLM analysis across flavors
        # Note: Coordination uses GitHub API, so we only skip it if git_operations is in mock mode
        # LLM can be mocked while still using real GitHub API for coordination testing
        if CoordinationConfig.ENABLED and not self.git.mock_mode:
            flavor = os.getenv('BUILD_FLAVOR', 'unknown')
            github_repo = os.getenv('GITHUB_REPOSITORY', '')

            if flavor != 'unknown' and github_repo:
                coordinator = FlavorCoordinator(
                    github_client=self.git,
                    repo=github_repo,
                    commit_sha=self.context_fetcher.commit_sha or 'unknown'
                )

                # Generate error signature for deduplication
                error_signature = coordinator.generate_error_signature(
                    error_context.get('error_excerpt', '')
                )

                # Check if we should analyze
                coordination = coordinator.should_analyze(flavor, error_signature)

                if not coordination['should_analyze']:
                    reason = coordination['reason']
                    logger.info(f"⏭️  Skipping LLM analysis: {reason}")

                    if reason == 'fix_in_progress':
                        wait_branch = coordination.get('wait_for_branch')
                        logger.info(f"Waiting for fix from branch: {wait_branch}")
                        # TODO: Could wait and retry after fix is pushed

                    return AgentResult(
                        success=True,
                        action_taken='coordination_skip',
                        attempt=0,
                        model_used='none',
                        fix_description=f"Skipped: {reason} (cost saving!)",
                        coordination_issue=coordination.get('issue_number')
                    )

                logger.info(f"✅ Proceeding with analysis: {coordination['reason']}")

        # Use iterative investigation to analyze failure
        llm_response = self.llm.investigate_failure_iteratively(
            error_context=error_context,
            previous_attempts=[],
            context_fetcher=self.context_fetcher,
            attempt=1,
            max_turns=self.config.model.MAX_INVESTIGATION_TURNS,
            github_repo=os.getenv('GITHUB_REPOSITORY', ''),
            branch=branch,
            commit_sha=self.context_fetcher.commit_sha or ''
        )

        logger.info(f"Investigation complete (confidence: {llm_response.analysis.get('confidence', 0):.2f})")

        # Create branch
        branch_info = self.git.create_fix_branch(fix_id, attempt=1, base_branch=branch)
        branch_name = branch_info.name

        # Apply fix
        change_results = self.git.apply_file_changes(llm_response.fix['files_to_change'])

        if not all(r['success'] for r in change_results):
            failed = [r for r in change_results if not r['success']]
            return AgentResult(
                success=False,
                action_taken='error',
                attempt=1,
                model_used=llm_response.model_used,
                error_message=f"Failed to apply changes: {failed}"
            )

        # Commit
        commit_sha = self._commit_fix(
            fix_id=fix_id,
            attempt=1,
            llm_response=llm_response,
            previous_attempts=[]
        )

        # Push
        self.git.push_branch(branch_name)

        logger.info(f"✅ CASE 1 complete: Created {branch_name}, pushed commit {commit_sha[:8]}")

        return AgentResult(
            success=True,
            action_taken='first_failure',
            attempt=1,
            model_used=llm_response.model_used,
            confidence=llm_response.analysis['confidence'],
            fix_description=llm_response.fix['description'],
            branch_name=branch_name
        )

    def _case_2_retry(self, fix_id: str, current_attempt: int, failure_log: str) -> AgentResult:
        """
        CASE 2: Build failed on autonomous-fix branch (retry)

        Make another fix attempt on the same branch.
        """
        next_attempt = current_attempt + 1

        logger.info(f"🔄 CASE 2: Retry on autonomous-fix-{fix_id}, attempt {next_attempt}")

        # Check for escalation
        if self.config.model.should_escalate(next_attempt):
            return self._case_5_escalate(fix_id, current_attempt)

        # Check for human intervention
        if self._detect_human_commits(fix_id):
            logger.warning("⚠️  Human has committed to this branch - stopping agent")
            return AgentResult(
                success=True,
                action_taken='stopped_human_intervention',
                attempt=next_attempt,
                model_used='none',
                fix_description='Human intervention detected, agent stopped'
            )

        # Load previous attempts
        previous_attempts = self._load_previous_attempts(fix_id)

        # Extract error context from log using smart extractor
        error_context = self.log_extractor.extract_relevant_error(failure_log, platform="unknown")

        logger.info(f"Extracted {error_context['excerpt_lines']} lines, type: {error_context['error_type']}")

        # Get current branch name for GitHub context
        try:
            current_branch = self.git.git_repo.active_branch.name
        except:
            current_branch = self.config.git.format_branch_name(fix_id)

        # Use iterative investigation to analyze failure
        llm_response = self.llm.investigate_failure_iteratively(
            error_context=error_context,
            previous_attempts=previous_attempts,
            context_fetcher=self.context_fetcher,
            attempt=next_attempt,
            max_turns=self.config.model.MAX_INVESTIGATION_TURNS,
            github_repo=os.getenv('GITHUB_REPOSITORY', ''),
            branch=current_branch,
            commit_sha=self.context_fetcher.commit_sha or ''
        )

        logger.info(f"Investigation complete (confidence: {llm_response.analysis.get('confidence', 0):.2f})")
        logger.info(f"Model used: {llm_response.model_used}")

        # Apply fix
        change_results = self.git.apply_file_changes(llm_response.fix['files_to_change'])

        if not all(r['success'] for r in change_results):
            failed = [r for r in change_results if not r['success']]
            return AgentResult(
                success=False,
                action_taken='error',
                attempt=next_attempt,
                model_used=llm_response.model_used,
                error_message=f"Failed to apply changes: {failed}"
            )

        # Commit
        commit_sha = self._commit_fix(
            fix_id=fix_id,
            attempt=next_attempt,
            llm_response=llm_response,
            previous_attempts=previous_attempts
        )

        # Push to same branch
        branch_name = self.config.git.format_branch_name(fix_id)
        self.git.push_branch(branch_name, force=True)

        logger.info(f"✅ CASE 2 complete: Pushed attempt {next_attempt} to {branch_name}")

        return AgentResult(
            success=True,
            action_taken='retry',
            attempt=next_attempt,
            model_used=llm_response.model_used,
            confidence=llm_response.analysis['confidence'],
            fix_description=llm_response.fix['description'],
            branch_name=branch_name
        )

    def _case_3_success(self, fix_id: str, attempt_count: int) -> AgentResult:
        """
        CASE 3: Build passed on autonomous-fix branch

        Update skill and create PR with LLM summary.
        """
        logger.info(f"🎉 CASE 3: Build passed on autonomous-fix-{fix_id} after {attempt_count} attempts")

        # Get all commits on branch
        branch_name = self.config.git.format_branch_name(fix_id)
        commits = self.git.get_commits_on_branch(branch_name)

        # Extract original error from first commit
        original_error = self._extract_original_error_from_commit(commits[0] if commits else None)

        # Get final diff
        final_diff = self.git.get_diff(branch_name, 'main')

        # Ask LLM to summarize for PR
        pr_summary = self.llm.summarize_for_pr(
            original_error=original_error,
            final_diff=final_diff,
            attempt_count=attempt_count,
            platform="unknown"
        )

        # Update skill
        # TODO: Implement skill update
        skill_updated = False

        # Create PR
        pr = self.git.create_pull_request(
            title=pr_summary['title'],
            body=pr_summary['body'],
            branch=branch_name,
            base='main',
            labels=[self.config.git.format_attempt_label(fix_id, attempt_count)]
        )

        logger.info(f"✅ CASE 3 complete: Created PR {pr.url}")

        return AgentResult(
            success=True,
            action_taken='pr_created',
            attempt=attempt_count,
            model_used='claude-sonnet-4-5-20250929',  # Sonnet for summaries
            confidence=1.0,
            fix_description=pr_summary['title'],
            pr_url=pr.url,
            branch_name=branch_name,
            skill_updated=skill_updated
        )

    def _case_5_escalate(self, fix_id: str, attempts_made: int) -> AgentResult:
        """
        CASE 5: Too many attempts - escalate to human

        Create GitHub Issue if not already escalated.
        """
        logger.warning(f"🚨 CASE 5: Escalating after {attempts_made} attempts")

        # Check for existing escalation
        escalation_label = self.config.git.format_escalation_label(fix_id)
        existing_issue = self.git.find_issue_by_label(escalation_label)

        if existing_issue:
            logger.info(f"Already escalated: {existing_issue.html_url}")
            return AgentResult(
                success=True,
                action_taken='already_escalated',
                attempt=attempts_made + 1,
                model_used='none',
                pr_url=existing_issue.html_url
            )

        # Get all attempts
        branch_name = self.config.git.format_branch_name(fix_id)
        commits = self.git.get_commits_on_branch(branch_name)

        # Format attempts for LLM
        attempts_text = self._format_attempts_for_escalation(commits)

        # Get original error
        original_error = self._extract_original_error_from_commit(commits[0] if commits else None)

        # Ask LLM for escalation summary
        escalation_summary = self.llm.create_escalation_summary(
            original_error=original_error,
            all_attempts=attempts_text,
            attempt_count=attempts_made
        )

        # Create issue
        issue = self.git.create_issue(
            title=f"🚨 Build Failure Escalation: {fix_id}",
            body=self._format_escalation_body(escalation_summary, fix_id, attempts_made),
            labels=[escalation_label, 'needs-human', 'autonomous-agent']
        )

        logger.info(f"✅ CASE 5 complete: Created escalation issue {issue.html_url}")

        return AgentResult(
            success=True,
            action_taken='escalated',
            attempt=attempts_made + 1,
            model_used='none',
            fix_description=f'Escalated after {attempts_made} attempts',
            pr_url=issue.html_url
        )

    # Helper methods

    def _parse_failure_log(self, log_path: str, platform: str) -> Dict:
        """Parse failure log into context with full traceback"""
        if not log_path or not Path(log_path).exists():
            return {
                'platform': platform,
                'errors': ['No log file available'],
                'log_excerpt': '',
                'phase': 'unknown'
            }

        content = Path(log_path).read_text()

        # Extract full traceback if present
        traceback_lines = []
        in_traceback = False
        for line in content.split('\n'):
            if 'Traceback' in line:
                in_traceback = True
            if in_traceback:
                traceback_lines.append(line)
                # Stop at the error message
                if line and not line.startswith(' ') and 'Error' in line:
                    break

        # If we have a traceback, use that as the primary error
        if traceback_lines:
            error_text = '\n'.join(traceback_lines)
        else:
            # Otherwise extract error lines
            error_lines = []
            for line in content.split('\n'):
                if any(keyword in line for keyword in ['ERROR', 'Error', 'FAILED', 'Failed']):
                    error_lines.append(line)
            error_text = '\n'.join(error_lines[:20])

        return {
            'platform': platform,
            'errors': error_text,
            'log_excerpt': content[-2000:],  # Last 2000 chars of log
            'phase': 'test'  # For now, assume test phase
        }

    def _load_skill_knowledge(self) -> str:
        """Load skill knowledge base"""
        # For now, return placeholder
        return "No skill knowledge loaded yet"

    def _load_previous_attempts(self, fix_id: str) -> List[Dict]:
        """Load info about previous attempts from commits"""
        branch_name = self.config.git.format_branch_name(fix_id)
        commits = self.git.get_commits_on_branch(branch_name)

        attempts = []
        for commit in commits:
            match = re.search(r'Attempt (\d+):', commit.message)
            if match:
                attempts.append({
                    'attempt': int(match.group(1)),
                    'commit_sha': commit.hexsha[:8],
                    'message': commit.message,
                    'description': commit.message.split('\n')[0],
                    'failure_reason': 'Build failed after this attempt'
                })

        return sorted(attempts, key=lambda x: x['attempt'])

    def _commit_fix(self, fix_id: str, attempt: int, llm_response, previous_attempts: List) -> str:
        """Create commit for fix attempt"""
        message = self._format_commit_message(fix_id, attempt, llm_response, previous_attempts)

        if self.mock_mode:
            return f"mock_commit_{fix_id}_{attempt}"

        self.git.git_repo.git.commit('-m', message, '--allow-empty')
        commit_sha = self.git.git_repo.head.commit.hexsha

        logger.info(f"Committed: {commit_sha[:8]}")
        return commit_sha

    def _format_commit_message(self, fix_id: str, attempt: int, llm_response, previous_attempts: List) -> str:
        """Format git commit message"""

        why_previous_failed = ""
        if previous_attempts:
            why_previous_failed = f"\n\n**Why Previous Attempts Failed:**\n{llm_response.analysis.get('why_previous_failed', 'See previous commits')}"

        # Get reasoning from either fix or analysis (different prompts use different structures)
        reasoning = llm_response.fix.get('reasoning') or llm_response.analysis.get('reasoning', 'See root cause analysis above')

        message = f"""🤖 Autonomous Fix Attempt {attempt}: {llm_response.fix['description']}

**Root Cause Analysis:**
{llm_response.analysis['root_cause']}
{why_previous_failed}

**Fix Applied:**
{llm_response.fix['description']}

**Reasoning:**
{reasoning}

**Confidence:** {llm_response.analysis.get('confidence', 0.0):.2f}
**Model Used:** {llm_response.model_used}

---
Fix ID: {fix_id}
Attempt: {attempt}
"""

        return message

    def _extract_original_error_from_commit(self, commit) -> str:
        """Extract original error from first commit message"""
        if not commit:
            return "Unknown error"

        # Look for Root Cause Analysis section
        message = commit.message
        match = re.search(r'\*\*Root Cause Analysis:\*\*\n(.+?)(?:\n\*\*|$)', message, re.DOTALL)
        if match:
            return match.group(1).strip()

        return message.split('\n')[0]

    def _format_attempts_for_escalation(self, commits: List) -> str:
        """Format commit history for escalation summary"""
        attempts_text = ""
        for i, commit in enumerate(commits, 1):
            attempts_text += f"\n### Attempt {i}\n"
            attempts_text += f"Commit: {commit.hexsha[:8]}\n"
            attempts_text += f"{commit.message}\n"

        return attempts_text

    def _format_escalation_body(self, summary: Dict, fix_id: str, attempts: int) -> str:
        """Format GitHub issue body for escalation"""
        return f"""## 🚨 Escalation Notice

The autonomous agent attempted to fix this build failure **{attempts} times** but was unsuccessful. Human intervention is now required.

**Fix ID:** {fix_id}
**Total Attempts:** {attempts}

## Summary

{summary['summary']}

## Patterns Observed

{chr(10).join('- ' + p for p in summary.get('patterns', []))}

## Suggested Investigation

{chr(10).join('- ' + s for s in summary.get('suggested_investigation', []))}

## Next Steps

{chr(10).join(f"{i+1}. {step}" for i, step in enumerate(summary.get('next_steps', [])))}

---
Generated by Autonomous DevOps Agent after {attempts} failed attempts
"""


def main():
    """CLI entry point"""
    parser = argparse.ArgumentParser(description='Autonomous DevOps Agent')

    parser.add_argument(
        '--branch',
        required=True,
        help='Current branch name'
    )

    parser.add_argument(
        '--build-status',
        required=True,
        choices=['success', 'failure'],
        help='Build status (success or failure)'
    )

    parser.add_argument(
        '--failure-log',
        help='Path to failure log file (if build failed)'
    )

    parser.add_argument(
        '--output',
        default='agent-result.json',
        help='Output file for agent result'
    )

    parser.add_argument(
        '--mock-mode',
        action='store_true',
        help='Run in mock mode (both LLM and Git) - same as --mock-llm --mock-git'
    )

    parser.add_argument(
        '--mock-llm',
        action='store_true',
        help='Mock LLM API calls only (allows testing coordination with real GitHub)'
    )

    parser.add_argument(
        '--mock-git',
        action='store_true',
        help='Mock Git operations only'
    )

    args = parser.parse_args()

    # Initialize agent with separate mock controls
    # If --mock-mode is set, it overrides individual flags
    mock_llm = args.mock_llm if not args.mock_mode else True
    mock_git = args.mock_git if not args.mock_mode else True

    agent = AutonomousAgent(
        mock_mode=args.mock_mode,
        mock_llm=mock_llm,
        mock_git=mock_git
    )

    # Run agent
    result = agent.run(
        branch=args.branch,
        build_status=args.build_status,
        failure_log=args.failure_log
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
    if result.fix_description:
        print(f"Fix: {result.fix_description}")
    if result.pr_url:
        print(f"PR/Issue: {result.pr_url}")
    if result.error_message:
        print(f"Error: {result.error_message}")
    print("=" * 60)


if __name__ == '__main__':
    main()
