"""
Git and GitHub Operations for Autonomous Agent

Handles branch creation, commits, PR creation, and label management.
Supports both real Git operations and mock mode for testing.
"""
import logging
import os
from typing import Dict, List, Optional
from pathlib import Path
from dataclasses import dataclass

# Import with fallback for testing
try:
    from github import Github
    import git
except ImportError:
    Github = None
    git = None

# Handle both package import and direct script execution
try:
    from .config import GitConfig
except ImportError:
    from config import GitConfig

logger = logging.getLogger(__name__)


@dataclass
class BranchInfo:
    """Information about a created/managed branch"""
    name: str
    fix_id: str
    attempt: int
    exists: bool
    commit_sha: Optional[str] = None


@dataclass
class PRInfo:
    """Information about created PR"""
    number: int
    url: str
    title: str
    branch: str


class GitOperations:
    """
    Git and GitHub operations

    Supports mock mode for testing without actual Git/GitHub operations.
    """

    def __init__(self,
                 repo_path: str = ".",
                 github_token: Optional[str] = None,
                 github_repo: Optional[str] = None,
                 mock_mode: bool = False,
                 config: Optional[GitConfig] = None):
        """
        Initialize Git operations

        Args:
            repo_path: Path to git repository
            github_token: GitHub personal access token
            github_repo: GitHub repository (owner/repo format)
            mock_mode: If True, simulate operations without actual Git/GitHub calls
            config: Git configuration
        """
        self.repo_path = Path(repo_path)
        self.mock_mode = mock_mode
        self.config = config or GitConfig()

        if not mock_mode:
            if git is None:
                raise ImportError("gitpython required for real Git operations")
            if Github is None:
                raise ImportError("PyGithub required for GitHub operations")

            self.git_repo = git.Repo(repo_path)

            if github_token and github_repo:
                self.github = Github(github_token)
                self.github_repo = self.github.get_repo(github_repo)
            else:
                self.github = None
                self.github_repo = None
                logger.warning("GitHub integration disabled (no token/repo provided)")
        else:
            self.git_repo = None
            self.github = None
            self.github_repo = None
            logger.info("Git Operations initialized in MOCK MODE")

    def create_fix_branch(self, fix_id: str, attempt: int,
                         base_branch: str = "main") -> BranchInfo:
        """
        Create autonomous fix branch

        Args:
            fix_id: Unique fix identifier
            attempt: Attempt number
            base_branch: Base branch to branch from

        Returns:
            BranchInfo with branch details
        """
        branch_name = self.config.format_branch_name(fix_id, attempt)

        logger.info(f"Creating branch: {branch_name}")

        if self.mock_mode:
            return BranchInfo(
                name=branch_name,
                fix_id=fix_id,
                attempt=attempt,
                exists=False,
                commit_sha="mock_sha_" + branch_name
            )

        # Check if branch exists
        branch_exists = branch_name in [b.name for b in self.git_repo.branches]

        if not branch_exists:
            # Create new branch from base
            self.git_repo.git.checkout(base_branch)
            self.git_repo.git.checkout('-b', branch_name)
            logger.info(f"Created new branch: {branch_name}")
        else:
            # Switch to existing branch
            self.git_repo.git.checkout(branch_name)
            logger.info(f"Checked out existing branch: {branch_name}")

        return BranchInfo(
            name=branch_name,
            fix_id=fix_id,
            attempt=attempt,
            exists=branch_exists,
            commit_sha=self.git_repo.head.commit.hexsha
        )

    def apply_file_changes(self, file_changes: List[Dict]) -> List[Dict]:
        """
        Apply file changes from fix

        Args:
            file_changes: List of file changes (path, action, content)

        Returns:
            List of results for each file change
        """
        results = []

        for change in file_changes:
            path = change['path']
            action = change['action']
            content = change.get('content', '')

            logger.info(f"Applying {action} to {path}")

            if self.mock_mode:
                results.append({
                    'path': path,
                    'action': action,
                    'success': True,
                    'mock': True
                })
                continue

            try:
                file_path = self.repo_path / path

                if action == 'create' or action == 'edit':
                    # Create parent directories if needed
                    file_path.parent.mkdir(parents=True, exist_ok=True)
                    file_path.write_text(content)
                    self.git_repo.git.add(path)

                elif action == 'delete':
                    if file_path.exists():
                        file_path.unlink()
                        self.git_repo.git.rm(path)

                results.append({
                    'path': path,
                    'action': action,
                    'success': True
                })

            except Exception as e:
                logger.error(f"Failed to apply change to {path}: {e}")
                results.append({
                    'path': path,
                    'action': action,
                    'success': False,
                    'error': str(e)
                })

        return results

    def commit_fix(self, fix_id: str, attempt: int, fix_info: Dict,
                   previous_attempts: List[Dict]) -> str:
        """
        Commit fix with structured message

        Args:
            fix_id: Fix identifier
            attempt: Attempt number
            fix_info: Fix information from LLM
            previous_attempts: Previous attempt history

        Returns:
            Commit SHA
        """
        message = self._format_commit_message(fix_id, attempt, fix_info,
                                              previous_attempts)

        logger.info(f"Committing fix (attempt {attempt})")

        if self.mock_mode:
            return f"mock_commit_sha_{fix_id}_{attempt}"

        try:
            self.git_repo.git.commit('-m', message, '--allow-empty')
            commit_sha = self.git_repo.head.commit.hexsha
            logger.info(f"Committed: {commit_sha[:8]}")
            return commit_sha

        except Exception as e:
            logger.error(f"Commit failed: {e}")
            raise

    def _format_commit_message(self, fix_id: str, attempt: int,
                               fix_info: Dict, previous_attempts: List[Dict]) -> str:
        """Format structured commit message"""

        why_previous_failed = ""
        if previous_attempts:
            why_previous_failed = f"""
**Why Previous Attempts Failed:**
{fix_info['analysis'].get('why_previous_failed', 'See previous commit messages')}
"""

        message = f"""🤖 Autonomous Fix Attempt {attempt}: {fix_info['fix']['description']}

**Root Cause Analysis:**
{fix_info['analysis']['root_cause']}
{why_previous_failed}
**Fix Applied:**
{fix_info['fix']['description']}

**Reasoning:**
{fix_info['fix']['reasoning']}

**Test Plan:**
{fix_info['fix'].get('test_plan', 'Trigger CI build')}

**Files Changed:**
{chr(10).join(f"- {fc['path']}" for fc in fix_info['fix']['files_to_change'])}

**Confidence:** {fix_info['analysis']['confidence']}
**Model Used:** {fix_info.get('model_used', 'Unknown')}

---
Fix ID: {fix_id}
Attempt: {attempt}
"""
        return message

    def push_branch(self, branch_name: str, force: bool = False) -> bool:
        """
        Push branch to remote

        Args:
            branch_name: Branch to push
            force: Force push

        Returns:
            True if successful
        """
        logger.info(f"Pushing branch: {branch_name}")

        if self.mock_mode:
            return True

        try:
            origin = self.git_repo.remote('origin')
            push_args = [f"HEAD:{branch_name}"]
            if force:
                push_args.append('--force')

            origin.push(*push_args)
            logger.info(f"Pushed {branch_name} to remote")
            return True

        except Exception as e:
            logger.error(f"Push failed: {e}")
            return False

    def create_pr(self,
                  fix_id: str,
                  attempt: int,
                  fix_info: Dict,
                  previous_attempts: List[Dict],
                  skill_updates: Optional[str] = None,
                  platform: str = "unknown",
                  base_branch: str = "main") -> Optional[PRInfo]:
        """
        Create pull request with fix and skill updates

        Args:
            fix_id: Fix identifier
            attempt: Attempt number
            fix_info: Fix information
            previous_attempts: Previous attempts
            skill_updates: Skill update content
            platform: Platform identifier
            base_branch: Base branch for PR

        Returns:
            PRInfo if successful, None otherwise
        """
        if not self.github_repo:
            logger.warning("GitHub integration not available")
            return None

        branch_name = self.config.format_branch_name(fix_id, attempt)

        # Format PR body
        pr_body = self._format_pr_body(fix_id, attempt, fix_info,
                                       previous_attempts, skill_updates)

        title = self.config.PR_TITLE_FORMAT.format(
            description=fix_info['fix']['description'][:80]
        )

        logger.info(f"Creating PR: {title}")

        if self.mock_mode:
            return PRInfo(
                number=123,
                url=f"https://github.com/mock/mock/pull/123",
                title=title,
                branch=branch_name
            )

        try:
            # Check if PR already exists
            existing_prs = self.github_repo.get_pulls(
                state='open',
                head=f"{self.github_repo.owner.login}:{branch_name}"
            )

            for pr in existing_prs:
                logger.info(f"Updating existing PR: {pr.html_url}")
                pr.edit(body=pr_body)
                return PRInfo(
                    number=pr.number,
                    url=pr.html_url,
                    title=pr.title,
                    branch=branch_name
                )

            # Create new PR
            pr = self.github_repo.create_pull(
                title=title,
                body=pr_body,
                head=branch_name,
                base=base_branch
            )

            # Add labels
            confidence = fix_info['analysis']['confidence']
            labels = self.config.format_labels(
                fix_id=fix_id,
                attempt=attempt,
                platform=platform,
                high_confidence=(confidence >= 0.85)
            )
            pr.add_to_labels(*labels)

            logger.info(f"Created PR: {pr.html_url}")

            return PRInfo(
                number=pr.number,
                url=pr.html_url,
                title=pr.title,
                branch=branch_name
            )

        except Exception as e:
            logger.error(f"PR creation failed: {e}")
            return None

    def _format_pr_body(self, fix_id: str, attempt: int, fix_info: Dict,
                        previous_attempts: List[Dict],
                        skill_updates: Optional[str]) -> str:
        """Format PR body"""

        previous_section = ""
        if previous_attempts:
            previous_section = "\n## 🔄 Previous Attempts\n\n"
            for prev in previous_attempts:
                previous_section += f"- ❌ Attempt {prev['attempt_num']}: {prev.get('fix_applied', 'Unknown')}\n"

        skill_section = "No skill updates in this fix."
        if skill_updates:
            skill_section = f"```markdown\n{skill_updates}\n```"

        files_changed = "\n".join(
            f"- `{fc['path']}` ({fc['action']})"
            for fc in fix_info['fix']['files_to_change']
        )

        max_attempts = 6  # From config
        model = fix_info.get('model_used', 'Unknown')

        return f"""## 🤖 Autonomous DevOps Agent

**Fix ID:** {fix_id}
**Attempt:** {attempt} of {max_attempts}
**Model Used:** {model}
**Confidence:** {fix_info['analysis']['confidence']:.2f}

{previous_section}

## 🔍 Root Cause

{fix_info['analysis']['root_cause']}

## 🔧 Fix Applied

{fix_info['fix']['description']}

**Reasoning:**
{fix_info['fix']['reasoning']}

## 📚 Skill Updates

{skill_section}

## 📁 Files Changed

{files_changed}

---
Generated by Autonomous DevOps Agent
"""

    def load_previous_attempts(self, fix_id: str, max_attempt: int) -> List[Dict]:
        """
        Load previous fix attempts from git history

        Args:
            fix_id: Fix identifier
            max_attempt: Maximum attempt number to load

        Returns:
            List of previous attempt information
        """
        logger.info(f"Loading previous attempts for fix {fix_id}")

        if self.mock_mode:
            # Return mock previous attempts
            if max_attempt > 1:
                return [{
                    'attempt_num': 1,
                    'fix_applied': 'Mock fix from attempt 1',
                    'reasoning': 'Mock reasoning',
                    'model_used': 'claude-sonnet-4-5',
                    'commit_sha': 'mock_sha_1'
                }]
            return []

        attempts = []

        for attempt_n in range(1, max_attempt):
            branch_name = self.config.format_branch_name(fix_id, attempt_n)

            try:
                # Get commits on this branch
                commits = list(self.github_repo.get_commits(sha=branch_name))

                if commits:
                    commit = commits[0]
                    attempt_info = self._parse_attempt_commit(commit, attempt_n)
                    attempts.append(attempt_info)
                    logger.info(f"Loaded attempt {attempt_n}")

            except Exception as e:
                logger.warning(f"Could not load attempt {attempt_n}: {e}")
                continue

        return attempts

    def _parse_attempt_commit(self, commit, attempt_num: int) -> Dict:
        """Parse commit message to extract attempt info"""
        message = commit.commit.message

        # Extract sections using simple parsing
        # (In production, use more robust parsing)

        return {
            'attempt_num': attempt_num,
            'fix_applied': self._extract_section(message, "Fix Applied"),
            'reasoning': self._extract_section(message, "Reasoning"),
            'model_used': self._extract_field(message, "Model Used"),
            'commit_sha': commit.sha
        }

    def _extract_section(self, text: str, section_name: str) -> str:
        """Extract section from commit message"""
        import re
        pattern = rf"\*\*{section_name}:\*\*\n(.+?)(?=\n\*\*|\n\n---|\Z)"
        match = re.search(pattern, text, re.DOTALL)
        return match.group(1).strip() if match else "Unknown"

    def _extract_field(self, text: str, field_name: str) -> str:
        """Extract single field from commit message"""
        import re
        pattern = rf"\*\*{field_name}:\*\* (.+)"
        match = re.search(pattern, text)
        return match.group(1).strip() if match else "Unknown"


class MockGitOperations(GitOperations):
    """Convenience class for mock git operations"""

    def __init__(self, config: Optional[GitConfig] = None):
        super().__init__(repo_path=".", mock_mode=True, config=config)
