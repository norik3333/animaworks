# Instruction Patterns

A collection of patterns for giving clear, actionable instructions to subordinates and teammates.
Vague instructions cause rework and confusion. Follow this guide to give instructions that others can act on without hesitation.

## Tool Selection

| Tool | Use Case | Notes |
|------|----------|-------|
| `delegate_task` | Task delegation to direct subordinates | Adds to task queue + sends DM. Progress trackable. Direct subordinates only |
| `send_message` | One-on-one requests, reports, questions | `intent` required: one of `report` / `delegation` / `question` |
| `post_channel` | Organization-wide sharing (announcements, resolution reports) | Acknowledgments, thanks, FYI use Board. See `board-guide.md` for details |

**send_message constraints**: Maximum 2 recipients per session, 1 message per recipient. Omitting `intent` causes an error.

## Five Elements of a Clear Instruction

When giving instructions, include these five elements (MUST). Minimize confirmation and rework on the recipient's side.

| Element | Description | MUST/SHOULD |
|---------|-------------|-------------|
| Purpose (why) | Reason and context for this work | MUST |
| Expected outcome (what) | What should exist when complete | MUST |
| Deadline (when) | Completion deadline | MUST (provide a rough target even when not urgent) |
| Constraints (how) | Approach to use, what to avoid | SHOULD |
| When to report | On completion / progress / when issues arise | MUST |

## Good vs Bad Instructions

### Example 1: Data Aggregation Request

**Bad:**
```
send_message(
    to="alice",
    content="Please aggregate the sales data.",
    intent="delegation"
)
```
Problems: Which data, which period, output format, and deadline are unclear.

**Good:**
```
send_message(
    to="alice",
    content="""Please do the monthly sales aggregation.

Purpose: For the management meeting (2/20)
Target: January 2026 sales data (/shared/data/sales_202601.csv)
Deliverable: Department and product category summary table (Markdown format)
Output location: /shared/reports/sales_summary_202601.md
Deadline: 2/18 (Tue) 17:00
Report: Please reply with a result summary when done.""",
    intent="delegation"
)
```

### Example 2: Investigation Request

**Bad:**
```
send_message(
    to="bob",
    content="Look into the API error.",
    intent="delegation"
)
```
Problems: Which API, which error, depth of investigation, and report format are unclear.

**Good:**
```
send_message(
    to="bob",
    content="""Please investigate the GitHub API rate limit error (HTTP 403).

Context: Intermittent since around 3pm yesterday; auto-deploy is failing
Investigate:
1. Error frequency and pattern (log: /var/log/deploy/github-api.log)
2. Current rate limit configuration and usage
3. Mitigation options (retry strategy, token distribution, etc.)

Deadline: Today
Report: Summarize findings and recommended actions in your reply.
Report immediately if you discover something critical.""",
    intent="delegation"
)
```

### Example 3: Review Request

**Bad:**
```
send_message(
    to="carol",
    content="Please take a look at the code.",
    intent="delegation"
)
```

**Good:**
```
send_message(
    to="carol",
    content="""Please review the authentication module code.

Target file: ~/project/auth/token_manager.py (new)
Check:
- Security concerns (token storage, invalidation handling)
- Error handling coverage
- Consistency with existing auth_handler.py

Deadline: Tomorrow morning (2/16)
Report: Reply with "LGTM" if no issues; if changes needed, reply with specific locations and reasons.""",
    intent="delegation"
)
```

## Task Delegation Patterns

### Pattern 1: One-Off Task (Delegation to Direct Subordinate)

For a one-time task delegated to a **direct subordinate**, use `delegate_task`. The task is added to the queue and progress can be tracked with `task_tracker`.

```
delegate_task(
    name="alice",
    instruction="""Please update the API spec (/shared/docs/api-spec.md) with v2.1 changes.

Changes:
- Add pagination parameters to /api/users endpoint
- Add total_count field to response
- See /shared/docs/changelog-v2.1.md for details

Please reply when done.""",
    deadline="2d",
    summary="API spec v2.1 update"
)
```

### Pattern 1b: One-Off Task (Request to Peer / Non-Subordinate)

For requests to someone who is not a direct subordinate, use `send_message` with `intent="delegation"`.

```
send_message(
    to="alice",
    content="""[Request] Document update

Please update the API spec (/shared/docs/api-spec.md) with v2.1 changes.

Changes:
- Add pagination parameters to /api/users endpoint
- Add total_count field to response
- See /shared/docs/changelog-v2.1.md for details

Deadline: 2/16 15:00
Please reply when done.""",
    intent="delegation"
)
```

