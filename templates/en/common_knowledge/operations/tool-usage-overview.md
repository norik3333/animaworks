# Tool Usage Overview

Reference for AnimaWorks tool system and usage by execution mode.
Use this to understand the tools you can use and how to call them correctly.

## Execution Mode and Tools

How you call tools and what is available depends on your execution mode.
Your mode is determined automatically from your model name in `status.json`.

| Mode | Target Models | How tools are called |
|------|---------------|----------------------|
| S (SDK) | `claude-*` | MCP tools (`mcp__aw__*`) + Claude Code built-ins + external tools via Bash |
| A (Autonomous) | `openai/*`, `google/*`, `vertex_ai/*`, etc. | LiteLLM function calling (tool name as-is) |
| B (Basic) | Small models like `ollama/*` | JSON text format (`{"tool": "name", "arguments": {...}}`) |

### S-mode (Claude Agent SDK)

Three tool families:

1. **Claude Code built-ins**: Read, Write, Edit, Grep, Glob, Bash, git, etc. For file operations and command execution
2. **MCP tools (`mcp__aw__*`)**: AnimaWorks-specific internal features. External tools permitted in `permissions.md` are also available directly via MCP
   - Internal: `send_message`, `post_channel`, `read_channel`, `read_dm_history`, `add_task`, `update_task`, `list_tasks`, `call_human`, `search_memory`, `report_procedure_outcome`, `report_knowledge_outcome`, `skill`, `disable_subordinate`, `enable_subordinate`
   - External (when permitted): `mcp__aw__slack_post`, `mcp__aw__chatwork_send`, etc.
3. **Bash + animaworks-tool**: Long-running tools (image generation, local LLM, speech transcription, etc.) are executed asynchronously via `animaworks-tool submit`

### A-mode (LiteLLM)

Two tool families:

1. **Internal tools**: `send_message`, `search_memory`, `read_file`, `execute_command`, `add_task`, `discover_tools`, etc. Call by name using function calling
2. **External tools**: When you enable a category with `discover_tools(category="...")`, those tools are dynamically added

### B-mode (Basic)

Tools are invoked in JSON text format. Available tools:

- **Memory**: search_memory, read_memory_file, write_memory_file, archive_memory_file
- **Communication**: send_message, post_channel, read_channel, read_dm_history
- **File & search**: read_file, write_file, edit_file, execute_command, web_fetch, search_code, list_directory
- **Skill**: skill, create_skill
- **Outcome tracking**: report_procedure_outcome, report_knowledge_outcome
- **Notification**: call_human (when notification channels are configured)
- **External tools**: Tools in categories permitted in permissions.md (when permitted)

Task management, supervisor tools, discover_tools, refresh_tools, share_tool, and create_anima are not available.

---

## Tool Categories

### Internal Tools (Always Available)

AnimaWorks internal features available in all modes (some may be omitted depending on mode).

| Category | Tool | Description |
|----------|------|-------------|
| Memory | `search_memory` | Keyword search over long-term memory |
| Memory | `read_memory_file` | Read a memory file |
| Memory | `write_memory_file` | Write to a memory file |
| Memory | `archive_memory_file` | Move unused memory files to archive/ |
| Communication | `send_message` | Send DM (intent required: report / delegation / question) |
| Communication | `post_channel` | Post to Board channel |
| Communication | `read_channel` | Read Board channel |
| Communication | `read_dm_history` | Read DM history |
| Skill | `skill` | Fetch full text of skill/procedure |
| Skill | `create_skill` | Create skill in directory structure (A/B-mode) |
| Outcome tracking | `report_procedure_outcome` | Report procedure execution result |
| Outcome tracking | `report_knowledge_outcome` | Report usefulness of knowledge |
| Notification | `call_human` | Notify human admin |
| Permission check | `check_permissions` | View your permission list (A/B-mode) |

In S-mode, the tools exposed via MCP have the `mcp__aw__` prefix.

### File & Search Tools (A/B-mode)

