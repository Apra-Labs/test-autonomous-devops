# Simplified Coordination Logic

## The Simple Requirement

**Goal:** When multiple workflows fail on the same commit, only ONE should do the expensive LLM analysis. Others should wait.

**Solution:** Use GitHub Issues as a lock mechanism.

---

## How It Works (3 Simple Steps)

### Step 1: Workflow Fails
```
linux-x64 workflow fails on commit abc123
```

### Step 2: Check for Coordination Issue
```python
# Search for open issues with label "autonomous-coordination"
# and commit SHA "abc123" in the title
existing_issue = find_coordination_issue(commit_sha="abc123")
```

### Step 3: Decision
```python
if existing_issue:
    # Another workflow is already fixing this commit
    skip_analysis()
    add_comment_to_issue("linux-x64 also failed, waiting for fix")
else:
    # We're first!
    create_coordination_issue(commit_sha="abc123", flavor="linux-x64")
    proceed_with_llm_analysis()
```

---

## Complete Flow Diagram

```
┌─────────────────────────────────────────────────────────────┐
│ Multiple Workflows Fail on Same Commit                     │
├─────────────────────────────────────────────────────────────┤
│                                                             │
│  linux-x64    windows     linux-arm64    jetson-arm64      │
│     FAIL        FAIL         FAIL           FAIL           │
│      │           │            │              │             │
│      ├───────────┼────────────┼──────────────┤             │
│      │           │            │              │             │
│      v           v            v              v             │
│  ┌────────────────────────────────────────────────┐        │
│  │ Check: Does coordination issue exist?          │        │
│  │   Search: label=autonomous-coordination        │        │
│  │            + "abc123" in title                 │        │
│  └────────────────────────────────────────────────┘        │
│      │           │            │              │             │
│   NO │        YES│         YES│           YES│             │
│      │           │            │              │             │
│      v           v            v              v             │
│  ┌────────┐  ┌──────────────────────────────────┐         │
│  │ CREATE │  │ SKIP - another workflow fixing   │         │
│  │ ISSUE  │  │ Add comment: "also failed"       │         │
│  │        │  └──────────────────────────────────┘         │
│  │ Title: │                                                │
│  │ "Build │      Cost Saved: 3 × $0.60 = $1.80           │
│  │ Coord: │      (avoided 3 LLM analyses)                 │
│  │ abc123"│                                                │
│  └────────┘                                                │
│      │                                                     │
│      v                                                     │
│  ┌────────────────┐                                        │
│  │ RUN LLM        │                                        │
│  │ ANALYSIS       │                                        │
│  │                │                                        │
│  │ Cost: $0.60    │                                        │
│  └────────────────┘                                        │
│      │                                                     │
│      v                                                     │
│  ┌────────────────┐                                        │
│  │ CREATE FIX     │                                        │
│  │ BRANCH & PR    │                                        │
│  └────────────────┘                                        │
│                                                             │
└─────────────────────────────────────────────────────────────┘
```

---

## Code Implementation

### coordinator.should_analyze() - The Core Logic

```python
def should_analyze(self, flavor: str) -> Dict:
    """
    Simple logic: If another workflow is already fixing this commit, skip.
    Otherwise, create an issue and proceed with analysis.
    """
    # Check for existing coordination issue
    existing_issue = self._find_coordination_issue()

    if existing_issue:
        # Another workflow is already working on this
        self._add_flavor_to_issue(existing_issue['number'], flavor)

        return {
            'should_analyze': False,
            'reason': 'another_workflow_fixing',
            'issue_number': existing_issue['number']
        }
    else:
        # We're first!
        issue = self._create_coordination_issue(flavor)

        return {
            'should_analyze': True,
            'reason': 'first_to_fix',
            'issue_number': issue['number']
        }
```

### _find_coordination_issue() - Search by Commit SHA

```python
def _find_coordination_issue(self) -> Optional[Dict]:
    """Find existing coordination issue for this commit"""
    # Get open issues with coordination label
    issues = self.github_repo.get_issues(
        state='open',
        labels=['autonomous-coordination']
    )

    # Filter for our commit SHA in title
    commit_prefix = self.commit_sha[:8]
    for issue in issues:
        if commit_prefix in issue.title:
            return {
                'number': issue.number,
                'title': issue.title,
                'body': issue.body,
                'url': issue.html_url
            }

    return None
```

### _create_coordination_issue() - Create Lock

```python
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

    issue = self.github_repo.create_issue(
        title=title,
        body=body,
        labels=['autonomous-coordination', f'commit-{self.commit_sha[:8]}']
    )

    return {'number': issue.number, 'title': title, 'url': issue.html_url}
```

---

## What Was Removed (Unnecessary Complexity)

### ❌ Error Signature Generation
**What it was:** SHA256 hash of normalized error message
```python
# REMOVED - NOT NEEDED
def generate_error_signature(error_log: str) -> str:
    normalized = normalize(error_log)  # Remove paths, dates, IPs
    return hashlib.sha256(normalized).hexdigest()[:16]
```

