# Use Case: Software Development Support

This use case covers automating and supporting software development workflows such as code review, PR management, test execution, and bug investigation.

---

## Problems This Addresses

- PRs pile up and reviews fall behind
- CI failures go unnoticed for too long
- Delays between bug reports and the start of investigation
- Tests are often forgotten
- Code quality standards depend on individual knowledge

---

## Pattern 1: Automated Code Review

### What It Does
When a PR is created, the system automatically reads the code and comments on issues and improvement suggestions.

### Flow
1. Detect new PR creation (via Webhook or periodic check)
2. Fetch and analyze the diff
3. Review from these angles:
   - Security issues (SQL injection, hardcoded secrets, etc.)
   - Performance concerns
   - Consistency with existing code
   - Test coverage and presence
4. Post review results as comments on the PR

### Example Use Cases
- Run basic quality checks on PRs from junior engineers
- Automatically apply security checklists
- Verify code against coding standards

### Key Points
- The goal is to **assist** human reviewers, not replace them
- Automated review catches obvious issues so humans can focus on design decisions
- Review criteria can be customized (stricter or more lenient)

---

## Pattern 2: CI/CD Result Monitoring and Response

### What It Does
Monitors CI (continuous integration) execution results and, when failures occur, performs root cause analysis and suggests fixes.

### Flow
1. Detect CI run completion
2. If the result is failure:
   - Fetch and analyze error logs
   - Identify the cause (test failure, build error, environment issue, etc.)
   - Propose a fix
   - Notify the assignee
3. If the result is success:
   - Confirm merge criteria
   - If all conditions are met, request human approval

### Example Use Cases
- On test failure: “These 3 files changed. Here’s the suggested fix.”
- Detect environment-dependent failures (flaky tests) and trigger automatic retries
- On CI success: “Ready to merge. Here’s the change summary.”

---

## Pattern 3: From Issue Creation to Implementation

### What It Does
Automates the flow from bug reports and feature requests through issue creation, branch creation, implementation, and PR creation.

### Flow
1. Create an issue based on human instructions (requirements definition)
2. Create a work branch automatically
3. Implement code according to the instructions
4. Run tests and verify behavior
5. Create a PR and request review

### Example Use Cases
- “Add validation to the login screen” → Issue creation → implementation → PR creation, all automated
- “Investigate and fix this bug” → Root cause analysis → fix → tests → PR creation

### Caveats
- Automated merge is not recommended (human final review is required)
- Consult humans before large design changes
- Always verify implementation with tests

---

## Pattern 4: Bug Investigation and Root Cause Analysis

### What It Does
When a bug is reported, analyzes logs and code, identifies the cause, and proposes a fix strategy.

### Flow
1. Analyze the bug report (reproduction steps, impact)
2. Search and analyze relevant code
3. Investigate logs and error traces
4. Form hypotheses about the root cause
5. Report the fix strategy and impact scope

### Example Use Cases
- “Feature X doesn’t work in production” → Analyze logs and report cause and fix strategy
- “Performance has degraded recently” → Analyze recent commits and identify likely causes
- “Tests are unstable” → Analyze flaky test patterns and suggest stabilization approaches

---

## Pattern 5: Automated Documentation

### What It Does
Generates changelogs and release notes from code changes.

### Flow
1. Fetch commit history for the specified period
2. Categorize changes (new features, bug fixes, improvements, etc.)
3. Generate user-facing descriptions
4. Produce documentation in the required format

### Example Use Cases
- Generate changelog automatically before releases
- Create monthly development progress reports automatically
- Generate documentation summarizing API change impact

---

## Configuration Tips

### Minimal Setup (1 Anima)
- One Anima handles PR monitoring, review, and CI checks
- Sufficient for small projects (around 10 PRs per month)

### Recommended Setup (3–5 Anima)
- **Development lead**: Overall progress management, task assignment
- **Implementation**: Issue handling, code implementation
- **Review**: Code review, quality checks
- **Testing**: Test execution, CI monitoring
- The lead receives tasks and assigns them to the appropriate team members

### Quality Practices
- Always run automated implementation through review (Anima review is acceptable)
- Verify test changes (avoid “tests rewritten to pass” scenarios)
- Disallow direct commits to main; require all merges via PR
