# Reference — Technical Reference Index

Detailed technical specifications and admin configuration guides for AnimaWorks.
Not indexed by RAG. Use `read_memory_file(path="reference/...")` to read directly when needed.

## How to Access

```
read_memory_file(path="reference/00_index.md")          # This index
read_memory_file(path="reference/anatomy/anima-anatomy.md")  # Example
```

## Categories

### anatomy/ — File Structure & Architecture

| File | Content |
|------|---------|
| `anima-anatomy.md` | Complete guide to Anima configuration files (roles, change rules, encapsulation) |

### communication/ — External Integration Setup

| File | Content |
|------|---------|
| `slack-bot-token-guide.md` | Slack bot token configuration (per-Anima vs shared) |

### internals/ — Framework Internals

| File | Content |
|------|---------|
| `common-knowledge-access-paths.md` | 5 access paths for common_knowledge and RAG indexing mechanism |

### operations/ — Admin & Operations Setup

| File | Content |
|------|---------|
| `project-setup.md` | Project initial setup (`animaworks init`, directory structure) |
| `model-guide.md` | Model selection, execution modes, context window details |
| `mode-s-auth-guide.md` | Mode S authentication modes (API/Bedrock/Vertex/Max) |
| `voice-chat-guide.md` | Voice chat architecture, STT/TTS, installation |

### organization/ — Organization Structure Internals

| File | Content |
|------|---------|
| `structure.md` | Organization data sources, supervisor/speciality resolution |

### troubleshooting/ — Credential Setup

| File | Content |
|------|---------|
| `gmail-credential-setup.md` | Gmail Tool OAuth credential setup procedure |

## Related

- Everyday practical guides → `common_knowledge/00_index.md`
- Common skills → `common_skills/`
