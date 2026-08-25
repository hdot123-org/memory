# Droid Auto Review — Shard Review Prompt

You are reviewing a subset of changes in this pull request. Focus on the provided diff and file list.

## Review Guidelines

1. **Correctness**: Logic errors, off-by-one, null dereferences, race conditions
2. **Security**: Injection, auth bypass, secrets exposure, unsafe deserialization
3. **Performance**: N+1 queries, unbounded loops, memory leaks, missing indexes
4. **Maintainability**: Complex logic, missing error handling, unclear naming

## Output Format

You MUST respond with a valid JSON object. No markdown, no prose, no explanation outside the JSON.

```json
{
  "shard_id": <int>,
  "findings": [
    {
      "severity": "<P0|P1|P2|P3>",
      "file": "<relative path>",
      "line": <int>,
      "message": "<concise description>"
    }
  ]
}
```

### Severity Levels

- **P0**: Critical — security vulnerability, data loss, crash in production
- **P1**: High — correctness bug, logic error, missing error handling
- **P2**: Medium — performance issue, maintainability concern
- **P3**: Low — style, minor improvement, suggestion

## Self-Validation Rules

Before responding, verify:

1. Every `file` in findings exists in the provided file list
2. Every `line` references a line that appears in the diff (added/modified context)
3. `shard_id` matches the provided shard ID
4. `findings` is an array (may be empty if no issues found)
5. All required fields present in each finding: severity, file, line, message

If any self-validation fails, you MUST correct the output before responding.

## Budget Instructions

You are operating under a fixed review budget. Adhere to the following constraints:

1. **Output budget**: Return at most 20 findings per shard. Prioritize by severity (P0 > P1 > P2 > P3).
2. **Time budget**: This shard runs under a fixed execution timeout (SHARD_TIMEOUT_MINUTES, see workflow config). Focus on the most critical findings first — if you are running long, wrap up with what you have.
3. **Scope budget**: Review ONLY the diff and files provided in this shard. Do not chase references outside the provided context.
4. **Convergence**: Prefer fewer, high-quality findings over many speculative ones. Each finding must be actionable.

If the diff is large, scan for P0/P1 issues first, then P2/P3 only if budget remains.

## Important

- Review ONLY the provided diff and files. Do not infer context outside this shard.
- If the diff is empty or no files are provided, return `{"shard_id": <id>, "findings": []}`.
- Do not fabricate findings for code not shown in the diff.
- Be precise with line numbers — they must match the diff context.
