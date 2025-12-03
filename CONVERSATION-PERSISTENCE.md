# Conversation Persistence in Anthropic API

## Answer to: "Does Anthropic LLM API have session-id/conversation-id concept?"

**Short Answer:** **No built-in session/conversation ID**, but the API supports conversation persistence through the `messages` parameter and optional `metadata` field.

## How the Anthropic Messages API Works

### Stateless API
The Messages API is **stateless** - each API call is independent. There is NO automatic session/conversation ID that persists context between calls.

### Manual Conversation Threading
To maintain conversation context, you must:

1. **Send full conversation history** in every API call via the `messages` parameter:
```python
response = client.messages.create(
    model="claude-sonnet-4-5-20250929",
    max_tokens=1024,
    messages=[
        {"role": "user", "content": "Turn 1 question"},
        {"role": "assistant", "content": "Turn 1 response"},
        {"role": "user", "content": "Turn 2 question"},
        {"role": "assistant", "content": "Turn 2 response"},
        {"role": "user", "content": "Turn 3 question"}  # Current turn
    ]
)
```

2. **Use metadata for custom tracking** (optional):
```python
response = client.messages.create(
    model="claude-sonnet-4-5-20250929",
    messages=[...],
    metadata={
        "user_id": "custom-session-123",
        "conversation_id": "fix-attempt-456",
        "attempt": 3
    }
)
```

**Note:** Metadata is NOT used by the API for conversation threading - it's purely for your own tracking/billing purposes.

## Application to Autonomous Agent

### Current Implementation (Iterative Investigation)
Our `investigate_failure_iteratively()` already does this correctly:

```python
def investigate_failure_iteratively(self, ...):
    conversation_history = []  # Build up conversation

    for turn in range(1, max_turns + 1):
        # Build prompt with FULL conversation history
        prompt = self._build_investigation_prompt(
            error_context=error_context,
            conversation_history=conversation_history,  # ← Full history
            ...
        )

        # Make API call
        response = self.client.messages.create(
            model=model,
            messages=[{"role": "user", "content": prompt}]
        )

        # Add to conversation history
        conversation_history.append({
            'turn': turn,
            'action': response_json.get('action'),
            'reasoning': response_json.get('reasoning'),
            'context_fetched': fetched_context
        })
```

### Your Excellent Idea: Persist Conversation in Git Commits

**Proposal:** Store conversation metadata in git commit messages so context survives across attempts.

**Benefits:**
1. ✅ Context survives even when switching models (haiku → sonnet → opus)
2. ✅ Human reviewers can see the "thought process" in git history
3. ✅ No external database needed - git is the database
4. ✅ Each attempt builds on previous attempts' learnings

**Implementation:**

#### Commit Message Format (Enhanced)
```
🤖 Autonomous Fix Attempt 2: Add missing import statement

**Root Cause Analysis:**
Missing json module import

**Fix Applied:**
Import json at top of file

**Reasoning:**
Previous attempt fixed calculate_age but missed the json import

**Confidence:** 0.92
**Model Used:** claude-sonnet-4-5-20250929

**LLM Investigation:**
Turn 1: Requested test-project/main.py
Turn 2: Requested test-project/utils.py
Turn 3: Proposed fix after seeing full context

**Previous Attempt Context:**
Attempt 1: Fixed missing calculate_age function (confidence: 0.85)
  - Model: claude-sonnet-4-5-20250929
  - Investigation: 2 turns
  - Why it failed: Only addressed first error, didn't check for other issues

---
Fix ID: 19895799892
Attempt: 2
Conversation: Turn 3/5
Total tokens: 12,450
```

#### Code Changes Needed

