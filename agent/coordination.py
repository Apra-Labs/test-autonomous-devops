"""
Multi-Flavor Build Coordination

Prevents duplicate LLM analysis when multiple flavors fail with same root cause.
Uses GitHub Issues as distributed lock mechanism.
"""
import logging
import time
import json
from typing import Optional, Dict, List
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


class FlavorCoordinator:
    """
    Coordinates multiple flavor builds to avoid duplicate LLM analysis

    Strategy:
    1. First failing flavor creates coordination issue
    2. Other flavors check for existing coordination issue
    3. Wait for first flavor to fix, then retry
    4. If fix works, skip LLM analysis (cost savings!)
    """

    def __init__(self, github_client, github_repo, repo: str, commit_sha: str):
        """
        Initialize coordinator

        Args:
            github_client: Top-level GitHub API client (for search_issues)
            github_repo: PyGithub Repository object (for create_issue)
            repo: Repository name (e.g., "Apra-Labs/ApraPipes")
            commit_sha: Current commit being built
        """
        self.github = github_client
        self.github_repo = github_repo
        self.repo = repo
        self.commit_sha = commit_sha
        self.coordination_label = "autonomous-coordination"

    def should_analyze(self, flavor: str, error_signature: str) -> Dict:
        """
        Determine if this flavor should run LLM analysis

        Args:
            flavor: Build flavor (e.g., "linux-x64", "windows", "jetson-arm64")
            error_signature: Hash/signature of error (for deduplication)

        Returns:
            Dict with decision and coordination info
        """
        logger.info(f"Checking coordination for flavor={flavor}, commit={self.commit_sha[:8]}")

        # Check for existing coordination issue for this commit
        existing_issue = self._find_coordination_issue()

        if existing_issue:
            logger.info(f"Found existing coordination issue #{existing_issue['number']}")

            # Check if this flavor already reported
            flavors = self._parse_flavors_from_issue(existing_issue)

            if flavor in flavors:
                logger.info(f"Flavor {flavor} already coordinated")
                return {
                    'should_analyze': False,
                    'reason': 'already_coordinated',
                    'issue_number': existing_issue['number']
                }

            # Add this flavor to the issue
            self._add_flavor_to_issue(existing_issue['number'], flavor, error_signature)

            # Check if fix is in progress
            if self._is_fix_in_progress(existing_issue):
                logger.info("Fix already in progress by another flavor, waiting...")
                return {
                    'should_analyze': False,
                    'reason': 'fix_in_progress',
                    'issue_number': existing_issue['number'],
                    'wait_for_branch': self._extract_fix_branch(existing_issue)
                }

            # No fix in progress, but we're not first - check if we should analyze
            if len(flavors) == 1:
                # We're second flavor, close enough to first - analyze
                logger.info("We're second flavor, will analyze")
                self._mark_fix_in_progress(existing_issue['number'], flavor)
                return {
                    'should_analyze': True,
                    'reason': 'second_flavor',
                    'issue_number': existing_issue['number']
                }
            else:
                # Many flavors already failed, wait for first to fix
                logger.info(f"{len(flavors)} flavors already failed, waiting")
                return {
                    'should_analyze': False,
                    'reason': 'multiple_flavors_waiting',
                    'issue_number': existing_issue['number']
                }
        else:
            # No coordination issue exists - we're first!
            logger.info(f"First flavor to fail, creating coordination issue")
            issue = self._create_coordination_issue(flavor, error_signature)

            return {
                'should_analyze': True,
                'reason': 'first_flavor',
                'issue_number': issue['number']
            }

    def _find_coordination_issue(self) -> Optional[Dict]:
        """Find existing coordination issue for this commit"""
        try:
            # Search for open issues with coordination label and commit SHA in title
            query = f"repo:{self.repo} is:issue is:open label:{self.coordination_label} {self.commit_sha[:8]} in:title"

            # Use GitHub API to search
            # Search for existing coordination issue
            if hasattr(self.github, 'search_issues'):
                issues = self.github.search_issues(query, order='created', sort='desc')
                if issues and len(issues) > 0:
                    logger.info(f"Found existing coordination issue: #{issues[0].number}")
                    return issues[0]
                logger.info(f"No coordination issue found for commit {self.commit_sha[:8]}")
                return None
            else:
                # Fallback for testing
                logger.info(f"Would search: {query}")
                return None

        except Exception as e:
            logger.error(f"Error finding coordination issue: {e}")
            return None

    def _create_coordination_issue(self, flavor: str, error_signature: str) -> Dict:
        """Create coordination issue for this commit"""
        title = f"🤖 Build Coordination: {self.commit_sha[:8]}"

        body = f"""## Multi-Flavor Build Coordination

**Commit:** {self.commit_sha}
**First Failing Flavor:** {flavor}
**Error Signature:** `{error_signature[:100]}`
**Created:** {datetime.utcnow().isoformat()}

### Failing Flavors

- ✗ **{flavor}** - First to fail, analyzing with LLM

### Status

🔄 LLM analysis in progress for {flavor}

---
*This issue coordinates multiple flavor builds to avoid duplicate LLM analysis.*
*Other flavors will wait for the fix from {flavor}.*
"""

        try:
            # Create real GitHub issue for coordination
            if hasattr(self.github_repo, 'create_issue'):
                issue = self.github_repo.create_issue(
                    title=title,
                    body=body,
                    labels=[self.coordination_label, f"commit-{self.commit_sha[:8]}"]
                )
                logger.info(f"Created coordination issue: #{issue.number}")
                return {'number': issue.number, 'title': title, 'url': issue.html_url}
            else:
                # Fallback for testing
                logger.info(f"Would create coordination issue: {title}")
                return {'number': 12345, 'title': title}

        except Exception as e:
            logger.error(f"Error creating coordination issue: {e}")
            # Return dummy for graceful degradation
            return {'number': 0, 'title': title}

    def _add_flavor_to_issue(self, issue_number: int, flavor: str, error_signature: str):
        """Add this flavor to existing coordination issue"""
        try:
            comment = f"""### Flavor: {flavor}

**Status:** ✗ Failed with similar error
**Error Signature:** `{error_signature[:100]}`
**Time:** {datetime.utcnow().isoformat()}

Waiting for fix from primary flavor...
"""

            # In real implementation:
            # self.github.create_issue_comment(issue_number, comment)

            logger.info(f"Would add comment to issue #{issue_number}")

        except Exception as e:
            logger.error(f"Error adding flavor to issue: {e}")

    def _mark_fix_in_progress(self, issue_number: int, flavor: str):
        """Mark that this flavor is working on the fix"""
        try:
            comment = f"""🔄 **{flavor}** is now analyzing with LLM and will propose a fix.

Other flavors should wait for the fix branch to be created.
"""
            # self.github.create_issue_comment(issue_number, comment)
            logger.info(f"Would mark fix in progress for {flavor}")

        except Exception as e:
            logger.error(f"Error marking fix in progress: {e}")

    def _is_fix_in_progress(self, issue: Dict) -> bool:
        """Check if fix is already being worked on"""
        # Check issue comments for "analyzing with LLM" or fix branch
        # For now, return False
        return False

    def _extract_fix_branch(self, issue: Dict) -> Optional[str]:
        """Extract fix branch name from issue if exists"""
        # Parse issue body/comments for autonomous-fix-* branch
        return None

    def _parse_flavors_from_issue(self, issue: Dict) -> List[str]:
        """Parse list of flavors that have failed from issue"""
        # Parse issue body/comments for flavor names
        # For now, return empty
        return []

    def mark_fix_complete(self, issue_number: int, fix_branch: str, pr_number: int):
        """Mark that fix is complete and ready for other flavors"""
        try:
            comment = f"""✅ **Fix Complete!**

**Fix Branch:** `{fix_branch}`
**Pull Request:** #{pr_number}

Other flavors can now:
1. Pull the fix branch
2. Re-run tests
3. Skip LLM analysis if tests pass

**Cost Savings:** Avoided {self._count_waiting_flavors(issue_number)} duplicate LLM analyses! 💰
"""

            # self.github.create_issue_comment(issue_number, comment)
            # self.github.close_issue(issue_number)

            logger.info(f"Would mark fix complete for issue #{issue_number}")

        except Exception as e:
            logger.error(f"Error marking fix complete: {e}")

    def _count_waiting_flavors(self, issue_number: int) -> int:
        """Count how many flavors are waiting"""
        # Parse issue to count flavors
        return 6  # Dummy: 7 total - 1 that fixed = 6 saved

    def generate_error_signature(self, error_log: str) -> str:
        """
        Generate signature for error to detect duplicates

        Args:
            error_log: Error log content

        Returns:
            Hash/signature of error
        """
        import hashlib

        # Extract key error lines (ignoring timestamps, paths, etc.)
        # For simple version, hash last 500 chars of error
        error_excerpt = error_log[-500:] if len(error_log) > 500 else error_log

        # Remove timestamps and variable parts
        import re
        normalized = re.sub(r'\d{4}-\d{2}-\d{2}', 'DATE', error_excerpt)
        normalized = re.sub(r'\d+\.\d+\.\d+\.\d+', 'IP', normalized)
        normalized = re.sub(r'/[\w/]+/', '/PATH/', normalized)

        # Hash it
        return hashlib.sha256(normalized.encode()).hexdigest()[:16]


class CoordinationConfig:
    """Configuration for flavor coordination"""

    # Wait time before giving up on first flavor (minutes)
    MAX_WAIT_TIME = 15

    # Maximum flavors to wait for before force-analyzing
    MAX_WAITING_FLAVORS = 3

    # Whether to enable coordination (can disable for testing)
    ENABLED = True
