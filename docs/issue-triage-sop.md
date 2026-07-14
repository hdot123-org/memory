# Issue Triage SOP (v0.9.0)

This page documents the standard operating procedure for triaging
incoming issues on the memory-core repository. It defines priority
levels, SLAs, the labeling workflow, and the triage cadence.

## Severity Levels

Every issue must be assigned exactly one of the following priorities.
The priority drives the SLA (see next section).

| Priority | Name           | Definition                                                                 |
|----------|----------------|----------------------------------------------------------------------------|
| **P0**   | Critical       | Complete loss of core functionality, data corruption, security breach, or all users blocked. |
| **P1**   | High           | Major feature broken for a large share of users with no known workaround.  |
| **P2**   | Medium         | Feature degraded or broken for a subset of users; workaround exists.       |
| **P3**   | Low            | Minor bug, polish issue, or nice-to-have enhancement with limited impact.  |

Guidance for ambiguous cases:

- If you're unsure between P1 and P2, start at **P1** and downgrade
  after investigating scope.
- Documentation-only issues default to **P3** unless they block a
  release.
- Issues that only affect the CI tooling or advisory jobs default to
  **P2** unless they block merges, in which case they are **P1**.

## SLA Definitions

SLAs start from the moment the issue is labeled with its priority.

| Priority | First response | Resolution target        | Update cadence         |
|----------|----------------|--------------------------|------------------------|
| **P0**   | within 1 hour  | within 24 hours          | every 4 hours          |
| **P1**   | within 4 hours | within 3 days            | daily                  |
| **P2**   | within 1 day   | within 2 weeks           | every 3 days           |
| **P3**   | within 1 week  | next minor release       | weekly                 |

Notes:

- "First response" means an acknowledgement comment with the next
  steps, not a fix.
- "Resolution target" means a merged fix on `main` or a documented
  workaround posted on the issue.
- SLAs are best-effort for a small open-source team; if a deadline
  will be missed, comment on the issue with a revised ETA before the
  SLA elapses.

## Labeling Workflow

Every incoming issue goes through the following labeling steps:

1. **Triage owner picks the issue** from the `needs-triage` queue (see
   cadence below).
2. **Assign priority**: add exactly one of `P0`, `P1`, `P2`, or `P3`.
3. **Assign type**: add one of
   `bug`, `enhancement`, `documentation`, `tooling`, `question`.
4. **Assign area**: add one or more of
   `area: core`, `area: hooks`, `area: cli`, `area: ci`,
   `area: telemetry`, `area: docs`.
5. **Remove `needs-triage`** once the above labels are set.
6. **Assign an owner** if the issue is actionable; otherwise leave
   unassigned but labeled.
7. **Milestone**: add the issue to the relevant milestone (e.g.
   `v0.9.1`, `v0.10.0`).

Issue templates on GitHub pre-fill `needs-triage` and a suggested
type, so the triage owner only needs to verify and refine.

### Labels at a Glance

```
Priority:     P0 | P1 | P2 | P3
Type:         bug | enhancement | documentation | tooling | question
Area:         area: core | area: hooks | area: cli | area: ci | area: telemetry | area: docs
Workflow:     needs-triage   (removed after triage)
```

## Triage Cadence

| Activity                | Cadence        | Owner                |
|-------------------------|----------------|----------------------|
| Triage new issues       | weekly (Monday)| rotating triage owner|
| P0/P1 hot-review        | on-demand      | on-call maintainer   |
| Re-prioritization sweep | every 2 weeks  | triage owner + lead  |
| Stale-issue close       | monthly        | triage owner         |

### Weekly Triage Session

- **When:** every Monday, 30-minute timebox.
- **Scope:** every issue labeled `needs-triage` since the previous
   session.
- **Output:** all new issues labeled with priority, type, area, and
   milestone; `needs-triage` removed.

### On-Call for P0/P1

The on-call maintainer is notified via the repository's issue
notifications. For P0 issues, the on-call owner must:

1. Acknowledge the issue within the 1-hour SLA.
2. Create a `hotfix/...` branch and open a draft PR.
3. Update the issue with the branch link and an ETA.
4. Coordinate the merge and release with the lead.

### Monthly Stale-Issue Close

Once per month, the triage owner runs a stale sweep:

- Issues with no activity for 90 days and priority `P3` are closed
   as `stale`.
- Higher-priority issues are pinged for status and re-labeled
  accordingly.

## Templates

### Acknowledgement Comment

    Thanks for the report! I've triaged this as <P0/P1/P2/P3> and
    added the <area> label. Next steps:
    - <investigate / reproduce / draft PR>
    - Target ETA: <date>

### Handoff Comment

    Handing off to @<owner> for follow-up. Priority: <P?>, area: <area>.

## References

- GitHub repository: `https://github.com/hdot123/memory`
- Labels: `https://github.com/hdot123/memory/labels`
- Code quality metrics: `docs/code-quality-metrics.md`
- OTel setup: `docs/otel-setup.md`
