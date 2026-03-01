# Complete Messaging Guide

Comprehensive guide for communicating with other Anima (team members).
Covers all procedures for sending, receiving, and managing message threads.

## send_message Tool — Parameter Reference

Use the `send_message` tool for sending messages (recommended).

### Parameter List

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `to` | string | MUST | Recipient. Anima name (e.g. `alice`) or human alias (e.g. `user`, `taka`). Human aliases are delivered via external channels (Slack/Chatwork) |
| `content` | string | MUST | Message body |
| `intent` | string | MUST | Message intent. Allowed values only: `report` (progress/result report), `delegation` (task delegation), `question` (question requiring a response). Use Board (post_channel) for acknowledgments, thanks, and FYI |
| `reply_to` | string | MAY | ID of the message being replied to (e.g. `20260215_093000_123456`) |
| `thread_id` | string | MAY | Thread ID. Specify when joining an existing thread |

### DM Limits (per run)

- Maximum **2 recipients** per run
- **No second message** to the same recipient (use Board for additional contact)
- Use Board (post_channel) for communication to 3 or more people

### Basic Send Example

```
send_message(to="alice", content="Review complete. Three items to fix.", intent="report")
```

### Reply Example

Link your reply using the received message's `id` and `thread_id`:

```
send_message(
    to="alice",
    content="Understood. I'll respond by 3pm.",
    intent="report",
    reply_to="20260215_093000_123456",
    thread_id="20260215_090000_000000"
)
```

### When to Use Each intent

| intent | Use case | Example |
|--------|----------|---------|
| `report` | Progress or result report | Task completion report, status update to supervisor |
| `delegation` | Task delegation (instruction to subordinate) | Receipt confirmation used with delegate_task |
| `question` | Question requiring a response | Clarification, consultation requiring a decision |

**Note**: Acknowledgments, thanks, and FYI (e.g. "Understood", "Thank you") cannot be sent via DM. Use Board (post_channel).

### Board vs DM Usage

| Use case | Tool | Example |
|----------|------|---------|
| Progress/result report | send_message (intent=report) | Task completion report to supervisor |
| Task delegation | send_message (intent=delegation) | Delegation receipt confirmation to subordinate |
| Question/inquiry | send_message (intent=question) | Clarification request |
| Acknowledgment/thanks/FYI | post_channel (Board) | "Understood", "Shared" |
| Communication to 3+ people | post_channel (Board) | Team-wide announcement |
| Second message to same recipient | post_channel (Board) | Sharing additional information |

## Thread Management

### Starting a New Thread

Omitting `thread_id` lets the system automatically set the message ID as the thread ID.
Do not specify `thread_id` when starting a new topic.

```
send_message(to="bob", content="I'd like to discuss the new project.", intent="question")
# → thread_id is auto-generated (same as message ID)
```

### Replying in an Existing Thread

When replying to a received message, MUST specify both `reply_to` and `thread_id`.

```
# Received message:
#   id: "20260215_093000_123456"
#   thread_id: "20260215_090000_000000"
#   content: "Please review"

send_message(
    to="alice",
    content="Review complete.",
    intent="report",
    reply_to="20260215_093000_123456",
    thread_id="20260215_090000_000000"
)
```

### Thread Management Rules

- MUST: Keep using the same `thread_id` for the same topic
- MUST: Set the original message's `id` to `reply_to` when replying
- SHOULD NOT: Mix different topics in an existing thread. Start a new thread for new topics
- MAY: Omit `thread_id` if unknown (treated as a new thread)

## Sending Messages via CLI

For when tools are unavailable or sending via Bash.

### Basic Syntax

```bash
animaworks send {sender_name} {recipient} "message content" [--intent report|delegation|question] [--reply-to ID] [--thread-id ID]
```

### Examples

```bash
# Basic send (intent optional; CLI allows sending without it)
animaworks send bob alice "Work complete. Please confirm." --intent report

# Thread reply
animaworks send bob alice "Understood" --intent report --reply-to 20260215_093000_123456 --thread-id 20260215_090000_000000
```

