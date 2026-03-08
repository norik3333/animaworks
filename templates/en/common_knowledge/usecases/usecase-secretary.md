# Use Case: Secretary & Administrative Support

This use case automates day-to-day administrative tasks such as schedule management, coordination, reminders, and information organization.

---

## Problems This Solves

- Falling behind on schedule management
- Forgetting meetings and deadlines
- Spending too much time on outreach and coordination
- Tedious daily and weekly report creation
- Losing track of progress across multiple projects

---

## Pattern 1: Schedule Management & Reminders

### What It Does
Monitors your calendar and handles reminders for upcoming events and availability management.

### How It Works
1. Each morning, fetches today's and tomorrow's schedule
2. Sends a "Today's Schedule Summary" to the human
3. Sends reminders before each event (e.g., 30 minutes prior)
4. Detects overlapping events and insufficient free time, then alerts

### Example Use Cases
- Every morning at 8:00: "You have 3 items today. 10:00: ○○ meeting, 14:00: ○○ interview, 16:00: ○○ deadline"
- 30 minutes before a meeting: "○○ meeting starts soon. Materials are here"
- "You have no free time tomorrow morning. Would you like to move the ○○ appointment?"

### Extensions
- When a new event is added to the calendar, prepare related materials in advance
- Before recurring meetings, organize and send the previous minutes and this meeting's agenda
- Suggest realistic schedules that account for travel time

---

## Pattern 2: Automated Coordination

### What It Does
Handles scheduling and communication with multiple stakeholders on your behalf.

### How It Works
1. Human instructs: "Set up a meeting with ○○ next week"
2. Extracts available slots from the human's calendar
3. Compiles candidate times and contacts stakeholders
4. Aggregates responses and proposes the best option
5. Registers the confirmed time in the calendar

### Example Use Cases
- "Schedule a meeting with the ○○ team sometime next week" → Proposes 3 options
- Email external partners: "We'd like to confirm the date for our next regular meeting"
- Automatically coordinate schedules for meetings with many participants, then notify everyone once decided

### Caveats
- For external outreach, sending after human confirmation is safer
- For important business meetings, request final human confirmation before sending

---

## Pattern 3: Automated Daily & Weekly Reports

### What It Does
Aggregates daily activity logs and outcomes, then generates standardized reports automatically.

### How It Works
1. At a specified time (e.g., 5:00 PM daily), collects that day's activity data
2. Summarizes sent/received messages, completed tasks, and notable events
3. Produces a report in a template format
4. Sends to the human for review (or posts automatically)

### Example Use Cases
- Auto-generate daily activity reports
- Create weekly project progress summaries
- Generate monthly activity statistics at month-end

### Sample Template
```
== Today's Activity Summary ==
■ Completed tasks: 5
  - Task A (done)
  - Task B (done)
  ...
■ Messages received: 12 (handled: 10, pending: 2)
■ Notable events: None
■ Tomorrow's schedule: 3 items
```

---

## Pattern 4: Information Gathering & Briefing

### What It Does
Collects essential information first thing in the morning and delivers it as a concise briefing.

### How It Works
1. At a specified morning time, gathers:
   - Summaries of unread messages
   - Today's schedule
   - Status of ongoing tasks
   - News or market data (if configured)
2. Organizes by priority
3. Sends as: "Good morning. Here's today's briefing"

### Example Use Cases
- "Two important messages arrived overnight"
- "Today's top priority is the ○○ deadline"
- "Yesterday's sales were ○○. Up 5% week-over-week"

---

## Pattern 5: Task Management & Progress Tracking

### What It Does
Centralizes task registration, progress tracking, and reminders.

### How It Works
1. Extracts and registers tasks from human instructions or messages
2. Sets reminders based on deadlines
3. Periodically checks progress and reports
4. Alerts on overdue tasks

### Example Use Cases
- "Get the estimate out by next Friday" → Task registered + reminder Friday morning
- "Check ○○ progress weekly" → Status check every Monday + report
- Reminders 3 days before, 1 day before, and on the deadline

---

## Pattern 6: Expense & Invoice Management Support

### What It Does
Helps organize invoices and expense reports, and sends reminders.

### How It Works
1. Detects invoices received via email or chat
2. Extracts amount, due date, and sender, then lists them
3. Sends reminders before each due date
4. Reports a list of unpaid invoices at month-end

### Example Use Cases
- "You have 3 unpaid invoices this month, totaling ○○"
- "○○ Corp's invoice is due in 3 days"
- Auto-generate monthly expense summaries

---

## Setup Tips

### Minimal Setup (1 Anima)
- One "secretary" Anima handles everything
- Basic set: schedule management + message monitoring + reminders
- Even this alone gives a sense of "someone always watching"

### Recommended Setup
- **Secretary Anima**: Schedule, coordination, reminders
- **Report Anima**: Auto-generate daily reports, weekly reports, progress reports
- Splitting roles between 2 Anima reduces load on the secretary

### Tips for Effective Use
- Starting with reminders alone can already provide significant value
- Automate first the things humans tend to forget
- For important communications, initially use: "draft → human review → send"
- Gradually expand automation as you get comfortable
