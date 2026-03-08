# Use Case: Research, Investigation & Analysis

This use case automates information gathering and analysis—including web search, market research, competitive analysis, and report creation.

---

## Problems This Addresses

- Information gathering takes too much time
- You want to monitor competitors regularly but lack the bandwidth
- Compiling collected information into reports is tedious
- You want to track mentions of your company on SNS
- You want to automate regular collection and analysis of market data

---

## Pattern 1: Information Gathering via Web Search

### What It Does
Performs web searches on specified topics and reports findings in a summarized, organized format.

### Flow
1. Receive a research topic from the user
2. Search for information using multiple queries
3. Organize and summarize the collected information
4. Report with citations included

### Examples
- "Research the latest trends in the ○○ industry" → Summarize key articles and report
- "Look into ○○ technology" → Summarize overview, pros/cons, and adoption examples
- "Research ○○ company" → Organize company overview, recent news, and reputation

### Key Points
- Always include source URLs
- Mark unverified information as "unverified"
- Cross-check multiple sources to ensure reliability

---

## Pattern 2: Regular Competitive & Market Monitoring

### What It Does
Periodically checks competitors and market trends, and reports when changes are detected.

### Flow
1. Run on a schedule (e.g., every Monday)
2. Gather information on predefined targets:
   - Competitors’ new services and press releases
   - Industry news
   - Relevant regulatory or legal changes
3. Extract changes compared to the previous run
4. Report a summary when changes are found

### Examples
- "Competitor A released a new feature. Summary: ○○"
- "A new regulatory proposal was announced in the ○○ industry"
- "A new market research report was published that can be used for market share estimates"

---

## Pattern 3: SNS & Media Monitoring

### What It Does
Periodically searches SNS and news sites for mentions of your company or products, and tracks sentiment.

### Flow
1. Regularly search SNS and news sites
2. Collect mentions of your company name, product names, and related keywords
3. Classify as positive, negative, or neutral
4. Report notable posts and trends

### Examples
- "15 mentions of our company this week: 10 positive, 2 negative, 3 neutral"
- "An influential user posted a favorable review of our product"
- "Negative reviews are increasing. Main complaints: ○○"

### Notes
- Report SNS posts with full context (avoid cherry-picking excerpts)
- Report immediately to human users when high-risk posts are detected

---

## Pattern 4: Data Collection & Automated Reports

### What It Does
Regularly collects public or market data and generates analytical reports.

### Flow
1. Fetch data from sources on a schedule
2. Analyze changes over time
3. Detect anomalies and trend shifts
4. Generate reports with charts and tables

### Examples
- Daily reports on exchange rates, stock prices, or crypto prices
- Weekly analysis of your service usage statistics
- Estimating market activity from industry job posting trends

---

## Pattern 5: Deep-Dive Research & Due Diligence

### What It Does
Conducts thorough, multi-angle research on specific companies, individuals, or technologies.

### Flow
1. Confirm the research target and objectives
2. Gather information from web search, public databases, news archives, etc.
3. Organize and classify information:
   - Basic info (founding year, location, business, etc.)
   - Financial info (if publicly available)
   - Reputation and reviews
   - Risk information
4. Report as a structured document

### Examples
- Company research for M&A targets
- Credit research on new business partners (based on public information)
- Feasibility assessment for adopting new technology (pros, cons, cost, case studies)

---

## Pattern 6: Regular Regulatory & Compliance Checks

### What It Does
Periodically checks for changes in regulations relevant to your business.

### Flow
1. Search for relevant regulations on a schedule (e.g., weekly)
2. Detect new or amended laws, regulations, or guidelines
3. Assess impact on your company
4. Report details when impact is significant

### Examples
- "A revision to the Personal Information Protection Act was proposed. Impact on our services: ○○"
- "A new guideline was issued by the industry association"
- "Related regulations were strengthened in ○○ country. Impact level: medium"

---

## Deployment Tips

### Minimal Setup (1 Anima)
- One Anima handles research requests and execution
- Ad-hoc operation based on user requests
- Can also handle regular monitoring

### Recommended Setup (2–3 Anima)
- **Research specialist**: Executes research requests and deep-dive investigations
- **Monitoring specialist**: Regular monitoring of market, SNS, and regulations
- **Analysis specialist**: Analyzes collected data and generates reports

### Tips for Higher Quality Research
- Always evaluate source reliability
- Cross-check with multiple sources
- Clearly separate "verified facts" from "assumptions"
- Mark dates on older information
- Store findings as knowledge for reuse in future research
