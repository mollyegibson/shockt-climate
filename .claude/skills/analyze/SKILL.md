---
name: analyze
description: >
  Answer questions about ShockT Climate data and analysis results. Use whenever the user
  asks about the data, results, emissions, supply, imports, shares, origins, lanes, tariffs,
  shocks, chokepoints, transport modes, HS codes, cases, products, or specific countries —
  or asks to "look at", "check", "compare", "break down", "show me", or "what happened to"
  anything in the data. Also use when the user asks about existing notebook findings or wants
  a custom cut of the data.
---

# Analyze

Answer questions about ShockT Climate data: either explain existing notebook results or run
ad-hoc analysis. Present answers in plain English with supporting numbers.

## Preflight

Before any database work, verify the analyst connection is configured:

```sh
grep -q 'ANALYST_DATABASE_URL=.' analysis/.env 2>/dev/null
```

If the file is missing or the variable is empty, tell the user:

> The analyst database connection isn't configured yet. See the Setup section in
> `analysis/README.md` for how to get the credentials from the engineering team.

Then stop. Do not attempt to connect without the credential.

## Step 1: Discover what exists

Run these at the start of every invocation to build a live inventory:

1. **Notebooks**: `find analysis/ -name "*.ipynb" -not -path "*/.ipynb_checkpoints/*"`
2. **Cases**: `ls inputs/cases/`
3. **HS codes**: read `data-pipelines/config/hs_codes.yaml` to map prefixes → cases
4. **Notebook headings**: for each notebook, extract its markdown section headings
   (read the `.ipynb` and scan cells with `cell_type == "markdown"` for lines starting
   with `#`)

This tells you what cases, products and analyses exist right now.

## Step 2: Classify the question

| Signal | Mode |
|---|---|
| Maps to a notebook section (supply shares, lane emissions, mix decomposition, findings, shock dating, route length, port of entry, etc.) | **Explain existing** |
| Spans multiple cases or notebooks (cross-case comparison, strongest signal, summary across products) | **Explain existing** — read the relevant sections from each notebook and synthesize |
| About data not covered by any notebook, or asks for a custom filter, time range, comparison, or aggregation | **Ad-hoc analysis** |
| Ambiguous | Read the most relevant notebook first; if its outputs answer the question, explain them; otherwise fall through to ad-hoc |

## Step 3a: Explain existing results

1. Read the relevant `.ipynb` file (the Read tool handles Jupyter natively and returns
   all cells with their outputs).
2. Find the section(s) that answer the question by matching markdown headings and
   scanning output cells.
3. Read the case's `inputs/cases/<case>/shock_windows.yaml` and `evidence.yaml` for
   context on what the windows mean and what policy events or shocks drive them.
4. Synthesize the answer. Structure it as:

   **The answer** — 2–3 sentences in plain English. Define domain terms inline on first
   use (e.g. "the supply mix — the weighted-average emissions across all origin and mode
   combinations"). Use precise numbers, not hedging.

   **The numbers** — a formatted table or key figures pulled from the notebook's output
   cells. Keep it to the rows and columns that matter for the question.

   **What this means** — one sentence connecting the number to the real-world
   implication (emissions went up/down, supply shifted from X to Y, a route got
   longer/shorter, etc.).

   **Methodology** — one line: which notebook and section produced this, what data
   source it used.

## Step 3b: Ad-hoc analysis

1. Read `references/data-access.md` (in this skill's directory) to pick the right
   `core.py` reader functions.
2. If the question needs engine computation (emissions, shares, decomposition), also
   read `references/engine-api.md`.
3. **Verify signatures before coding**: grep the actual source for each function you
   plan to call to confirm it still matches the reference. Reference files can drift.
   ```sh
   grep -n '^def supply' analysis/src/shockt_analysis/core.py
   ```
   If a signature has changed, use the source — not the reference — and note the
   discrepancy so it can be fixed.
4. Write a Python script that:
   - Imports from `shockt_analysis.core`, `shockt_analysis.cases`, `shockt_analysis.settings`,
     and `shockt_engine` as needed
   - Connects read-only: `with core.connect(get_settings()) as conn:`
   - Queries the relevant tables via the reader functions
   - Computes the answer with Polars operations
   - Prints the results as formatted tables (`pl.Config.set_tbl_rows(40)`)
   - Generates a chart when appropriate (see Chart decision below)
5. Save the script to the scratchpad, then run it:
   ```sh
   cd <repo-root>/analysis && uv run python -I <scratchpad>/analyze_<topic>.py
   ```
6. Read any chart PNGs to display them to the user.
7. Present the answer in the same structure as Step 3a (answer, numbers, meaning,
   methodology).

### Chart decision

Include a chart when it adds clarity the table alone doesn't give:

| Question shape | Chart type |
|---|---|
| Change over time (monthly supply, emissions trend) | Line chart |
| Compare categories (origins, modes, products) | Horizontal bar chart |
| Composition or shares | Stacked bar |
| What drove a change (Shapley decomposition) | Waterfall (`cases.plot_waterfall`) |
| A single number or short list | No chart — table only |

Use matplotlib following the existing notebook patterns. Save the PNG to the scratchpad
directory and read it back to show the user.

Chart style:
- Use `fig, ax = plt.subplots(figsize=(10, 6))` as a default size
- Use the muted palette from the notebooks: `#8a9a8f`, `#2d5b4f`, `#a2412d`, `#d9e5d6`,
  `#f3dfb6`, `#f0c7c0`
- Label axes with units; include a title
- `plt.tight_layout()` before saving
- Save as: `plt.savefig("<scratchpad>/chart_<topic>.png", dpi=150)`

## Step 4: Save prompt

After presenting results, ask: **"Want to save this analysis as a notebook?"**

If yes:
1. Choose a kebab-case directory name derived from the question topic (e.g.
   `vietnam-apparel-share`, `emission-factor-comparison`).
2. Create `analysis/<topic>/` if it doesn't exist.
3. Convert the analysis script into a Jupyter notebook (`.ipynb`) using
   `jupytext` or by writing the JSON directly. Structure it as:
   - A markdown cell with a title and one-paragraph description of the question
   - Code cells matching the script's logic, broken at logical boundaries
   - Markdown cells between code sections explaining what each does
4. Execute the notebook to populate its outputs:
   ```sh
   cd <repo-root>/analysis && uv run jupyter nbconvert --to notebook --execute --inplace <topic>/<topic>.ipynb
   ```
5. Tell the user where it is: `analysis/<topic>/<topic>.ipynb`

If no: the script stays in the scratchpad (ephemeral). Move on.

## Tone and language

The audience is data scientists and analysts on the ShockT team. They know the domain
but avoid jargon:
- Lead with plain English
- Define domain terms inline on first use
- Use precise numbers ("Taiwan's share rose from 42% to 58%"), not hedging ("increased
  significantly")
- When referencing a notebook section, name it by number and title (e.g. "Section 4:
  Origin shares and diversion rates in the Case 1 notebook")

## Constraints

- **Read-only**: never write to the database. Every connection uses the analyst login.
- **No hand-entered data**: if a question needs a number you don't have, query for it
  or say you can't answer — never type a value from memory.
- **Reproducibility**: every ad-hoc script must be runnable from scratch by anyone with
  the analyst `.env` set up. No hardcoded credentials, no paths outside the repo.
- **No `# type: ignore`, `# noqa`, `as any`**: follow the project's quality rules even
  in ad-hoc scripts.
