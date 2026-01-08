---
name: interview
description: Interview about a plan file to surface hidden assumptions, edge cases, and decisions before implementation. Use when you need to deeply discuss and refine a design plan.
argument-hint: <plan-file.md>
context: fork
allowed-tools: Read, Edit, Glob, Grep, AskUserQuestion
---

# Interview Skill

Read the plan file at $ARGUMENTS and conduct an exhaustive interview using the AskUserQuestion tool.

## Critical Instructions

**ASK MANY QUESTIONS.** This is not a quick review — it's a thorough interrogation of the design. 10, 15, 20+ questions is normal and expected. Do NOT rush. Do NOT summarize early. Keep asking until EVERY ambiguity is resolved.

After EACH answer:
- Dig deeper with follow-up questions on that topic
- Surface implications the user may not have considered
- Only move to the next topic when the current one is fully explored

**You are done when:**
- Every technical decision has a clear rationale
- Every edge case has a defined behavior
- Every integration point is specified
- You cannot think of any more meaningful questions to ask

Use your judgment — when answers start feeling complete and consistent, and you've covered all the topics below, wrap up and write the final spec. But if in doubt, ask another question.

## Interview Topics (Cover ALL of These)

- Technical implementation details (data structures, algorithms, system interactions)
- MCP protocol specifics (tool schemas, resource URIs, error responses)
- CommunicationMod integration (state handling, command timing, error recovery)
- Edge cases and error handling (what happens when things go wrong?)
- Testing strategy (unit tests, integration tests, mock game state)
- Risks and mitigation
- Future extensibility (how might this need to change later?)
- Dependencies and ordering (what needs to exist first?)

## Process

1. Read the specified plan file thoroughly
2. Identify ALL ambiguous or underspecified areas
3. Use AskUserQuestion with 2-4 focused options per question
4. After each answer, ask follow-up questions to go deeper
5. Continue interviewing until the user confirms completion
6. Update the plan file with the complete, detailed specification

## Anti-Patterns to Avoid

- Asking only 3-5 surface-level questions
- Accepting vague answers without digging deeper
- Moving on before a topic is fully explored
- Summarizing and finishing early to "save time"
- Assuming you know what the user wants
