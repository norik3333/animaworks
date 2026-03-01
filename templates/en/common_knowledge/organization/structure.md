# How Organization Structure Works

Organization structure in AnimaWorks is built from each Anima's `status.json` (or `identity.md`) as the Single Source of Truth (SSoT).
`core/org_sync.py` syncs disk values into `config.json`, which is used when building prompts.
This document explains how organization structure is defined, interpreted, and displayed.

## Data Sources and Priority

### supervisor

Hierarchy is defined by each Anima's `supervisor`. Read order:

1. **status.json** — `"supervisor"` key (recommended)
2. **identity.md** — table row `| 上司 | name |` (上司 = supervisor)

If unset, empty, or "なし" (none), the Anima is top-level.
`config.json` `animas.<name>.supervisor` is synced **from disk** by org_sync; manual edits are overwritten.

### speciality

Speciality is resolved in this order:

1. **status.json** — `"speciality"` or `"role"` key
2. **config.json** — `animas.<name>.speciality` (fallback)

## org_sync and config.json

`core/org_sync.py` `sync_org_structure()`:

1. Reads `status.json` / `identity.md` per Anima and extracts supervisor
2. Detects circular references (those Anima are excluded from sync)
3. Updates `config.json` `animas` to match disk
4. Prunes config entries for Anima that no longer exist on disk

**When it runs:**

- On server startup (`animaworks start`)
- When an Anima is added via reconciliation

## Hierarchy via supervisor

- `supervisor: null` or unset → Top-level Anima
- `supervisor: "alice"` → alice is the supervisor

Example in status.json (recommended):

```json
{
  "enabled": true,
  "supervisor": null,
  "speciality": "Strategy & overall management"
}
```

```json
{
  "enabled": true,
  "supervisor": "alice",
  "speciality": "Development lead"
}
```

This produces the following hierarchy:

```
alice (Strategy & overall management)
├── bob (Development lead)
│   └── dave (Backend development)
└── carol (Design & UX)
```

Important constraints:
- The name in `supervisor` must be a known Anima name (English)
- Circular references (e.g. alice → bob → alice) are detected and excluded from sync
- Each Anima can have at most one supervisor

## How Org Context Is Built

`core/prompt/builder.py` `_build_org_context()` derives from directory scan and config.json merge:

1. **Supervisor**: Your `supervisor` value. If unset: "You are top-level"
2. **Subordinates**: All Anima whose `supervisor` is your name
3. **Peers**: Anima with the same `supervisor` (excluding yourself)

This is injected into the system prompt as your org position:

```
## Your Org Position

Your speciality: Development lead

Supervisor: alice (Strategy & overall management)
Subordinates: dave (Backend development)
Peers (members with the same supervisor): carol (Design & UX)
```

## How to Read Your Position

From the "Your org position" section in the system prompt:

| Item | Meaning | Impact on behavior |
|------|---------|-------------------|
| Your speciality | speciality value | You are responsible for questions and decisions in this area |
| Supervisor | Your report target | Where to send progress reports and escalations |
| Subordinates | Anima under you | Who to delegate tasks to and check status with |
| Peers | Members with the same supervisor | Direct coordination partners for related work |

### What to Check

- If supervisor is "(none — you are top-level)", you bear overall responsibility as the top of the organization
- If subordinates is "(none)", you are an executor who does the work yourself
- If peers exist, you can coordinate directly with them on related work

## Behavior When Org Structure Changes

Org structure changes are applied as follows:

1. Edit the target Anima's `status.json` (change `supervisor` / `speciality`)
2. Restart the server or wait for the next org_sync run
3. org_sync updates `config.json`; the new org context is used on the next prompt build

Notes:
- Direct edits to `config.json` `animas` are overwritten when org_sync runs
- SHOULD notify affected Anima of org changes via message

## Example Org Patterns

Below are examples to set in each Anima's `status.json`. org_sync syncs these to config.json.

### Pattern 1: Flat Organization

Everyone is top-level. No hierarchy.

Each Anima's status.json:
```json
{ "supervisor": null, "speciality": "Planning" }
{ "supervisor": null, "speciality": "Development" }
{ "supervisor": null, "speciality": "Design" }
```

```
alice (Planning)
bob (Development)
carol (Design)
```

Characteristics:
- Everyone can interact directly as equals
- Suited for small teams or when each member has independent responsibilities
- Peers for everyone: "(none)" (no shared supervisor)

### Pattern 2: Hierarchical Organization

Clear hierarchy. The most common pattern.

Set `supervisor` and `speciality` in each Anima's status.json:

```
alice (CEO & overall management)
├── bob (Development lead)
│   ├── dave (Backend)
│   └── eve (Frontend)
└── carol (Sales lead)
    └── frank (Customer support)
```

Characteristics:
- bob and carol are peers (same supervisor = alice)
- dave and eve are peers (same supervisor = bob)
- Contact from dave to frank goes via bob → alice → carol → frank (cross-department rule)

### Pattern 3: Specialists + Manager

A few managers oversee many specialists.

```
manager (Project management)
├── dev1 (API development)
├── dev2 (DB design)
├── dev3 (Infrastructure)
└── qa (Quality assurance)
```

Characteristics:
- All members are peers. Direct coordination is easy
- manager handles task allocation and progress management
- Suited for startups and project teams

## Using speciality

`speciality` is free text in `status.json` under `speciality` or `role`.

- Shown next to each Anima's name in org context (e.g. `bob (Development lead)`)
- Helps other Anima decide who to consult or delegate to
- Unset shows as "(unset)"

Effective speciality guidelines:
- Concrete and short: `Backend development`, `Customer support`, `Data analysis`
- Avoid vague: `Various` → `Planning, coordination, progress management`
- Multiple areas: separate with middle dot: `UI design · Frontend development`
