# Notes

Pain Points:

1. What even is this? how do sheets connect, which columns matter
2. Can I trust it? -> Suspiscious data
3. Wrong shape or data format
4. Manual cleanup every momth
5. Can't explain or defend a number

Many fixes need business knowledge only the user has --> tool can't just blindly answer --> Confidence score (?)

Load every file into one standard internal format, and limit the AI to choosing from a small, fixed set of operations. 

Every company has its own DB. Can choose to separate into environments for different orgs.

A lot of it is READ only!

Build the system around trust.

## What I'm considering
- who is this for: smart non-technical people who got handed a spreadsheet and are stuck. not analysts
- the real pain isn't typos, it's not knowing if you can trust the number (olympics: naive USA golds = 2,638, real ≈ 1,131)
- people live in excel, so the grid stays front and center. they trust what they can see
- show ALL the warnings up front, then let the AI walk them through the questions one by one
- the tool finds the questions, the user answers them. a lot of fixes need business context only the user has (does blank discount = 0?)
- "where do I look" matters a lot when there are tons of fields → group columns by meaning (who / where / when / what)
- make data beautiful, not just correct. calm, clean, color only when it means something
- be honest when there's nothing interesting. don't make up insights (employee data looks generated)

## Trade-offs
- AI suggests, code changes the data. more upfront work (fixed set of ops) but it's predictable, repeatable, explainable, cheap
- AI only called ~2-3x per dataset, not for every click → less "magic" but fast and won't hallucinate numbers
- duckdb over pandas: SQL is easy to show the user ("here's what we did") + fast on 271k rows
- python backend vs all-in-browser: extra server to run, but keeps the API key safe + easier excel handling
- one grid + side panels instead of separate understand / fix / explore screens. simpler, less flashy
- fixed list of ~10 operations → can't handle every weird case, but every decision is replayable next month
- went deep on cleaning/trust, light on exploration. didn't want to build a mini tableau

## Not focusing on / future work
- multi-sheet data (bookshop): auto-detecting how sheets link, joining, stacking quarters
- re-applying saved decisions to next month's export
- edit a cell → turn it into a rule ("apply to all rows like this?")
- charts + "worth a look" relationship finder (correlations, trends, where data is missing)
- natural language questions
- collaboration, saving projects, sharing
- big files (millions of rows), auth, deployment
- messier layouts: header not in row 1, merged cells, totals rows mixed in

## How I used AI (process)
- brainstormed + made design calls with claude first, wrote everything into DESIGN.md before any code
- wrote an API contract (API.md) so 2 agents could build backend + frontend in parallel without drifting
- separate "blind" tester agent: only knew "Dataful helps non-technical people trust messy spreadsheets", no design doc, used the app through the browser like a real user
- I review the tester's findings and pick what to fix

## 🚩 Flags / talk about later
- 🚩 malicious data: a cell could contain instructions aimed at the AI (prompt injection). safe-ish bc AI can only pick from a fixed list of ops (schema-checked) AND nothing runs until the user clicks YES. talk about this in the video
- 🚩 privacy: AI sees column summaries + a few sample rows. maybe show that in the UI / let people turn AI off
- 🚩 tests: unit tests for detectors + ops (pytest). talk about later
- 🚩 video script: doing this myself
- 🚩 overfitting: detectors were tuned looking at the sample data. the shared-medal check only fires on olympics (checked all 21 demo datasets), and our CRM file is made up. idea is general (team prizes, co-authored papers, split commissions) but thresholds are guesses. it's a question not a fix, so a false alarm = 1 click. would validate on way more real files
- 🚩 medal ties: judo/boxing give 2 bronzes per event, so "same event + games + medal" merged rivals into one medal (18,293). fix = also key on the column that says whose side it is (NOC) → 18,905. picked by a general rule (same for teammates, different for every rival), not hard-coded. careful: Sex looked similar but splits mixed doubles teams
- 🚩 team spellings: "United States-1/-2" might be separate crews, not typos. bug fixed: target was picking "United States-10" over "United States"

## Decisions
- name: **Dataful**
- confidence = 3 levels (certain / likely / guess), not a fake % score
- grid toggles "original ↔ with my decisions"
- skipped questions stay unresolved. AI can only change data when the user clicks YES
- decisions saved as local .json files per dataset (survive restarts) + export. no accounts. "reset this dataset" if something goes wrong
- mixed currencies: not converting (exchange rates = a business decision). left as future work
- sonnet for the AI parts. bring your own anthropic key, app still works without one (just plainer wording)
- local only for now
- excel: each sheet = its own table. linking sheets together is future work
- 3 kinds of duplicates: copied rows, same person/company twice, double counting. all handled
- entity matching = code, not AI. work on distinct values not rows, fuzzy match in small blocks. AI only sees ~10 example groups → cost doesn't grow with row count
- wrong merges are worse than missed dupes (silently wrong numbers = the thing we're fighting). so: never auto-merge, show evidence for AND against, let user untick members, show impact before yes, "keep separate" gets remembered, everything undoable
- detectors are general "families" (dupes, junk placeholders, defaults posing as data, etc), not olympics-specific rules → avoid overfitting
- messy CRM deals export lives in dataset/extensions/ (made up by us, so it's a bonus demo, not proof. still test on the real datasets as-is)
- AI can add up to **20** new issues per review (was 5). more coverage, still every option re-checked by code + user clicks yes. cost: more tokens, busier margin
