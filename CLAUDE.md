# CLAUDE.md — WSRE Intelligence

## Working autonomy

Default to acting, not asking. For this project, execute work without seeking approval at every step.

### Proceed without asking

- File edits, creation, deletion within the project
- Running tests, linters, type checks
- Running migrations against local dev databases
- Running scrapers, ingestion jobs, API calls to free public endpoints
- Committing to feature branches
- Pushing feature branches to origin
- Refactoring across multiple files
- Schema changes that are reversible
- Frontend visual changes
- Adding/removing dependencies (free, open-source)
- Generating, editing, or rendering documents/screenshots/PDFs

### Ask before proceeding

- Operations that cost real money beyond minor LLM API spend (e.g. provisioning paid infrastructure, paid SaaS signups)
- Production deployments
- Merging to main (always confirm before merging the active feature branch to main)
- Destructive operations on data we cannot recreate (dropping production tables, deleting non-recoverable files)
- Anything touching credentials, API keys, .env files
- Operations against third-party APIs that have explicit ToS concerns or quota costs (paid APIs, rate-limited services where over-use has consequences)
- Anything Karol has explicitly flagged as gated (e.g. anything involving the demo plot's defensible numbers — these were tuned and shouldn't be changed without confirmation)

### Report style

- Report what was done, not what you're about to do
- Skip "shall I proceed?" closings unless one of the "ask before proceeding" cases applies
- For multi-step work, batch related steps and report at the end rather than gate each one
- Use markdown tables and short bullets for summaries; not prose paragraphs
- If a step encounters an error you can fix without judgment calls, fix it and continue, then mention in the report what was fixed

When in doubt, prefer to act. Karol can always revert via git, and this is a feature branch — main stays clean. Lean autonomous.
