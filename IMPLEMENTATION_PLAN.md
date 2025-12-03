# Autonomous DevOps Agent - Implementation Plan

**Status:** Ready to implement after your approval
**Estimated Time:** 3-4 hours of focused work + testing

---

## Architecture Confirmed

### Branch Naming
- ✅ Branch: `autonomous-fix-{run_id}` (NO `/attempt-N`)
- ✅ Tracking: Commit messages + GitHub labels
- ✅ Labels: `autonomous-fix-{run_id}-attempt-1`, `autonomous-fix-{run_id}-attempt-2`, etc.

### Five Cases

**CASE 1:** First failure on main/other branch
- Create `autonomous-fix-{run_id}`
- Commit: "🤖 Autonomous Fix Attempt 1: {description}"
- Label: `autonomous-fix-{run_id}-attempt-1`
- Push → Triggers build on fix branch

**CASE 2:** Failure on `autonomous-fix-*` branch (retry)
- Detect attempt N from commit messages
- If N ≥ 7: Go to CASE 5
- If human committed: Stop (no more attempts)
- Load commits 1..N from branch
- Select model (Sonnet ≤4, Opus 5-6)
- LLM with full history
- Commit: "🤖 Autonomous Fix Attempt {N+1}: {description}"
- Label: `autonomous-fix-{run_id}-attempt-{N+1}`
- Push to SAME branch

**CASE 3:** Success on `autonomous-fix-*` branch
- Load all commits on branch (full changeset)
- Get original error from attempt 1
- LLM summarizes: original problem + how final changeset fixes it
- Update SKILL.md
- Create PR with LLM summary + skill update

**CASE 4:** Success on main/other (early exit optimization)
- Do nothing (no checkout needed)

**CASE 5:** Escalation (N ≥ 7)
- Check if issue exists with label `autonomous-fix-{run_id}-escalation`
- If exists: Stop (already escalated)
- If not: Create issue with all attempt history
- No new commit

---

## Files to Modify

### 1. `agent/prompts.json` ✅ DONE
Contains all LLM prompt templates (tunable without code changes)

### 2. `agent/config.py`
**Changes:**
```python
@dataclass
class GitConfig:
    BRANCH_FORMAT = "autonomous-fix-{fix_id}"  # Remove /attempt-{attempt}
    LABEL_FORMAT = "autonomous-fix-{fix_id}-attempt-{attempt}"
    ESCALATION_LABEL_FORMAT = "autonomous-fix-{fix_id}-escalation"
```