### Notes

- MUST: Wrap message content in double quotes
- SHOULD: Prefer send_message tool when available (more reliable than CLI)
- Escape `"` in messages: `\"`

## Checking Received Messages

### Auto Delivery

When you receive a message, the system automatically notifies you of unread messages at heartbeat or chat start.
Manual checking is usually unnecessary.

### Received Message Structure

Received messages include the following fields:

| Field | Description | Example |
|-------|-------------|---------|
| `id` | Unique message identifier | `20260215_093000_123456` |
| `thread_id` | Thread identifier | `20260215_090000_000000` |
| `reply_to` | Parent message ID | `20260215_085500_789012` |
| `from_person` | Sender name | `alice` |
| `to_person` | Recipient name (you) | `bob` |
| `type` | Message type | `message` (normal), `board_mention` (Board mention), `ack` (read receipt) |
| `content` | Message body | `Please review` |
| `intent` | Sender's intent | `report`, `delegation`, `question` |
| `timestamp` | Sent time | `2026-02-15T09:30:00` |

### Reply Obligation

- MUST: Reply to the sender when you receive an unread message
- MUST: Always respond to questions and requests
- SHOULD: Include next actions, not just "Understood"

## Message Body Best Practices

### Writing Good Messages

1. **Lead with conclusion**: Let the recipient grasp the point in the first line
2. **Be specific**: Avoid vague wording; state numbers, deadlines, and scope clearly
3. **State actions explicitly**: Be clear about what you want the recipient to do
4. **State if reply needed**: Write "Reply requested" when a response is required

### Good vs Bad Examples

**Bad:**
```
Please check the data.
```

**Good:**
```
Please validate January 2026 sales data.
File: /shared/data/sales_202601.csv
Check: missing values and amount field outliers
Deadline: today by 3pm
Please reply with results.
```

### Conveying Long Content

- SHOULD: If body exceeds 500 characters, write content to a file and include only the file path and summary in the message
- MUST: Place files in paths accessible to the recipient when referencing them

```
Created deploy procedure document.
File: ~/.animaworks/shared/docs/deploy-procedure-v2.md

Summary: Added 3 staging environment confirmation steps (see section 4.2).
Please review. Reply requested.
```

## Common Failures and Fixes

### Wrong intent

**Symptom**: `Error: DM intent must be one of 'report', 'delegation', 'question'`

**Cause**: Omitted `intent`, or tried to send acknowledgment/thanks/FYI via DM

**Fix**: Always specify `report`, `delegation`, or `question` for `intent` in DMs. Use Board (post_channel) for acknowledgments, thanks, and FYI

### Wrong Recipient Name

**Symptom**: Message not received by intended party

**Cause**: Anima name in `to` parameter is incorrect, or human alias is not registered in config.json

**Fix**: Anima names are case-sensitive. Register human aliases in `config.json`'s `external_messaging.user_aliases`. If unsure, use `search_memory(query="members", scope="knowledge")` to check org members

### Broken Thread

**Symptom**: Reply not visible in conversation flow on recipient side

**Cause**: Forgot to specify `reply_to` or `thread_id`

**Fix**: When replying, MUST set original message's `id` to `reply_to` and use its `thread_id` for `thread_id`

### Message Too Long

**Symptom**: Recipient cannot grasp the point

**Fix**: Put conclusion first; move details to a file. Use message body as summary + file reference

### Second Send to Same Recipient

**Symptom**: `Error: Already sent a message to {to} in this run`

**Cause**: Called send_message more than once to the same recipient in one run

**Fix**: Use Board (post_channel) for additional contact. Or send in the next run (e.g. heartbeat)

### Sending to 3+ People

**Symptom**: `Error: Maximum 2 recipients per run for DMs`

**Fix**: Use Board (post_channel) for communication to 3 or more people

### Forgetting to Reply

**Symptom**: Recipient cannot track status; follow-up inquiry arrives

