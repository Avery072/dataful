# Dataful

Dataful helps people in businesses to make sense of a messy spreadsheet someone handed them (maybe it's a CRM service, maybe it's the company's internal data tool, maybe it's a dataset they're doing research on). The real goal is to help users see if they can really trust the data.

Drop in a CSV / excel file and it loads it in tableau style [more formats coming soon!!]. Dataful lists things that look off right off the bat: duplicate rows; "NA" pretending to be data; 'Gender' column written in eight different ways (M,m,MALE,Male,...); a Olympic medal counted once per teammate instead of event + country. You can also easily undo or turn off any decisions / changes made, and export the new, modified data as a csv to plug in else where (hopefully an in-house data analytics tools).

## Instructions

You need Python 3.12+ with [uv](https://docs.astral.sh/uv/), and Node 20+.

```bash
# 1. (optional) AI features: put your key in a .env at the repo root
echo "ANTHROPIC_API_KEY=sk-ant-..." > .env

# 2. backend  → http://localhost:8000
cd backend && uv sync && uv run uvicorn app.main:app --port 8000

# 3. frontend → http://localhost:5173 (sends /api requests to the backend)
cd frontend && npm install && npm run dev
```

Open http://localhost:5173. The demo datasets load automatically, or you can upload your own `.csv`, `.tsv` or `.xlsx`.

**Without an API key, the basics still work.** The key only adds "Ask Dataful to review", which gives friendlier wording, an overview of the dataset, and extra issues the rules missed.

## Data

- **Mine:** `dataset/extensions/crm_deals.csv`, a synthetic messy CRM export. Real business data has problems the provided sets don't: the same deal repeated once per contact, mixed currencies, "Closed Won" with $0, test records. Recreate it with `backend/scripts/make_crm_deals.py`. 

---

## Why I built this

I tried to put myself in the user's shoes. Now, as a student and researcher, I would LOVE a tool that could help me identify subtle relationships within my data, or turn a messy table into easy-to-understand summaries. But, I also understand that Golden Analytics works with other businesses. So I put myself in the shoes of someone who works in a business but may not necessarily be data-savvy. The nicely formatted data still sounds amazing, but a lot of real-world data is incredibly messy -- sometimes just WRONG. So I wanted to focus on building a tool that helps you trust your data.

For example, in the Olympics data, if you count the "USA, Gold" rows, you get 2,638. But a basketball gold gives every play on the team a medal on their rows, so the real count is actually 1131. The data itself isn't wrong, but its semantics and how traditional data manipulation methods interpret it are.

Without data cleaning, I felt like a lot of the other grander features (which are equally as important) like NLP + data analysis / linking multiple data sources wouldn't sell well -- since the core data itself would still be 'unreliable'. 

So I built this tool, sort of as the plumbing for data, made for noobs. It is intended to be used together with data analysis tools!

Some decisions:
**The grid/table stays front and centre.** People trust what they can see. A summary of relationships would be really nice, but people need to see data tangibly to trust it (especially if they're making multi-million dollar decisions based on it). So, my main interface is a grid with notes beside it. 

**Show every problem, then ask.** A lot of fixes require knowledge only the user has. Does a blank discount mean 0? Are "Acme Inc" and "ACME" the same customer? So the tool finds the questions and the user answers them, through buttons. For more complex issues or maybe issues the user spots manually, we use the 'Chat' interface.

**Only the code changes the data, never the AI** Every fix is one of a small, fixed set of operations (e.g. merge these spellings, treat ... as blank, etc.). I know you might be thinking, but what if we didn't predict the issue with the data? It turns out that a lot of issues with data are actually very repetitive e.g. duplicate rows, etc. and if we're working with enterprises, we typically have a sense of what the most common issues with their data look like. [I do have an idea to overcome this though, in next steps]. Claude can *suggest* operations, but each suggestion is checked against the real data and only runs when the user clicks Yes. 

**A wrong merge is worse than a missed duplicate.** Quietly wrong numbers are exactly the problem I'm fighting. So nothing merges automatically: every note shows evidence for *and* against, a preview of the impact, and "keep separate" is remembered.

**Honest confidence.** Three levels, *certain / likely / guess*, instead of a made-up 87% the AI might spit out.

**Make it pleasant.** Warm paper background, serif headings, amber only where something needs attention. This is really inspired by Apple Notes. Cleaning data is tedious, so the tool shouldn't feel like another white dashboard with RGB histogram bars.

I chose to go deep on trust and less on exploration. There's group-by with warnings ("these rows share one medal, count it once?"), but I didn't want to build a mini Tableau in 45 minutes that is a jack of all trades but master of none.

## How I used AI

I built this with Claude Code (Opus 5.5). Major prompts I gave it are in [`PROMPTS.md`].

Some principles I followed:
1. **Conversate first**. I spent the first stretch just talking it through as if Claude was my cofounder. What's wrong with these data sets? What goes wrong in real business data generally? Who's in pain and why? I pushed back when it was overfitting on Olympics data. And I made sure that Claude and I had the same mental model, or **vision** of the product before even starting the design.

2. **I made the calls.** I told Claude to lay out major design options and always made sure I had the final say.

3. **Parallel agents with an agreed API.** I had Claude write an API contract [`API.md`]first, then two agents built the backend and frontend at the same time against it.

4. **A blind tester** I used a separate agent that acted like a non-technical person navigating the app and run tests with no design docs.  It found a crash and some trust problems the builders had missed (e.g. counts that disagreed between places). I triaged its findings and decided what to fix.

Really just making sure I'm being as efficient as possible while never off-loading my brain to AI. And making sure me and Claude are always on the same page, because it's always easier (and cheaper in tokens) to fix something before any code is ever written.

## With more time

- **Multisheet data**. Be able to identify links between tables, join them, and stack sheets together.
- **Present data in another form**. Maybe a marketing person wants data insight to make decisions. I would make an interface that helps them check relationships within the data using natural language.
- **Edit a cell → make it a rule.** "You changed 'NY' to 'New York'. Apply that to all 412 rows like it?"
- **"Worth a look."** Honest relationship-finding (trends, correlations, where data is missing), including saying "nothing interesting here".
- **Production scale**
- **An agent that can modify its own harness** I can have a virtual environment and perhaps a multi-agent harness where one agent may propose an issue in data that we can't handle with our current preset tools, and another agent could actually modify the harness and create a new tool to adapt to new issues and scenarios [ideally approved by a Golden Analytics staff member]

Overall, this was very fun!