### 3. `agent/autonomous_agent.py`
**Major refactor:**
```python
def run(self, branch: str, build_status: str, failure_log: str = None):
    """Main entry - routes to 5 cases"""

    is_fix_branch = branch.startswith('autonomous-fix-')

    if not is_fix_branch:
        if build_status == 'success':
            return self._case_4_do_nothing()
        else:
            return self._case_1_first_failure(...)
    else:
        fix_id = self._extract_fix_id(branch)
        current_attempt = self._detect_attempt_from_commits(fix_id)

        if build_status == 'success':
            return self._case_3_success(fix_id, current_attempt)
        else:
            return self._case_2_retry(fix_id, current_attempt, failure_log)

def _detect_attempt_from_commits(self, fix_id):
    """Parse commit messages for 'Attempt N' to find highest N"""
    commits = self.git.get_commits_on_branch(f'autonomous-fix-{fix_id}')
    max_attempt = 0
    for commit in commits:
        match = re.search(r'Attempt (\d+):', commit.message)
        if match:
            max_attempt = max(max_attempt, int(match.group(1)))
    return max_attempt

def _detect_human_commits(self, fix_id):
    """Check if any non-agent commits exist on branch"""
    commits = self.git.get_commits_on_branch(f'autonomous-fix-{fix_id}')
    for commit in commits:
        if commit.author.name != "Autonomous Agent":
            return True
    return False

def _case_3_success(self, fix_id, attempt_count):
    """Build passed - create PR with LLM summary"""

    # Get original error from first commit
    commits = self.git.get_commits_on_branch(f'autonomous-fix-{fix_id}')
    original_error = self._extract_error_from_commit(commits[0])

    # Get final diff (all changes from main)
    final_diff = self.git.get_diff(f'autonomous-fix-{fix_id}', 'main')

    # LLM: Summarize for humans
    summary = self.llm.summarize_for_pr(
        original_error=original_error,
        final_diff=final_diff,
        attempt_count=attempt_count,
        platform=...
    )

    # Update skill
    skill_update = self._update_skill(...)

    # Create PR
    pr = self.git.create_pr(
        title=summary['title'],
        body=summary['body'],
        branch=f'autonomous-fix-{fix_id}',
        base='main',
        labels=[f'autonomous-fix-{fix_id}', f'attempt-count-{attempt_count}']
    )

    return AgentResult(action_taken='pr_created', pr_url=pr.url, ...)

def _case_5_escalate(self, fix_id, attempts_made):
    """Too many attempts - escalate to human"""

    # Check for existing escalation
    escalation_label = f'autonomous-fix-{fix_id}-escalation'
    existing = self.git.find_issue_by_label(escalation_label)

    if existing:
        logger.info(f"Already escalated: {existing.url}")
        return AgentResult(action_taken='already_escalated', ...)

    # Get all attempts
    commits = self.git.get_commits_on_branch(f'autonomous-fix-{fix_id}')

    # LLM: Summarize failure
    summary = self.llm.create_escalation_summary(
        original_error=...,
        all_attempts=commits,
        attempt_count=attempts_made
    )

    # Create issue
    issue = self.git.create_issue(
        title=f"🚨 Build Failure Escalation: {fix_id}",
        body=self._format_escalation_body(summary),
        labels=[escalation_label, 'needs-human', 'autonomous-agent']
    )

    return AgentResult(action_taken='escalated', pr_url=issue.url, ...)
```

### 4. `agent/llm_client.py`
**Add methods:**
```python
def __init__(self, ...):
    self.prompts = self._load_prompts('agent/prompts.json')

def _load_prompts(self, path):
    with open(path) as f:
        return json.load(f)

def summarize_for_pr(self, original_error, final_diff, attempt_count, platform):
    """CASE 3: Create human-friendly PR summary"""
    template = self.prompts['summarize_for_pr']

    prompt = template['user_template'].format(
        original_error=original_error,
        final_diff=final_diff,
        attempt_count=attempt_count,
        platform=platform
    )

    response = self.client.messages.create(
        model="claude-sonnet-4-5-20250929",  # Always use Sonnet for summaries
        system=template['system'],
        messages=[{"role": "user", "content": prompt}]
    )

    return json.loads(response.content[0].text)

def create_escalation_summary(self, original_error, all_attempts, attempt_count):
    """CASE 5: Summarize failures for human"""
    # Similar to above but uses escalation_summary template
```

### 5. `agent/git_operations.py`
**Add methods:**
```python
def get_commits_on_branch(self, branch_name):
    """Get all commits on specified branch"""
    if self.mock_mode:
        return []

    try:
        commits = list(self.git_repo.iter_commits(branch_name))
        return commits
    except:
        return []

def get_diff(self, branch, base='main'):
    """Get diff between branch and base"""
    if self.mock_mode:
        return "mock diff"

    return self.git_repo.git.diff(f'{base}...{branch}')

def find_issue_by_label(self, label):
    """Find existing issue with specific label"""
    if self.mock_mode or not self.github_repo:
        return None

    issues = self.github_repo.get_issues(
        state='open',
        labels=[label]
    )

    for issue in issues:
        return issue  # Return first match

    return None

def add_label_to_commit(self, fix_id, attempt):
    """Add label via GitHub API (labels are on PRs/issues, not commits)"""
    # Actually, we'll add labels when creating PR or during workflow
    # Git commits don't have labels, but we can add them via workflow
```

