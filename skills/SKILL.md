# Autonomous DevOps Skills

Test skill knowledge base for autonomous agent testing.

## Common Patterns

### Pattern 1: Python Import Errors

**Symptoms:**
- `NameError: name 'X' is not defined`
- `ModuleNotFoundError: No module named 'X'`

**Root Cause:** Missing import statement

**Fix:**
1. Add `import X` at top of file
2. If module is external, add to requirements.txt

**Confidence:** HIGH (0.90)

---

### Pattern 2: JSON Syntax Errors

**Symptoms:**
- `JSON Syntax Error`
- `Expected ',' or '}'`
- Parse error messages

**Root Cause:** Invalid JSON syntax (missing commas, brackets, etc.)

**Fix:**
1. Validate JSON syntax
2. Add missing commas/brackets
3. Remove trailing commas (invalid in strict JSON)

**Confidence:** HIGH (0.95)

---

### Pattern 3: Missing Dependencies

**Symptoms:**
- `ModuleNotFoundError` after import is added
- `Package not found` errors

**Root Cause:** Dependency not installed

**Fix:**
1. Add package to requirements.txt (Python)
2. Add to package.json (Node.js)
3. Run package manager install

**Confidence:** MEDIUM (0.80)

---

## Best Practices

1. **Always check imports first** - Most common error
2. **Validate configuration files** - JSON, YAML, TOML
3. **Update dependencies conservatively** - Pin versions
4. **Test fixes locally when possible**
5. **Document new patterns** - Learn from every failure

---

**Last Updated:** 2025-12-02
**Maintained by:** Autonomous Agent System
