# Multi-Flavor Build Coordination

## Problem

ApraPipes triggers **7 parallel workflows** per commit:
- Linux x64
- Linux ARM64
- Jetson ARM64
- Windows
- WSL
- Docker
- macOS (if added)

**Without coordination:**
- All 7 fail with same root cause
- All 7 call LLM independently
- Cost: 7 × $0.50 = **$3.50 per commit** 💸
- High probability: same fix works for all

**With coordination:**
- First flavor analyzes with LLM
- Others wait for fix
- Cost: **$0.50 per commit** 💰
- **Savings: 85%+ ($3.00 saved)**

## Solution: GitHub Issues as Distributed Lock

### Architecture

```
Commit abc123 pushed → Triggers 7 workflows in parallel

Workflow 1 (Linux x64)     ─┐
Workflow 2 (Linux ARM64)   ─┤
Workflow 3 (Jetson)        ─┤──> All start simultaneously
Workflow 4 (Windows)       ─┤
Workflow 5 (WSL)           ─┤
Workflow 6 (Docker)        ─┤
Workflow 7 (macOS)         ─┘

┌─────────────────────────────────────────────┐
│ FlavorCoordinator.should_analyze()          │
├─────────────────────────────────────────────┤
│ 1. Check for coordination issue             │
│    Label: "autonomous-coordination"         │
│    Title: "Build Coordination: abc123"      │
│                                             │
│ 2. If NO issue exists:                      │
│    → Create issue                           │
│    → Mark self as "analyzing"               │
│    → Return: should_analyze=TRUE ✅         │
│                                             │
│ 3. If issue EXISTS:                         │
│    → Add self to waiting list               │
│    → Check if fix in progress               │
│    → Return: should_analyze=FALSE ⏭️         │
└─────────────────────────────────────────────┘

FIRST FLAVOR (e.g., Linux x64):
├─ Creates coordination issue
├─ Runs LLM analysis ($0.50)
├─ Creates fix branch: autonomous-fix-abc123
├─ Pushes fix
└─ Marks fix complete in issue

OTHER 6 FLAVORS:
├─ See coordination issue exists
├─ Skip LLM analysis (COST SAVED!)
├─ Wait for fix branch
└─ Re-run tests with fix
```

## Implementation

### 1. Error Signature for Deduplication

```python
def generate_error_signature(error_log: str) -> str:
    """Hash error to detect if it's the same across flavors"""
    # Normalize (remove timestamps, paths, IPs)
    normalized = normalize_error(error_log)
    return sha256(normalized).hexdigest()[:16]
```

### 2. Coordination Check (CASE 1)

```python
# Before running LLM:
coordinator = FlavorCoordinator(github_client, repo, commit_sha)
error_sig = coordinator.generate_error_signature(error_log)

decision = coordinator.should_analyze(
    flavor="linux-x64",
    error_signature=error_sig
)

if not decision['should_analyze']:
    # Skip LLM - another flavor is handling it!
    return AgentResult(
        action_taken='coordination_skip',
        fix_description=f"Skipped: {decision['reason']} (cost saving!)"
    )
```

### 3. Coordination Issue Format

```markdown
## Multi-Flavor Build Coordination

**Commit:** abc123456789
**First Failing Flavor:** linux-x64
**Error Signature:** `a1b2c3d4e5f6`
**Created:** 2025-12-03T12:00:00Z

### Failing Flavors

- ✗ **linux-x64** - First to fail, analyzing with LLM
- ✗ **linux-arm64** - Waiting for fix
- ✗ **jetson-arm64** - Waiting for fix
- ✗ **windows** - Waiting for fix
- ✗ **wsl** - Waiting for fix
- ✗ **docker** - Waiting for fix

### Status

🔄 LLM analysis in progress for linux-x64

### Fix Progress

✅ Fix branch created: autonomous-fix-abc123
✅ PR created: #456
✅ Tests passing on linux-x64

**Other flavors:** Pull fix branch and re-run tests
```

## Configuration

```python
# config.py
class AgentConfig:
    # Enable coordination (set False to disable)
    ENABLE_FLAVOR_COORDINATION = True

    # Max time to wait for another flavor's fix
    MAX_COORDINATION_WAIT_MINUTES = 15
```

