# AnimaWorks Use Case Guide

A theme-based guide to what you can do with AnimaWorks. It is structured to help first-time users imagine how the framework can support their day-to-day work.

---

## What is AnimaWorks?

AnimaWorks is a framework that organizes AI agents (Anima) as "employees" and runs them 24/7, 365 days a year.

While humans sleep, Anima can:

- Monitor messages and respond when needed
- Detect and report server or service issues
- Generate regular reports
- Run code reviews and tests

They handle these tasks autonomously.

---

## Anima Characteristics

### 1. Memory

Anima have short-term and long-term memory. They accumulate past responses, lessons learned, and established procedures, so quality improves over time. Experience like "last time we solved this problem this way" builds up across the organization.

### 2. Roles

Each Anima is assigned a specific role. Secretary, engineer, monitoring, customer support, and so on. By giving them clear responsibilities, you can build a division of labor similar to a human team.

### 3. Collaboration as an Organization

Anima exchange messages and delegate tasks to each other. A coordinator can oversee the whole, while specialists handle execution, enabling hierarchical organization.

### 4. Scheduled Autonomous Actions

You can configure scheduled runs such as "create a report every morning at 9" or "check messages every 30 minutes." They keep running these routines without human intervention.

### 5. Integration with External Services

Anima can connect to chat tools, email, calendars, cloud services, social media, and more. Any service with a public API can be operated directly by Anima.

---

## Use Case Index

The following theme-based guides describe concrete usage patterns.

| Guide | Theme | Best for |
|-------|-------|----------|
| [Communication Automation](usecase-communication.md) | Automating chat and email handling | People with many external contacts and concerns about missed messages |
| [Software Development Support](usecase-development.md) | Code review, PR management, bug investigation | Development teams and solo developers |
| [Infrastructure & Service Monitoring](usecase-monitoring.md) | 24/7 monitoring, alerts, incident response | People running servers or web services |
| [Secretary & Admin Support](usecase-secretary.md) | Schedule management, coordination, reminders | Busy people who lack time for admin tasks |
| [Research & Investigation](usecase-research.md) | Web research, market analysis, report creation | People who regularly gather and analyze information |
| [Knowledge Management](usecase-knowledge.md) | Procedures, FAQ, structuring information | People who want to systematize team knowledge |
| [Customer Support](usecase-customer-support.md) | Handling inquiries, escalation | People with customer-facing responsibilities |

---

## Getting Started

You don't need to do everything at once. Starting with one or two Anima and scaling up as you get comfortable is recommended.

### Small Start Examples

**Pattern 1: Start with one**
- Deploy a single secretary Anima
- Assign only message monitoring and reminders
- Expand responsibilities gradually as you get used to it

**Pattern 2: Two Anima with divided roles**
- Secretary Anima (communications, schedule management)
- Monitoring Anima (server and service health checks)
- These two alone can provide 24/7 coverage

**Pattern 3: Team setup**
- Coordinator Anima (overall coordination and decisions)
- Several worker Anima (development, monitoring, secretary, etc.)
- Humans interact only with the coordinator; the coordinator delegates to the workers

---

## Important Notes

### When Human Judgment Is Required

Anima act autonomously but should escalate to humans in these situations:

- Decisions involving money
- Important external communications (contracts, negotiations, etc.)
- Irreversible actions (data deletion, production deploys, etc.)
- New situations where the decision criteria are unclear

### Cost Awareness

Each Anima uses LLM (large language model) APIs, so costs scale with usage. It's important to run them only where and as often as needed.

### Security

- Define clear rules for handling confidential information
- Manage external service credentials centrally
- Grant Anima minimal permissions (only the tools they need)
