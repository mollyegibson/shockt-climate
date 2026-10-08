# ShockT Climate

## Climatebase Fellowship Capstone Project - Cohort 10

ShockT Climate helps a company decide its next move when a supply-chain shock hits, using the carbon cost of how the market responded to real past shocks.

The user is a sustainability director at a company that buys, builds or operates data center hardware and reports Scope 3 emissions. When a shock hits, they need to influence their company's response (transport mode, port of entry, timing and inventory, and volume between existing sites) before the emissions show up in next year's inventory.

The MVP pairs two case studies with a scenario calculator, both for data center hardware:

- **Policy shock:** the 2025 US tariffs and the shift of AI server supply between Taiwan and Mexico.
- **Physical and climate shock:** the 2023–24 Panama Canal drought and Red Sea diversions, which squeezed Asia-to-US East Coast shipping.

The case studies measure how shipping patterns changed during each shock. The calculator applies those observed responses to a user's own shipments, and compares the emissions of following the market with the lower-carbon options the user controls. All numbers come from a deterministic emissions engine (tonnes × distance × emission factor, door to door). The product shows how a supply chain responds to a type of shock; it doesn't predict when shocks happen.

## How it fits together

1. **Data pipelines** load public trade, shipping and emissions data (US Census, BTS TransBorder, IMF PortWatch, Climate TRACE) into Postgres.
2. **Analysis** in notebooks identifies shock windows and how the market responded, committed to the repo as reviewed inputs.
3. **The engine** turns those inputs into per-tonne emissions for each response and alternative.
4. **The app** presents the case studies and the calculator.

## Repository layout

| Directory | Contents |
|---|---|
| [`data-pipelines/`](data-pipelines/) | Ingestion pipelines and dbt models for the `raw` and `core` database layers (Python) |
| [`docs/plans/`](docs/plans/) | Technical designs, starting with the [data ingestion pipelines](docs/plans/data-ingestion-pipelines.md) |

The engine, analysis notebooks, analytical inputs, case-study write-ups and the React/TypeScript app will each get their own directory as the work starts.
