# Use Case: Infrastructure & Service Monitoring

This use case automates 24/7 monitoring of servers, web services, cloud resources, and more—covering anomaly detection, alerting, and initial incident response.

---

## Problems This Solves

- Delayed awareness of server outages
- No coverage for incidents during nights and holidays
- Overlooking SSL certificate expiration
- Missing disk space and resource exhaustion until it’s critical
- Too many alerts from monitoring tools, causing important ones to be missed

---

## Pattern 1: Web Service Health Checks

### What It Does
Periodically checks whether web services respond correctly and sends alerts when anomalies are detected.

### How It Works
1. Access target URLs at regular intervals (e.g., every 5–30 minutes)
2. Verify HTTP response codes and response times
3. When an anomaly is detected:
   - First occurrence: Re-check (may be a transient error)
   - Second consecutive failure: Notify humans
   - When recovery is detected: Send a recovery notification
4. Record response time trends and detect degradation

### Example Scenarios
- Production website returns 503 → Immediate notification to the admin’s phone
- API response time triples → Performance degradation warning
- Post-maintenance recovery check → Automatically confirm and report that the service is back to normal

### What You Need to Get Started
- List of URLs to monitor
- Alert destinations (chat, email, etc.)
- Thresholds (e.g., response time above which to treat as delayed)

---

## Pattern 2: Server Resource Monitoring

### What It Does
Monitors server resources such as CPU, memory, disk space, and process status.

### How It Works
1. Periodically fetch server state (via SSH or API)
2. Compare each metric against thresholds:
   - Disk usage > 80% → Warning
   - Disk usage > 95% → Urgent notification
   - Sudden spike in memory usage → Possible memory leak
   - Sustained high CPU load → Check for runaway processes
3. On anomaly: Send alert plus recommended actions

### Example Scenarios
- Disk space down to 5% → Suggest candidates for old log deletion
- A process stuck at 100% CPU → Report process name and start time
- Memory usage increasing day by day → Warn about possible leak

### Example Automated Actions
- Log rotation (compress and delete old log files)
- Identify and report runaway processes (auto-kill only after human approval)
- Clean up temporary files

---

## Pattern 3: SSL/TLS Certificate Expiration Monitoring

### What It Does
Periodically checks SSL certificate validity and prompts renewal before expiration.

### How It Works
1. Check certificate expiration for target domains once daily
2. Adjust alert level by days remaining:
   - 30 days left → Informational (recommend preparing for renewal)
   - 14 days left → Warning (renew soon)
   - 7 days left → Urgent (immediate action required)
3. Send reminders with renewal procedure details

### Example Scenarios
- Manage certificate expiration for multiple domains in one place
- Verify that automatic renewal (e.g., Let’s Encrypt) is working correctly
- Confirm that renewed certificates are applied correctly

---

## Pattern 4: Cloud Service Monitoring

### What It Does
Monitors the status and cost of cloud resources (containers, databases, storage, etc.).

### How It Works
1. Periodically fetch resource state via cloud APIs
2. Monitor:
   - Service health (normal/abnormal)
   - Error log occurrence
   - Cost trends (budget overrun detection)
3. Notify when anomalies or budget overruns are detected

### Example Scenarios
- Container service task count drops → Possible service outage
- Database connections near limit → Suggest scaling up
- Monthly cloud cost exceeds 80% of budget → Cost warning

---

## Pattern 5: Log Analysis and Anomaly Detection

### What It Does
Periodically analyzes application logs to detect error patterns and abnormal trends.

### How It Works
1. Fetch logs for the specified period
2. Count error and warning occurrences
3. Compare with baseline to detect anomalies:
   - Error rate 3× normal → Investigation alert
   - New error type appears → Possible new failure
   - Errors concentrated on a specific endpoint → Possible failure in that feature
4. Report analysis results as a summary

### Example Scenarios
- “0 errors in the last 30 minutes, all normal” → Routine report
- “3 new error patterns detected” → Report with details
- “Error rate for a specific API spiking” → Start root cause investigation

---

## Pattern 6: Integrated Dashboard-Style Operation

### What It Does
Aggregates multiple monitoring results and generates periodic summary reports.

### How It Works
1. Collect reports from each monitoring role
2. Summarize overall status at a glance
3. Report to humans on a schedule (e.g., every morning at 9)

### Sample Report
```
== Today's Infrastructure Status ==
[OK] Web services: Responding normally (avg 120ms)
[OK] Server resources: CPU 15%, Memory 45%, Disk 62%
[CAUTION] SSL certificate: example.com expires in 20 days
[OK] Cloud services: All tasks running
[OK] Error logs: 0 errors in the last 24 hours
```

---

## Configuration Tips

### Minimal Setup (1 Anima)
- One Anima handles all monitoring in rotation
- Rotation interval around 30 minutes
- Sufficient for small environments (1–2 servers)

### Recommended Setup (3–4 Anima)
- **Monitoring coordinator**: Overall status, anomaly judgment, escalation
- **Server monitoring**: OS, processes, resource monitoring
- **Network/SSL monitoring**: SSL certificates, DNS, connectivity
- **Cloud monitoring**: Cloud-specific monitoring

### Reducing False Positives
- Don’t alert on a single anomaly (confirm with two consecutive failures)
- Set thresholds based on baseline values from your actual environment
- Have the coordinator independently verify reports from monitoring Anima
- Accumulate false-positive patterns as knowledge to improve judgment accuracy