```python
# coordination.py
class CoordinationConfig:
    # Can disable for testing
    ENABLED = True

    # Wait timeout
    MAX_WAIT_TIME = 15  # minutes

    # If 3+ flavors waiting, maybe force analyze
    MAX_WAITING_FLAVORS = 3
```

## Environment Variables

Workflows must set:
```yaml
env:
  BUILD_FLAVOR: "linux-x64"  # Or arm64, jetson, windows, etc.
```

This identifies which flavor is running.

## Decision Flow

```python
def should_analyze(flavor, error_sig):
    issue = find_coordination_issue_for_commit()

    if issue is None:
        # First flavor to fail!
        create_coordination_issue(flavor, error_sig)
        return {
            'should_analyze': True,
            'reason': 'first_flavor'
        }

    # Issue exists - not first
    flavors_in_issue = parse_failing_flavors(issue)

    if flavor in flavors_in_issue:
        # Already reported this flavor
        return {
            'should_analyze': False,
            'reason': 'already_coordinated'
        }

    # Add ourselves to the issue
    add_flavor_to_issue(issue, flavor, error_sig)

    if is_fix_in_progress(issue):
        # Another flavor is working on it
        return {
            'should_analyze': False,
            'reason': 'fix_in_progress',
            'wait_for_branch': extract_fix_branch(issue)
        }

    if len(flavors_in_issue) == 1:
        # We're second flavor - close enough, analyze
        return {
            'should_analyze': True,
            'reason': 'second_flavor'
        }

    # Many flavors failed already - wait
    return {
        'should_analyze': False,
        'reason': 'multiple_flavors_waiting'
    }
```

## Cost Savings Example

### Without Coordination

```
Commit breaks all 7 flavors:
├─ linux-x64:    $0.50 LLM analysis
├─ linux-arm64:  $0.50 LLM analysis
├─ jetson-arm64: $0.50 LLM analysis
├─ windows:      $0.50 LLM analysis
├─ wsl:          $0.50 LLM analysis
├─ docker:       $0.50 LLM analysis
└─ macos:        $0.50 LLM analysis
    TOTAL:       $3.50 per commit
```

### With Coordination

```
Commit breaks all 7 flavors:
├─ linux-x64:    $0.50 LLM analysis ✅
├─ linux-arm64:  $0.00 (skipped)
├─ jetson-arm64: $0.00 (skipped)
├─ windows:      $0.00 (skipped)
├─ wsl:          $0.00 (skipped)
├─ docker:       $0.00 (skipped)
└─ macos:        $0.00 (skipped)
    TOTAL:       $0.50 per commit
    SAVINGS:     $3.00 (85%)
```

## Edge Cases

### 1. Platform-Specific Failures

If error signatures differ significantly:
```python
if similarity(error_sig_1, error_sig_2) < 0.7:
    # Different errors - analyze separately
    return {'should_analyze': True}
```

### 2. Timeout Waiting

If first flavor takes >15 minutes:
```python
if time_since_issue_created > MAX_WAIT_TIME:
    # Give up waiting, analyze ourselves
    return {'should_analyze': True, 'reason': 'timeout'}
```

### 3. First Flavor's Fix Doesn't Work

Other flavors will:
1. Try the fix branch
2. Tests still fail
3. Trigger CASE 2 (retry) with context from first flavor
4. Might discover platform-specific issue

## Testing

```bash
# Disable coordination for testing
export COORDINATION_ENABLED=false

# Or in code:
CoordinationConfig.ENABLED = False
```

## Future Enhancements

1. **GitHub Actions API Integration**
   - Query recent workflow runs
   - Detect which flavors failed
   - Auto-close coordination issues when all pass

2. **ML-Based Error Similarity**
   - Better error signature matching
   - Detect platform-specific vs. general failures

3. **Slack/Discord Notifications**
   - Notify when 5+ flavors fail (serious issue)
   - Alert when coordination saves significant cost

4. **Historical Analysis**
   - Track: "85% of failures fixed by same change"
   - Tune: "Wait for fix vs. analyze independently"
