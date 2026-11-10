# Prompt Log

The major prompts I gave the AI (Claude Code, Opus 5.5) during this project, in order. Small follow-ups ("how do I run it", quick questions) are left out, and typos are fixed.

---

### 1 — Kickoff
*Pasted the full Golden Analytics Instructions*

> Act as my cofounder and talk through this with me. Before we build anything, let's spend some time brainstorming: who this is for, what problem we're actually solving, and what direction makes sense. Let me know if you need the links to the datasets.

-- Long conversation --

### 2 — Adding AI
> Could I integrate an AI agent into this?

### 3 — Back to the drawing board
> Let's go back to the drawing board and discuss what looks wrong with the data here specifically, but also what could be wrong with other data outside of this dataset (especially messy business data), then talk about pain points and focus on the user and then find a direction.

### 4 — Picking a direction
> I do like (1), but I wanna merge it with 3. Instead of answering with warnings, it provides ALL the warnings, and starts asking questions. So that users can see possible issues but also the AI can remind them of questions. But I also really like the idea of "I don't know where to look", especially when the data is messy or has a lot of different fields.

### 5 — One internal format
> I wonder if there's a way to convert every .csv or data to a native format that I can auto-manipulate, right? Or else I'd need an AI prompt for everything.

### 6 — Guiding users without AI
> Yes! But I do also want to talk about maybe some way to guide users in an ambiguous data environment, right? Like what relationships are interesting, general summaries. And then in terms of letting the user interact with the data without invoking AI, what are some ways to do this?

### 7 — Seeing the data itself
> No strong patterns, this data may be generated.
>
> Right, but how would the user or a business person want to interact with a data analytics platform if maybe they want to actually see the data itself?

### 8 — Make data beautiful
> Remember, I want to make data beautiful. Also please add to my Notes.md (in a concise and similar format to how I'm writing) things I'm considering as I'm designing, trade-offs, and areas I'm less focused on / lacking but can be worked on in the future.

### 9 — Visual direction
> Warmer and more editorial. I'm envisioning something similar to the Notes app (?)

### 10 — What did we miss?
> Is there anything you feel like you may have missed, and any design decisions that are still up for discussion?

### 11 — Design decisions
> 1. We can think about this later. I may do that myself.
> 2. Do you feel like you're overfitting to this case? What are some other more general data issues businesses and CRM data face?
> 3. Don't need to do that for now, but I will talk about the malicious part. (Put a flag on Notes.md.)
> 4. It should be easy to convert, right?
> 5. Put a note, we can talk about this later.
> 6. Yes, let's do that. They'd have to provide their own Anthropic key though.
>
> Decisions:
> 1. I like levels
> 2. Agreed
> 3. Leave unresolved. AI can only call tools when the user clicks a "YES" button
> 4. In memory
> 5. That's ok
> 6. Sonnet is good
> 7. Local for now
> 8. Dataful

### 12 — Duplicates
> Does our data app handle duplication and stuff? I agree with the messy CRM deals export (but keep it in like extensions).

### 13 — Cost at scale
> But like, if we have 270k rows, wouldn't that cost so many tokens for entity resolution?

### 14 — Wrong merges
> (quoting: "4. The AI sees at most about 10 examples...")
>
> But there could be special cases where it's actually different entities. What if you merge two separate things by accident?

### 15 — Building the MVP
> Yes! Let's do an MVP. Spin up multiple agents. For testing, use a separate agent with some context of what the app does, but don't give it your current design decisions. It should explore the app completely like a regular user would.

### 16 — Fixing the blind test findings
> Maybe we can store the decisions in local .json files first! Yes, fix everything except for 8.
*(8 = mixed currencies)*

### 17 — Code vs AI
> What are the current deterministic checks before AI? And does the AI check for as many possible weird things or just a few?

### 18 — One issue, not two
> Yeah, but what if it's like this: M, m, MALE, male. Is there a way to let Claude understand that these are actually ONE single issue, not two separate ones?

### 19 — Iterative review + chat
> Yes, I agree.
>
> And honestly I feel that the "review" process could be iterative too!
>
> Maybe I could have an NLP chat section to raise some issues I see with my eyes to Claude, and Claude can retrieve relevant data.
>
> And maybe after I click certain fixes like merge M to m, and male to MALE, I can re-ask the AI to check, and now it would actually see that M and MALE should be merged again!
>
> Also I'm thinking that sending 50 rows at random might be a good call instead of 10?

### 20 — Counting what matters
> (quoting README: "Olympics data shows this well. If you count the \"USA, Gold\" rows you get **2,638**...")
>
> But how would I even count it in my current app? There's no feature that does that.

### 21 — Overfitting check
> Do you think this is overfitting?
*(about the "shared medals" detector)*

### 22 — General fix + demo script
> Yes, do that. And also help me add to the script so I can explain how I built something while going through it.
