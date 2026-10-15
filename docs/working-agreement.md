# Working Agreement

- **Status:** living document; amend by PR when the team agrees a rule has changed
- **Companion:** [Domain-Driven Design and Hexagonal Architecture](./domain-driven-design.md), the reasoning behind these rules

The short, citable form of what we hold each other to in review.

## Architecture

1. **Adapters translate; they don't decide.** A CLI command or API handler that contains a business rule is a bug.
2. **Every upstream response is decoded through a parser or schema we own.** Raw JSON never crosses into domain code.
3. **Persistence and network code stay in adapters.** Engine and load-rule code take and return plain values.
4. **Dependencies form a DAG rooted in the domain.** No cycles, no domain → adapter imports.
5. **Contexts share database contracts, never code.** Pipelines publish `core`, the engine publishes `outputs`, the app reads them.
6. **One emissions engine.** Every emissions number comes from the engine package; never reimplement a factor or distance in the app or a notebook.
7. **Skip the layer when it earns nothing.** No substitution needed and no adapter calling it? Write a function.
8. **A new term in the code is a new row in the [Ubiquitous Language](./ubiquitous-language.md)**, in the same PR.

## Data

9. **`raw` is never edited by hand.** Every change is a load recorded in `raw.load_manifest`, with its filters in `params` and its source file in the archive.
10. **No hand-entered data.** Every value in the database comes from a source through a loader, or from checked-in code (a dbt model or macro, or a `shockt ref` generator). Seeds are generated, never edited; declared choices live in `config/`. See AGENTS.md, Data Provenance.
11. **Migrations are append-only once applied.** A change to an applied migration goes in a new migration, with a sequential `--rev-id`. The database owner applies them.

## Configuration and secrets

12. **Secrets live only in `.env` (gitignored) or a platform secret store.** Never in `config/`, code, docs, manifest params or logs. Type them as secrets (`SecretStr` in Python, `Redacted` in Effect).
13. **Required configuration fails loudly when unset.** No plausible defaults for values that differ between environments or people.

## Quality

14. **Never disable type checking or linting**: no `# noqa`, `# type: ignore`, `as any` or `as unknown as T`. Fix the code instead.
15. **Tests and lint pass before a PR is opened.**