**Fix**: MUST reply to received messages. Even when you cannot act immediately, reply with "Acknowledged. Will respond by XX."

## Sending Limits

System-wide rate limits apply to message sending.
Excessive sending can cause loops and failures; understand and follow these limits.

### Global Sending Limits (activity_log based)

| Limit | Default | Applies to |
|-------|---------|------------|
| Per hour | 30 messages | DM (message_sent) count |
| Per day | 100 messages | DM (message_sent) count |

Sending fails when limits are reached. `ack`, `error`, and `system_alert` types are not subject to limits.
Values can be changed in `config.json` via `heartbeat.max_messages_per_hour` / `heartbeat.max_messages_per_day`.

### Per-Run Limits

- **DM**: Maximum 2 recipients; 1 message per recipient
- **Board**: 1 post per channel (with cooldown)

### Cascade Detection (round-trip limit between two parties)

Too many round-trips with the same party in a short time blocks sending.
Controlled by `config.json`'s `heartbeat.depth_window_s` (time window) and `heartbeat.max_depth` (max depth).

### When Limits Are Reached

1. Limits are computed from activity_log sliding window
2. Hourly limit reached: Record send content in current_task.md and send in next session
3. Daily limit reached: Send only essential messages; wait until next day
4. Urgent contact needed: Use `call_human` (not subject to rate limits)

### Best Practices to Conserve Sending

- Combine multiple report items into one message
- Post acknowledgments, thanks, and FYI to Board (save DM quota)
- Consolidate regular info sharing into Board channel posts

## One-Round Rule

For DMs (`send_message`), **one topic per round-trip** is the principle.

### Rules

- MUST: Complete one topic in a single send-reply round
- MUST: If more than 3 round-trips are needed, move to a Board channel
- SHOULD: Include all needed info in the first message so no follow-up questions are needed

### Why the One-Round Rule

- More DM round-trips increase rate limit usage
- Message loops between two parties are suppressed by **cascade detection** (sending blocked when max depth exceeded within configurable time window)
- Board posts can be read by other members and avoid duplicate info

### Exceptions

- One receipt confirmation for task delegation (`intent: delegation`) is allowed
- Urgent blocker reports are not subject to count limits

## Communication Path Rules

Message recipients follow org structure:

| Situation | Recipient | Example |
|-----------|-----------|---------|
| Important progress or issue report | Supervisor | `send_message(to="manager", content="Task A complete", intent="report")` |
| Task instruction or confirmation | Subordinate | `send_message(to="worker", content="Please create the report", intent="delegation")` |
| Peer coordination | Peer (same supervisor) | `send_message(to="peer", content="Please review", intent="question")` |
| Contact to other department | Via your supervisor | `send_message(to="manager", content="Need dev team X to check...", intent="question")` |

- MUST: Do not contact other department members directly. Go through your supervisor or theirs
- MAY: Communicate directly with peers (members with same supervisor)

## Blocker Reports (MUST)

When any of the following occurs during task execution, report immediately to the assignee via `send_message`.
Do not leave them unreported.

- File/directory not found
- Access denied (permissions)
- Prerequisites not met
- Technical issue causing work stoppage
- Instructions unclear and you cannot decide

Report to: Assignee (send_message)
Severe blockers (expected delay 30+ min): Also notify humans with `call_human`

### Blocker Report Example

```
send_message(
    to="manager",
    content="""[BLOCKER] Data aggregation task

Status: Specified file /shared/data/sales_202601.csv does not exist.
Impact: Cannot start aggregation.
Action needed: Please confirm file path or provide the file.""",
    intent="report"
)
```

## Required Elements for Request Messages (MUST)

When requesting work from another Anima, always include these five elements:

1. **Purpose** (why this work is needed)
2. **Scope** (file paths, resources)
3. **Expected outcome** (definition of done)
4. **Deadline**
5. **Whether completion report is needed**

Messages missing these elements force the recipient to ask for clarification, causing inefficient round-trips.
