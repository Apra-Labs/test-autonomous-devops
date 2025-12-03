# Autonomous Agent Deployment Plan for ApraPipes

## Objective

Integrate the autonomous DevOps agent into ApraPipes workflows, starting with:
1. **CI-Win-NoCUDA** (Windows without CUDA)
2. **CI-Linux-NoCUDA** (Linux without CUDA)

## Approach Comparison: Git Submodule vs Copy

### Option 1: Git Submodule ✅ RECOMMENDED

**Pros:**
- ✅ No clutter in ApraPipes repo (agent code stays in separate repo)
- ✅ Easy to update (just update submodule reference)
- ✅ Clear separation of concerns
- ✅ Same agent code shared across multiple repos if needed
- ✅ Version pinning (can lock to specific commit)
- ✅ Independent testing in agent repo

**Cons:**
- ⚠️ Adds `.gitmodules` file (1 small file)
- ⚠️ Slightly more complex checkout (already using submodules though)
- ⚠️ Need to run `git submodule update --init` in workflows (already done)

**Implementation:**
```bash
# In ApraPipes repo
git submodule add https://github.com/Apra-Labs/test-autonomous-devops.git .github/autonomous-agent
git commit -m "Add autonomous agent as submodule"
```

### Option 2: Copy Files

**Pros:**
- ✅ Simple - everything in one repo
- ✅ No submodule management

**Cons:**
- ❌ Clutters ApraPipes with 20+ Python files
- ❌ Hard to update (need to manually copy files)
- ❌ Two sources of truth (can get out of sync)
- ❌ Harder to test agent independently

**Implementation:**
```bash
# Copy agent code to ApraPipes
cp -r /path/to/agent .github/autonomous-agent/
```

---

## RECOMMENDED: Git Submodule Approach

### Phase 1: Setup Submodule (One-time)

```bash
cd /Users/akhil/git/ApraPipes2

# Add autonomous agent as submodule
git submodule add https://github.com/Apra-Labs/test-autonomous-devops.git .github/autonomous-agent

# Commit the submodule
git commit -m "feat: Add autonomous DevOps agent as submodule

Adds autonomous agent for automatic build failure analysis and fixes.
Agent will trigger on workflow failures to:
- Analyze error logs using LLM
- Propose fixes
- Create PRs automatically

Starting with Win-NoCUDA and Linux-NoCUDA workflows."

git push origin main
```

**File added:** `.gitmodules` (5 lines)
```ini
[submodule ".github/autonomous-agent"]
    path = .github/autonomous-agent
    url = https://github.com/Apra-Labs/test-autonomous-devops.git
```

---

### Phase 2: Update Win-NoCUDA Workflow

**File:** `.github/workflows/CI-Win-NoCUDA.yml`

Add new job at the end (after `win-nocuda-publish`):

```yaml
  win-nocuda-autofix:
    needs: win-nocuda-build-test
    if: failure() && github.event_name == 'push' && github.ref == 'refs/heads/main'
    permissions:
      contents: write
      pull-requests: write
      issues: write
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
        with:
          submodules: 'recursive'

      - uses: actions/setup-python@v4
        with:
          python-version: '3.9'

      - name: Install dependencies
        run: pip install anthropic PyGithub gitpython pyyaml

      - name: Download build logs
        uses: actions/download-artifact@v4
        with:
          name: BuildLogs_Win-nocuda_1
          path: build-logs/

      - name: Run autonomous agent
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          BUILD_FLAVOR: Win-nocuda
          GITHUB_REPOSITORY: ${{ github.repository }}
        run: |
          python .github/autonomous-agent/agent/autonomous_agent.py \
            --branch ${{ github.ref_name }} \
            --build-status failure \
            --failure-log build-logs/vcpkg/buildtrees \
            --output agent-result.json

      - name: Upload agent result
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: AgentResult_Win-nocuda
          path: agent-result.json
```

**Key points:**
- ✅ Only runs on `failure()` of build-test job
- ✅ Only runs on `main` branch pushes (not PRs)
- ✅ Uses downloaded build logs from previous job
- ✅ Sets `BUILD_FLAVOR=Win-nocuda` for coordination
- ✅ Real LLM calls (not mock mode)