| Tool | Description |
|------|-------------|
| `read_file` | Read file with line numbers |
| `write_file` | Write to file |
| `edit_file` | Replace text within file |
| `execute_command` | Execute shell command (subject to allowlist in permissions.md) |
| `web_fetch` | Fetch content from URL |
| `search_code` | Search files with regex |
| `list_directory` | List directory with glob filter |

In S-mode, use Claude Code's Read / Write / Edit / Grep / Glob / Bash for equivalent operations.

### Task Management Tools (A/S-mode only)

| Tool | Description |
|------|-------------|
| `add_task` | Add task to task queue |
| `update_task` | Update task status |
| `list_tasks` | List tasks |

### Tool Management Tools (A-mode only)

| Tool | Description |
|------|-------------|
| `discover_tools` | List and enable external tool categories |
| `refresh_tools` | Rescan personal and common tools |
| `share_tool` | Share personal tool to common_tools/ |

### Supervisor Tools (Anima with subordinates only)

Organizational tools automatically enabled for Anima with subordinates. See `organization/hierarchy-rules.md` for details.

| Tool | Description | S-mode MCP |
|------|-------------|------------|
| `org_dashboard` | Show process status of all subordinates in a tree | × |
| `ping_subordinate` | Check subordinate liveness | × |
| `read_subordinate_state` | Read subordinate current task | × |
| `delegate_task` | Delegate task to subordinate | × |
| `task_tracker` | Track delegated task progress | × |
| `disable_subordinate` | Disable subordinate | ○ |
| `enable_subordinate` | Re-enable subordinate | ○ |
| `set_subordinate_model` | Change subordinate model | × |
| `restart_subordinate` | Restart subordinate process | × |

In S-mode, only `disable_subordinate` and `enable_subordinate` are available via MCP. Others are A-mode only.

### Admin Tools (Conditional)

| Tool | Description | Condition |
|------|-------------|-----------|
| `create_anima` | Create new Anima from character sheet | When holding skills/newstaff.md (A-mode) |

### External Tools (Permission and enablement required)

Tools for external services. Only categories permitted in the "External tools" section of `permissions.md` are available.

Main categories: `slack`, `chatwork`, `gmail`, `github`, `aws_collector`, `web_search`, `x_search`, `image_gen`, `local_llm`, `transcribe`

---

## Using External Tools

### S-mode

1. **Check categories**: Confirm permitted categories in `permissions.md`
2. **Execute**: Permitted external tools can be called directly via MCP (e.g. `mcp__aw__slack_post`)
3. **Long-running tools**: Execute asynchronously with `animaworks-tool submit <tool_name> <subcommand> [args...]`
4. **Help**: `animaworks-tool <tool_name> --help` for subcommands and arguments

Long-running tools (image generation, local LLM, speech transcription, etc.) must always be executed with `submit`. See `operations/background-tasks.md` for details.

### A-mode

1. **Check categories**: Call `discover_tools()` with no arguments
2. **Enable**: `discover_tools(category="slack")` to enable a category
3. **Execute**: Enabled tools become callable via normal function calling
4. **Long-running tools**: Automatically run in background (equivalent to `submit`)

### B-mode

1. **Check permissions**: Use `check_permissions` to see permitted categories
2. **Execute**: Permitted external tools can be called in JSON text format
3. **Long-running tools**: Ask your supervisor (A/S-mode) or call them the same way if permitted

---

## Common Questions

### common_knowledge examples use a different mode than mine

Documents use A/B-mode style like `send_message(to="...", content="...", intent="...")`.
If you are in S-mode, add the `mcp__aw__` prefix when reading (e.g. `mcp__aw__send_message`).

### How to see what tools I have

- **A/B-mode**: Use `check_permissions` to see your permissions
- **S-mode**: Tools exposed via MCP have the `mcp__aw__` prefix. Read `permissions.md` for permission details
- **A-mode**: `discover_tools()` for external tool categories
- **All modes**: `read_memory_file(path="permissions.md")` to check permitted content (S-mode: read directly with Claude Code's Read)

### Tool returns an error

→ See "Tools don't work" in `troubleshooting/common-issues.md`