### Pattern 2: Recurring Task (Delegation of Regular Work)

Pattern for instructing recurring tasks that should be added to Heartbeat or cron. Recurring tasks are not suitable for `delegate_task`; use `send_message` with `intent="delegation"`.

```
send_message(
    to="bob",
    content="""[Recurring Request] Daily log monitoring

From now on, please check the application log for anomalies every morning.

Target: /var/log/app/error.log
Check:
- Count of ERROR/CRITICAL logs in the past 24 hours
- Whether any new error patterns have appeared

Reporting rules:
- No anomalies → no report needed
- 10+ ERROR or new pattern → report to me immediately
- Weekly summary every Friday

Please add this to your Heartbeat checklist.""",
    intent="delegation"
)
```

### Pattern 3: Phased Task (with Milestones)

Pattern for delegating a large task broken into phases.

```
send_message(
    to="carol",
    content="""[Request] New feature design and implementation (3 phases)

Please add the user notification feature.

Phase 1 (by 2/17): Design
- Define notification types (email/Slack/in-app) and priority
- Design data model
→ Reply with design proposal. Proceed to Phase 2 after my approval.

Phase 2 (by 2/20): Implementation
- Implement based on approved design
- Include test code
→ Reply when done.

Phase 3 (by 2/21): Documentation
- Create API spec and user guide

Please reply at the end of each phase.
Consult me if unsure about direction between phases.""",
    intent="delegation"
)
```

## Follow-Up (Progress Check) Patterns

### Pre-Deadline Check

Progress checks are questions; use `intent="question"`.

```
send_message(
    to="alice",
    content="""Checking on the sales aggregation progress.
Deadline is tomorrow (2/18) 17:00 — how is it going?
Let me know if there are any blockers.""",
    intent="question"
)
```

### Post-Deadline Follow-Up

```
send_message(
    to="bob",
    content="""Following up on the log monitoring investigation.
Deadline was today — what's the status?
Let me know if you're stuck; we can extend the deadline if needed.""",
    intent="question"
)
```

### Feedback After Deliverable

Revision requests count as delegation; use `intent="delegation"`.

```
send_message(
    to="carol",
    content="""I've reviewed the design. Overall good direction.

Requested changes:
1. Add exponential backoff to the notification retry logic
2. Include i18n for notification templates in the design

Please send a revised version by 2/18.""",
    intent="delegation"
)
```

## Escalation Criteria

When to handle yourself vs escalate to your supervisor.

### Handle Yourself (No Escalation)

- Work is clearly defined and within your authority
- Minor error with known recovery procedure
- Subordinate question you can answer with your knowledge
- Priorities are clear and no ambiguity in judgment

### Escalate

- MUST: Decision exceeds your authority (e.g. external API integration policy change)
- MUST: Incident affects multiple departments
- MUST: Deadline will clearly be missed
- SHOULD: Unexpected situation with multiple valid options and unclear judgment
- SHOULD: Subordinate escalated and you cannot resolve it

### How to Escalate

Escalation is a report and request for decision to your supervisor; use `intent="report"`. Consider `call_human` for emergencies.

```
send_message(
    to="manager",
    content="""[Escalation] Deploy pipeline incident

Status: Auto-deploy stopped for 12 hours due to GitHub API rate limit
Impact: Cannot deploy v2.1 planned for today
Attempted: Longer retry interval, caching (neither effective)
Decision needed: Whether to issue another GitHub token or switch to manual deploy

Please advise.""",
    intent="report"
)
```

## Instruction Templates

When using these templates with `send_message`, specify `intent` appropriately (request=delegation, report=report, question=question).

### Generic Task Request Template

```
[Request] {task_name}

{Background and purpose (1–2 lines)}

Work:
- {specific work 1}
- {specific work 2}

Deliverable: {what and where to output}
Deadline: {date/time}
Report: {on completion / progress / when issues arise}
```

### Investigation Request Template

```
[Investigation Request] {topic}

Background: {why this investigation is needed}

Investigate:
1. {item 1}
2. {item 2}
3. {item 3}

Deadline: {date/time}
Report: Summarize findings and recommended actions in your reply.
```

### Review Request Template

```
[Review Request] {subject}

Target: {file path or resource}
Check:
- {point 1}
- {point 2}

Deadline: {date/time}
Report: Reply with "LGTM" if no issues; if changes needed, reply with specific items and reasons.
```