---

### Phase 3: Update Linux-NoCUDA Workflow

**File:** `.github/workflows/CI-Linux-NoCUDA.yml`

Add similar job:

```yaml
  linux-nocuda-autofix:
    needs: linux-nocuda-build-test
    if: failure() && github.event_name == 'push' && github.ref == 'refs/heads/main'
    permissions:
      contents: write
      pull-requests: write
      issues: write
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v3
        with:
          submodules: 'recursive'

      - uses: actions/setup-python@v4
        with:
          python-version: '3.9'

      - name: Install dependencies
        run: pip install anthropic PyGithub gitpython pyyaml

      - name: Download build logs
        uses: actions/download-artifact@v4
        with:
          name: BuildLogs_Linux_0
          path: build-logs/

      - name: Run autonomous agent
        env:
          ANTHROPIC_API_KEY: ${{ secrets.ANTHROPIC_API_KEY }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          BUILD_FLAVOR: Linux
          GITHUB_REPOSITORY: ${{ github.repository }}
        run: |
          python .github/autonomous-agent/agent/autonomous_agent.py \
            --branch ${{ github.ref_name }} \
            --build-status failure \
            --failure-log build-logs/vcpkg/buildtrees \
            --output agent-result.json

      - name: Upload agent result
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: AgentResult_Linux
          path: agent-result.json
```

---

### Phase 4: Add ANTHROPIC_API_KEY Secret

**In GitHub Repository Settings:**

1. Go to: `https://github.com/Apra-Labs/ApraPipes/settings/secrets/actions`
2. Click "New repository secret"
3. Name: `ANTHROPIC_API_KEY`
4. Value: `<your Anthropic API key>`
5. Click "Add secret"

**To get API key:**
```bash
# If you don't have one yet
# Sign up at: https://console.anthropic.com/
# Create API key in: Account Settings > API Keys
```

---

## Testing Strategy

### Step 1: Test with Intentional Failure (Dry Run)

**Create a test branch:**
```bash
git checkout -b test-autonomous-agent
# Make a small intentional error in code
# Push to main temporarily or use workflow_dispatch
```

**Expected behavior:**
1. ✅ Win-NoCUDA builds and fails
2. ✅ win-nocuda-autofix job runs
3. ✅ Agent analyzes logs
4. ✅ Agent creates branch `autonomous-fix-*`
5. ✅ Agent creates PR with fix
6. ✅ Coordination issue created (if multiple flavors fail)

### Step 2: Monitor First Real Failure

**When next real failure happens:**
1. Check Actions tab for `win-nocuda-autofix` job
2. Review agent logs
3. Check if PR was created
4. Review PR quality
5. Test the fix

### Step 3: Expand to More Workflows (After Success)

Once Win-NoCUDA and Linux-NoCUDA work well:
```yaml
# Add to these workflows:
- CI-Win-CUDA.yml
- CI-Linux-CUDA.yml
- CI-Linux-ARM64.yml
- CI-Linux-CUDA-Docker.yml
- CI-Linux-CUDA-wsl.yml
```

---

## Coordination Setup (Multi-Flavor)

**When both workflows are enabled, coordination prevents duplicate LLM analysis:**

### Scenario: Both Win-NoCUDA and Linux-NoCUDA fail on same commit

```
Timeline:
T+0:   Both workflows start building commit abc123
T+15:  Win-NoCUDA fails → win-nocuda-autofix starts
       → Creates coordination issue #123
       → Runs LLM analysis ($0.60)
       → Creates fix branch and PR

T+16:  Linux-NoCUDA fails → linux-nocuda-autofix starts
       → Finds coordination issue #123
       → SKIPS LLM analysis (SAVES $0.60)
       → Adds comment to issue #123
       → Exits gracefully
```

**Cost savings:**
- Without coordination: 2 × $0.60 = $1.20
- With coordination: 1 × $0.60 = $0.60
- **Savings: 50%** (will be 85% when all 7 flavors enabled)

---

## Directory Structure in ApraPipes