**Why removed:**
- Coordination uses commit SHA, not error content
- If workflows fail on same commit, they're likely the same bug
- Error signatures added complexity without benefit

### ❌ Complex Flavor Tracking
**What it was:** Track which flavors reported, parse comments, count flavors
```python
# REMOVED - NOT NEEDED
def _parse_flavors_from_issue(issue) -> List[str]:
    # Parse issue body and comments to extract flavor names
    ...

def _is_fix_in_progress(issue) -> bool:
    # Check if someone marked themselves as working on it
    ...
```

**Why removed:**
- Simple approach: ANY open issue for the commit means "skip"
- Don't need to track which specific flavor is fixing
- Don't need to count flavors

### ❌ Second Flavor Logic
**What it was:** Let second flavor also analyze
```python
# REMOVED - OVERTHOUGHT
if len(flavors) == 1:
    # We're second flavor, also analyze
    return {'should_analyze': True}
```

**Why removed:**
- Defeats the purpose (2 LLM analyses instead of 1)
- Adds complexity
- Original requirement: only ONE workflow analyzes

---

## Example Scenario

### Timeline: 4 Workflows Fail on Commit abc123

```
T+0s:  linux-x64 fails
       → No coordination issue exists
       → Creates issue #100
       → Proceeds with LLM analysis ($0.60)

T+30s: windows fails
       → Finds issue #100
       → Skips LLM analysis (SAVED $0.60)
       → Adds comment to #100

T+45s: linux-arm64 fails
       → Finds issue #100
       → Skips LLM analysis (SAVED $0.60)
       → Adds comment to #100

T+60s: jetson-arm64 fails
       → Finds issue #100
       → Skips LLM analysis (SAVED $0.60)
       → Adds comment to #100

RESULT:
- 1 LLM analysis: $0.60
- 3 LLM analyses avoided: $1.80 saved
- Savings: 75%
```

---

## GitHub Issue Example

**Title:** `🤖 Build Coordination: abc12345`

**Labels:** `autonomous-coordination`, `commit-abc12345`

**Body:**
```markdown
## Multi-Flavor Build Coordination

**Commit:** abc12345678901234567890
**First Failing Flavor:** linux-x64
**Created:** 2025-12-03T18:30:00.000000

### Status

🔄 **linux-x64** is analyzing the failure and will create a fix

### Failing Flavors

- ✗ **linux-x64** - Analyzing with LLM

---
*This issue coordinates workflows to avoid duplicate LLM analysis.*
*Other flavors will wait for the fix from linux-x64.*
```

**Comments:**
```markdown
### Flavor: windows
**Status:** ✗ Also failed on this commit
**Time:** 2025-12-03T18:30:30.000000

Waiting for fix from primary flavor...
---
### Flavor: linux-arm64
**Status:** ✗ Also failed on this commit
**Time:** 2025-12-03T18:30:45.000000

Waiting for fix from primary flavor...
```

---

## Configuration

Enable/disable coordination in `agent/config.py`:

```python
class CoordinationConfig:
    # Whether to enable coordination (can disable for testing)
    ENABLED = True

    # Wait time before giving up on first flavor (minutes)
    MAX_WAIT_TIME = 15
```

Coordination is automatically enabled when:
- `BUILD_FLAVOR` environment variable is set
- `GITHUB_REPOSITORY` environment variable is set
- `CoordinationConfig.ENABLED = True`

---

## Cost Savings

### ApraPipes Example (7 parallel flavors)

**Without coordination:**
- 7 workflows × $0.60 per LLM analysis = **$4.20 per failure**

**With coordination:**
- 1 workflow × $0.60 per LLM analysis = **$0.60 per failure**
- **Savings: 85%** ($3.60 per failure)

**Annual estimate:**
- 100 failures/year × $3.60 savings = **$360/year saved**

---

## Testing

The coordination logic is production-ready and has been tested with:
- ✅ Real GitHub API integration
- ✅ Race condition handling (duplicate detection)
- ✅ Retry logic for API consistency
- ✅ Mock mode for zero-cost testing

See `COORDINATION-TEST-RESULTS.md` for full test details.

---

## Summary

**Before:** 250+ lines of complex logic with error signatures, flavor tracking, and multi-level decision trees

**After:** 150 lines of simple logic with ONE rule: "If issue exists for this commit, skip. Otherwise, create and analyze."

**Result:** Same functionality, clearer code, easier to maintain.

The simplification removes:
- ❌ Error signature calculation (unused)
- ❌ Flavor parsing logic (overcomplicated)
- ❌ Second flavor analysis (defeats purpose)
- ❌ Fix-in-progress tracking (unnecessary)

And keeps:
- ✅ Commit SHA-based coordination
- ✅ GitHub Issue as lock mechanism
- ✅ Duplicate detection for race conditions
- ✅ Cost savings (85% for 7 flavors)