### 6. `.github/workflows/test-and-autofix.yml`
**Complete rewrite:**
```yaml
name: Test and Auto-Fix

on:
  push:
    branches: ['**']
  workflow_dispatch:

jobs:
  build-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Set up Python
        uses: actions/setup-python@v4
        with:
          python-version: '3.9'
      - name: Install dependencies
        run: |
          cd test-project
          pip install -r requirements.txt || true
      - name: Run tests
        id: test
        run: |
          cd test-project
          python test_main.py > ../test-output.log 2>&1
      - name: Upload test logs
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: test-logs
          path: test-output.log

  autonomous-fix:
    needs: build-test
    if: always()
    runs-on: ubuntu-latest
    permissions:
      contents: write
      pull-requests: write
      issues: write
    steps:
      # CASE 4 optimization: Quick check before checkout
      - name: Pre-check
        id: precheck
        run: |
          BRANCH="${GITHUB_REF#refs/heads/}"
          BUILD_STATUS="${{ needs.build-test.result }}"

          if [[ ! "$BRANCH" =~ ^autonomous-fix- ]] && [[ "$BUILD_STATUS" == "success" ]]; then
            echo "Case 4: Nothing to do"
            echo "action=skip" >> $GITHUB_OUTPUT
          else
            echo "action=run" >> $GITHUB_OUTPUT
          fi

      - name: Checkout
        if: steps.precheck.outputs.action == 'run'
        uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Set up Python
        if: steps.precheck.outputs.action == 'run'
        uses: actions/setup-python@v4
        with:
          python-version: '3.9'

      - name: Install agent dependencies
        if: steps.precheck.outputs.action == 'run'
        run: pip install anthropic PyGithub gitpython pyyaml

      - name: Download test logs
        if: steps.precheck.outputs.action == 'run' && needs.build-test.result == 'failure'
        uses: actions/download-artifact@v4
        with:
          name: test-logs
          path: .

      - name: Configure git
        if: steps.precheck.outputs.action == 'run'
        run: |
          git config user.name "Autonomous Agent"
          git config user.email "autonomous-agent@apra.ai"

      - name: Run autonomous agent
        if: steps.precheck.outputs.action == 'run'
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          GITHUB_REPOSITORY: ${{ github.repository }}
        run: |
          python agent/autonomous_agent.py \
            --branch "${GITHUB_REF#refs/heads/}" \
            --build-status "${{ needs.build-test.result }}" \
            --failure-log "test-output.log" \
            --output agent-result.json

      - name: Upload agent result
        if: always() && steps.precheck.outputs.action == 'run'
        uses: actions/upload-artifact@v4
        with:
          name: agent-result
          path: agent-result.json
```

---

## Test Scenarios to Create

### Test 1: Single Attempt Success
**File:** `test-project/bug-simple.py`
```python
# Missing import json (easy fix)
```
**Expected:** CASE 1 → fix → CASE 3 (PR created after 1 attempt)

### Test 2: Multiple Attempts (3 needed)
**File:** `test-project/bug-complex.py`
```python
# Bug 1: Missing import
# Bug 2: Wrong function name
# Bug 3: Syntax error
# Each fix only fixes one bug, so needs 3 attempts
```
**Expected:** CASE 1 → CASE 2 (attempt 2) → CASE 2 (attempt 3) → CASE 3 (PR)

### Test 3: Opus Switch (Attempt 5)
Force agent to need 5 attempts somehow, verify Opus is used

### Test 4: Escalation (Attempt 7)
Force agent to fail 6 times, verify GitHub Issue created

### Test 5: Human Intervention
- Agent creates fix branch
- Human pushes commit to same branch
- Next build fails
- Agent detects human commit and stops

---

## Estimated Work

1. **Refactor existing code:** 1-2 hours
2. **Test scenario 1 (simple):** 30 min
3. **Test scenario 2 (multi-attempt):** 45 min
4. **Test scenario 3 (Opus):** 30 min
5. **Test scenario 4 (Escalation):** 30 min
6. **Test scenario 5 (Human):** 30 min

**Total:** 3-4 hours

---

## Ready to Proceed?

Please confirm:
1. Architecture looks correct?
2. Implementation plan makes sense?
3. Test scenarios cover what you want to see?

Then I'll implement and provide REAL URLs to working examples (no more hallucinations!).
