# How Organization Structure Works

Organization structure in AnimaWorks is built from each Anima's `status.json` (or `identity.md`) as the Single Source of Truth (SSoT).
`core/org_sync.py` syncs the **supervisor** on disk into `config.json`, which is used when building prompts.
This document explains how organization structure is defined, interpreted, and displayed.

## Data Sources and Priority

### supervisor (Supervisor)

Hierarchy is defined by each Anima's `supervisor`. Read order:

1. **status.json** — `"supervisor"` key (recommended)
2. **identity.md** — table row `| 上司 | name |` (Japanese only; parsed by `read_anima_supervisor` in `core/config/models.py`)

If `supervisor` is unset, empty, or one of "なし", "(なし)", "（なし）", "-", "---", the Anima is top-level.
`config.json` `animas.<name>.supervisor` is **synced from disk** by org_sync; manual edits are overwritten.

### speciality (Specialty)

Specialty is resolved by `_scan_all_animas()` in `core/prompt/builder.py` in this order:

1. **status.json** — `"speciality"` key (free text)
2. **config.json** — `animas.<name>.speciality` (fallback when `speciality` key is absent in status.json)
3. **status.json** — `"role"` key (final fallback when above do not resolve; role names: engineer, researcher, manager, writer, ops, general)

**Note:** org_sync does **not** sync speciality. Speciality is resolved on each prompt build from disk and config.
Anima created with `animaworks anima create --from-md` get `role` in `status.json` but not `speciality`.
For custom display (e.g. "Development lead"), add `"speciality": "Development lead"` manually to `status.json`.

## Syncing config.json via org_sync

`sync_org_structure()` in `core/org_sync.py`:

1. Reads `status.json` / `identity.md` per Anima directory (only where `identity.md` exists) and extracts supervisor (`read_anima_supervisor`)
2. Detects circular references (affected Anima are excluded from sync)
3. Updates `config.json` `animas.<name>.supervisor` to match disk values (**supervisor only**)
4. Removes config entries for Anima that no longer exist on disk (prune)

**What is synced:** supervisor only. speciality is not updated by org_sync.

**When it runs:**

- On server startup (after Anima processes are started by `animaworks start`)
- When an Anima is added via reconciliation (`on_anima_added` callback)

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

`_build_org_context()` in `core/prompt/builder.py` derives the following from directory scan and config.json merge:

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
2. **If supervisor changed:** Restart the server or wait for the next org_sync run (org_sync syncs supervisor to config.json)
3. **If speciality changed:** No server restart needed. It is read from status.json on each prompt build, so it takes effect on the next chat/heartbeat

Notes:
- Direct edits to `config.json` `animas.<name>.supervisor` are overwritten when org_sync runs (speciality is not overwritten)
- SHOULD notify affected Anima of org changes via message

## Example Org Patterns

Below are examples to set in each Anima's `status.json`. org_sync syncs `supervisor` to config.json. `speciality` is resolved on each prompt build from status.json / config.

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

`speciality` is free text in `status.json` under the `speciality` key. When unset, `role` (role name) is shown as a fallback.

- Shown next to each Anima's name in org context (e.g. `bob (Development lead)` or `bob (engineer)`)
- Helps other Anima decide who to consult or delegate to
- Unset shows as "(unset)"

**Behavior when creating Anima (`core/anima_factory.py`):**
- `animaworks anima create --from-md PATH [--role ROLE] [--supervisor NAME] [--name NAME]` writes `supervisor` and `role` to `status.json`
- **supervisor**: Uses `--supervisor` option if specified; otherwise parses from character sheet basic info table (`| 上司 | name |`)
- **speciality**: Not included in character sheet basic info table; `_create_status_json` does not write speciality, so it is not set automatically on creation
- For custom specialty display, add `"speciality": "Development lead"` etc. manually to `status.json` after creation
- Same for `create_from_template` / `create_blank`: speciality is not auto-set in status.json (if template includes status.json, its contents are copied)

Effective speciality guidelines:
- Concrete and short: `Backend development`, `Customer support`, `Data analysis`
- Avoid vague: `Various` → `Planning, coordination, progress management`
- Multiple areas: separate with middle dot: `UI design · Frontend development`
