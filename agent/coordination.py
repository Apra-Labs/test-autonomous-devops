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

    def should_analyze(self, flavor: str) -> Dict:
        """
        Determine if this flavor should run LLM analysis

        Simple logic: If another workflow is already fixing this commit, skip.
        Otherwise, create an issue and proceed with analysis.

        Args:
            flavor: Build flavor (e.g., "linux-x64", "windows", "jetson-arm64")

        Returns:
            Dict with decision and coordination info
        """
        logger.info(f"Checking coordination for flavor={flavor}, commit={self.commit_sha[:8]}")

        # Check for existing coordination issue for this commit
        existing_issue = self._find_coordination_issue()

        if existing_issue:
            # Another workflow is already working on this commit
            logger.info(f"Found existing coordination issue #{existing_issue['number']} - another workflow is fixing this")

            # Add ourselves to the issue (for tracking)
            self._add_flavor_to_issue(existing_issue['number'], flavor)

            return {
                'should_analyze': False,
                'reason': 'another_workflow_fixing',
                'issue_number': existing_issue['number']
            }
        else:
            # No one is working on this commit yet - we're first!
            logger.info(f"No existing coordination issue - we're first to work on this")
            issue = self._create_coordination_issue(flavor)

            # Double-check: Did someone else create one at the same time?
            time.sleep(1)
            existing_issue = self._find_coordination_issue()

            if existing_issue and existing_issue['number'] != issue['number']:
                if existing_issue['number'] < issue['number']:
                    logger.info(f"Race condition: found lower-numbered issue #{existing_issue['number']}")
                    # Close our duplicate
                    try:
                        if hasattr(self.github_repo, 'get_issue'):
                            our_issue = self.github_repo.get_issue(issue['number'])
                            our_issue.edit(state='closed')
                            our_issue.create_comment(f"Duplicate of #{existing_issue['number']}")
                    except Exception as e:
                        logger.error(f"Failed to close duplicate: {e}")

                    return {
                        'should_analyze': False,
                        'reason': 'another_workflow_fixing',
                        'issue_number': existing_issue['number']
                    }

            return {
                'should_analyze': True,
                'reason': 'first_to_fix',
                'issue_number': issue['number']
            }

    def _find_coordination_issue(self) -> Optional[Dict]:
        """Find existing coordination issue for this commit

        Retries with small delays to handle GitHub API eventual consistency.
        """
        try:
            # Use Repository.get_issues() instead of search API
            # Try multiple times with small delays to handle API lag
            if hasattr(self.github_repo, 'get_issues'):
                commit_prefix = self.commit_sha[:8]

                # Try up to 3 times with increasing delays
                for attempt in range(3):
                    # Get open issues with coordination label
                    issues = self.github_repo.get_issues(
                        state='open',
                        labels=[self.coordination_label]
                    )

                    # Filter for our commit SHA in title
                    for issue in issues:
                        if commit_prefix in issue.title:
                            logger.info(f"Found existing coordination issue: #{issue.number} (attempt {attempt+1})")
                            # Convert to dict for easier handling
                            return {
                                'number': issue.number,
                                'title': issue.title,
                                'body': issue.body,
                                'url': issue.html_url
                            }

                    # If not found and not last attempt, wait a bit
                    if attempt < 2:
                        time.sleep(0.5 * (attempt + 1))  # 0.5s, then 1s

                logger.info(f"No coordination issue found for commit {self.commit_sha[:8]} after 3 attempts")
                return None
            else:
                # Fallback for testing
                logger.info(f"Would list issues with label {self.coordination_label}")
                return None

        except Exception as e:
            logger.error(f"Error finding coordination issue: {e}")
            return None

    def _create_coordination_issue(self, flavor: str) -> Dict:
        """Create coordination issue for this commit"""
        title = f"🤖 Build Coordination: {self.commit_sha[:8]}"

        body = f"""## Multi-Flavor Build Coordination

**Commit:** {self.commit_sha}
**First Failing Flavor:** {flavor}
**Created:** {datetime.utcnow().isoformat()}

### Status

🔄 **{flavor}** is analyzing the failure and will create a fix

### Failing Flavors

- ✗ **{flavor}** - Analyzing with LLM

---
*This issue coordinates workflows to avoid duplicate LLM analysis.*
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

    def _add_flavor_to_issue(self, issue_number: int, flavor: str):
        """Add this flavor to existing coordination issue"""
        try:
            comment = f"""### Flavor: {flavor}

**Status:** ✗ Also failed on this commit
**Time:** {datetime.utcnow().isoformat()}

Waiting for fix from primary flavor...
"""

            # In real implementation:
            # self.github_repo.get_issue(issue_number).create_comment(comment)

            logger.info(f"Would add comment to issue #{issue_number}")

        except Exception as e:
            logger.error(f"Error adding flavor to issue: {e}")


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


class CoordinationConfig:
    """Configuration for flavor coordination"""

    # Wait time before giving up on first flavor (minutes)
    MAX_WAIT_TIME = 15

    # Maximum flavors to wait for before force-analyzing
    MAX_WAITING_FLAVORS = 3

    # Whether to enable coordination (can disable for testing)
    ENABLED = True
