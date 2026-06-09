# ABOUT.md — Will Austin

## Why this role

AgentCollect is the first job posting I've seen that lists "Claude Code" as a required skill — not as a nice-to-have, not buried in a tools section. That's a specific signal: you want someone who has restructured how they build software around agentic AI, not someone who uses it as autocomplete. I have 14 CLAUDE.md files across production platforms and Claude Code is my primary engineering environment. The collections domain is also a real problem I understand structurally — I've built outbound voice campaigns, BullMQ + Redis drip sequences, and HITL-gated AI execution for client-facing workflows. The hard part of what you're doing isn't the engineering. It's the compliance discipline and the "cannot fire incorrectly under a Fortune 500 brand" constraint. That's a system design problem I think about constantly.

## How I work with AI tools

**Tools:** Claude Code (primary), Cursor, Anthropic SDK directly for production endpoints.

**How I direct them:** I write a CLAUDE.md before I open the IDE on any new project — business rules, data model, routing decisions, integration surface, what the AI should never do autonomously. The model runs from that context, not from assumptions.

I trust the model on: boilerplate, repetitive transformation, test generation, first-draft implementations of well-scoped functions.

I override the model on: anything that touches live data without a confirmation gate, schema decisions, and any logic that has downstream effects I can't fully see. I don't let the AI decide what gets committed to production data — I review the action, then approve it.

The HITL pattern is not a distrust of the model. It's a recognition that the model doesn't know what it doesn't know about your specific system state. I build the confirmation layer to bridge that gap.

## Last project — structured

**One ambiguity I faced and how I resolved it:**
Building an outbound IVR campaign system for a roofing contractor. Initial ask: "build us a CRM." After embedding with the operation for a few days, the real problem was that every storm event required manually calling 400+ property addresses from appraisal district pull data. That's a voice campaign problem, not a CRM problem. I stopped building the CRM, scoped the voice system first, and built the CRM on top of the data it generated. The CRM had real data from day one because the outbound campaigns were already running.

**One tradeoff I made and why:**
Built the voice agent on Twilio IVR + ElevenLabs rather than a managed voice platform. Twilio gives full TwiML control: AMD on an async callback, a keypress menu (1 = connect live, 2 = schedule visit, 3 = DNC opt-out), and branching logic changeable in code. ElevenLabs gives a custom voice persona — the owner's approved voice, not a robot. Tradeoff: more to wire vs. the abstraction a managed platform provides. For a 1-operator business with a bespoke script and custom branching, full control was correct. At AgentCollect's call volume with FDCPA compliance requirements across 50 states, RetellAI for orchestration + ElevenLabs for persona is the right call — same architecture, right layer of abstraction.

**One mistake I made and what I changed:**
Shipped the IVR without a pause before the voice message. Calls connected, recording started immediately — humans picked up mid-sentence. Found it in call logs after 50 wasted dials. Fix was one line: `<Pause length="3"/>`. Should have called the number myself before the first batch ran. Integration tests don't cover the human experience of answering the phone. The lesson: always be the first user before anyone else is.

**One review comment that made me change my mind:**
Building the AI assistant in a separate platform (MAX EV Admin), I initially designed it as: natural language instruction → AI executes DB write directly. During a self-review with real data, I asked it to move a lead to "Proposal Sent." It moved the wrong lead — similar business name, confident match, already in the database. The note I wrote to myself: *"Any agent that writes to production without a human confirmation step is a liability, not a feature."* That rewired the entire action architecture. Every write became a confirmation card. Autonomous execution behind a HITL gate is a feature. Without it, it's a bug waiting to surface under a client's brand — which is exactly the risk you're managing.

## One thing I'd improve about this challenge / your CLAUDE.md

Your CLAUDE.md is clean and practical. One gap: there's no section on what Claude should and should not do autonomously within the codebase — what it can commit without review vs. what it should always surface for human approval. For an AI-native team with CI-integrated Claude review, that distinction matters and it's worth encoding explicitly. It's the same HITL discipline applied to the development workflow itself.