```
ApraPipes/
├── .gitmodules                           # NEW (5 lines)
├── .github/
│   ├── autonomous-agent/                 # NEW (submodule)
│   │   ├── agent/
│   │   │   ├── autonomous_agent.py
│   │   │   ├── coordination.py
│   │   │   ├── llm_client.py
│   │   │   ├── git_operations.py
│   │   │   └── ... (8 files total)
│   │   ├── README.md
│   │   └── COORDINATION-SIMPLIFIED.md
│   └── workflows/
│       ├── CI-Win-NoCUDA.yml            # MODIFIED (add autofix job)
│       └── CI-Linux-NoCUDA.yml          # MODIFIED (add autofix job)
└── ... (rest of ApraPipes unchanged)
```

**Clutter in ApraPipes:** Only `.gitmodules` (5 lines)
**Agent code:** Isolated in submodule at `.github/autonomous-agent/`

---

## Updating the Agent (Future)

**When agent is improved in test-autonomous-devops repo:**

```bash
cd /Users/akhil/git/ApraPipes2

# Update submodule to latest
cd .github/autonomous-agent
git pull origin main

# Or update to specific version
git checkout <specific-commit-sha>

# Commit the update
cd ../..
git add .github/autonomous-agent
git commit -m "Update autonomous agent to latest version"
git push
```

---

## Rollback Plan (If Needed)

**If agent causes issues:**

### Quick disable (in workflows):
```yaml
# Change this:
if: failure() && github.event_name == 'push' && github.ref == 'refs/heads/main'

# To this:
if: false  # Temporarily disabled
```

### Complete removal:
```bash
# Remove submodule
git submodule deinit -f .github/autonomous-agent
git rm -f .github/autonomous-agent
rm -rf .git/modules/.github/autonomous-agent

# Remove autofix jobs from workflows
# Commit and push
```

---

## Cost Monitoring

**Set up budget alerts in Anthropic Console:**

1. Go to: https://console.anthropic.com/settings/billing
2. Set monthly budget alert (e.g., $10/month)
3. Monitor usage after deployment

**Expected costs (first month with 2 workflows):**
- Estimated failures: 4-8 per month
- Cost per failure: $0.60
- **Expected: $2.40-4.80/month**

**Full deployment (7 workflows):**
- Without coordination: 7 × 8 failures × $0.60 = $33.60/month
- With coordination: 1 × 8 failures × $0.60 = $4.80/month
- **Savings: $28.80/month** ($345/year)

---

## Next Steps Summary

### 1. Setup (One-time - 10 minutes)
```bash
# Add submodule
cd /Users/akhil/git/ApraPipes2
git submodule add https://github.com/Apra-Labs/test-autonomous-devops.git .github/autonomous-agent
git commit -m "feat: Add autonomous DevOps agent as submodule"
git push
```

### 2. Add API Key Secret (5 minutes)
- Get Anthropic API key
- Add as `ANTHROPIC_API_KEY` in GitHub secrets

### 3. Update Workflows (20 minutes)
- Modify `CI-Win-NoCUDA.yml` - add autofix job
- Modify `CI-Linux-NoCUDA.yml` - add autofix job
- Commit and push

### 4. Test (Next failure)
- Wait for natural failure OR create test failure
- Monitor agent behavior
- Review PR quality

### 5. Expand (After validation)
- Add to remaining 5 workflows
- Monitor coordination working across all 7 flavors

---

## Questions?

**Q: What if agent creates bad PR?**
A: Human reviews all PRs before merge. Agent just automates the investigation.

**Q: What if it costs too much?**
A: Set budget alerts. Can disable with `if: false` instantly.

**Q: What if submodule adds complexity?**
A: ApraPipes already uses submodules (line 102: `submodules: 'recursive'`). This adds one more.

**Q: Can we test without affecting production?**
A: Yes, use a test branch first or add `if: github.repository == 'your-test-repo'`

---

## Recommendation

✅ **Use Git Submodule approach**
✅ **Start with Win-NoCUDA and Linux-NoCUDA only**
✅ **Validate for 1-2 weeks**
✅ **Then expand to all 7 workflows**

The submodule keeps ApraPipes clean while giving you all the benefits of the autonomous agent!
