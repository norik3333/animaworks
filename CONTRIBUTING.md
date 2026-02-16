# Contributing to AnimaWorks

Thank you for your interest in contributing to AnimaWorks.

## Contributor License Agreement (CLA)

Before your first pull request can be merged, you must sign the project's
Contributor License Agreement.

### Why a CLA?

AnimaWorks is licensed under **AGPL-3.0-or-later** for the entire codebase.

The CLA allows the project maintainers to offer commercial licenses to
organizations that cannot use AGPL-licensed software. Without a CLA,
third-party contributions would prevent this, making the project
unsustainable.

### How to sign

1. Read [CLA.md](CLA.md) carefully.
2. Add your entry to the signature table at the bottom of `CLA.md`.
3. Include the CLA signature commit in your first pull request.

## Development Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e ".[all-tools,test]"
```

## Code Style

- `from __future__ import annotations` at the top of every file
- Type hints required (`str | None` style)
- Google-style docstrings
- `logger = logging.getLogger(__name__)`
- Semantic commits: `feat:`, `fix:`, `refactor:`, `docs:`, `test:`

## License Headers

All source files must include the AGPL header:

```python
# AnimaWorks - Digital Anima Framework
# Copyright (C) 2026 AnimaWorks Authors
# SPDX-License-Identifier: AGPL-3.0-or-later
```

## Pull Request Process

1. Ensure your CLA signature is on file.
2. Create a feature branch from `main`.
3. Add tests for new functionality.
4. Run `pytest` and ensure all tests pass.
5. Submit a pull request with a clear description.