1. **Extract conversation from previous commits:**
```python
def _extract_previous_investigation_context(self, commits):
    """Extract LLM investigation history from previous commit messages"""
    previous_context = []

    for commit in commits:
        msg = commit.message

        # Extract investigation turns
        turns_match = re.search(r'Turn (\d+)/(\d+)', msg)
        model_match = re.search(r'Model Used: ([\w-]+)', msg)
        reasoning_match = re.search(r'\*\*Reasoning:\*\*\n(.+?)(?:\n\n|\Z)', msg, re.DOTALL)

        if all([turns_match, model_match, reasoning_match]):
            previous_context.append({
                'attempt': len(previous_context) + 1,
                'turns': int(turns_match.group(1)),
                'model': model_match.group(1),
                'reasoning': reasoning_match.group(1).strip(),
                'why_failed': self._extract_why_failed(msg)
            })

    return previous_context
```

2. **Pass to LLM in iterative investigation:**
```python
# In _build_investigation_prompt()
previous_attempts_section = ""
if previous_investigation_context:
    previous_attempts_section = "## Previous LLM Investigations\n\n"
    for ctx in previous_investigation_context:
        previous_attempts_section += f"""
### Attempt {ctx['attempt']} (Model: {ctx['model']})
- Investigation turns: {ctx['turns']}
- Reasoning: {ctx['reasoning']}
- Why it failed: {ctx['why_failed']}

"""

# Add to prompt
prompt = f"""{base_prompt}

{previous_attempts_section}

## Current Task
This is attempt {current_attempt}. Learn from previous investigations above.
"""
```

3. **Store conversation in commit message:**
```python
def _format_commit_message(self, fix_id, attempt, llm_response,
                          previous_attempts, conversation_history):
    # ... existing commit message ...

    # Add LLM investigation summary
    investigation_summary = "\n**LLM Investigation:**\n"
    for turn in conversation_history:
        investigation_summary += f"Turn {turn['turn']}: {turn['action']}\n"
        if turn.get('reasoning'):
            investigation_summary += f"  → {turn['reasoning']}\n"

    # Add previous context
    if previous_attempts:
        prev_context = "\n**Previous Attempt Context:**\n"
        for prev in previous_attempts:
            prev_context += f"Attempt {prev['attempt_num']}: {prev['description']}\n"
            prev_context += f"  - Why it failed: {prev.get('why_failed', 'Unknown')}\n"

    message = f"""{message}

{investigation_summary}
{prev_context}

---
Fix ID: {fix_id}
Attempt: {attempt}
Conversation: Turn {len(conversation_history)}/{max_turns}
Total tokens: {total_tokens}
"""
    return message
```

## Benefits of Git-Based Conversation Persistence

### For LLM Context
- ✅ Each attempt sees what previous attempts tried and why they failed
- ✅ Model switching (sonnet → opus) doesn't lose context
- ✅累積learning across multiple attempts

### For Human Reviewers
- ✅ Transparent "thought process" visible in git history
- ✅ Can see how agent iterated toward solution
- ✅ Easy to audit what LLM was "thinking"

### For System Reliability
- ✅ No external database needed (git is the persistence layer)
- ✅ Survives across workflow runs
- ✅ Works with GitHub's distributed nature

## Limitations to Consider

1. **Commit message size limits:**
   - GitHub: No hard limit but UI truncates after ~65K characters
   - Git: No hard limit
   - **Mitigation:** Summarize conversation, don't store full prompts

2. **Token costs:**
   - More context = more input tokens
   - **Mitigation:** Summarize older attempts, focus on key learnings

3. **Model switching resets conversation:**
   - When upgrading haiku → sonnet → opus, can't literally continue same conversation
   - **But:** Git commit context provides the bridge!

## Recommendation

**Implement git-based conversation persistence:**

1. Store LLM investigation summary in each commit message
2. Extract previous attempt context when starting new attempt
3. Pass to LLM as additional context in investigation prompt
4. Benefits outweigh limitations (small token cost increase)

This gives us the best of both worlds:
- Conversation context survives model switching
- Human-readable audit trail
- No external dependencies
