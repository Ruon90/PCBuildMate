# PCBuildMate 🚀

Live site (demo): https://w########.herokuapp.com/

Project board: https://github.com/users/Ruon90/projects/13

## PCBuildMate 🚀

Live demo: https://w########.herokuapp.com/

Project board: https://github.com/users/Ruon90/projects/13

![Website landing page](/documentation/images/home.png)

## Index 📑
1. [Overview](#overview)
2. [UX Design Process](#ux-design-process)
   - [User Stories](#user-stories)
   - [Wireframes](#wireframes)
   - [Color Scheme](#color-scheme)
   - [Fonts](#fonts)
3. [Features](#features)
   - [Upgrade Calculator](#upgrade-calculator)
4. [Build Calculator Algorithm](#build-calculator-algorithm)
5. [Database](#database)
6. [Deployment (Git → IDE → Heroku)](#deployment-git--ide--heroku)
7. [Testing and Validation](#testing-and-validation)
8. [AI integration](#ai-integration)
9. [Tech used](#tech-used)
10. [Improvements & Future Work](#improvements--future-work)
11. [References](#references)
12. [Learning points](#learning-points)

---

## Overview 🎯
PCBuildMate is a Django web app that recommends PC builds based on a user's budget and target use case (gaming or workstation). The app ingests and enriches hardware datasets, applies deterministic compatibility rules, and ranks candidate builds using a weighted scoring model. Users can preview, edit, save builds, and explore targeted upgrades.

Key features
- Data ingestion and enrichment (CSV imports, benchmark merging)
- Build calculator (compatibility checks, scoring, pricing, FPS/render estimates)
- UX: budget entry, preview, basic & advanced edit, upgrade calculator, saved builds
- Authentication and persistence (django-allauth + `UserBuild` model)

## UX Design Process 🎨
See `documentation/` for full wireframes and mockups.

### User stories 👥
- Must-haves: budget-based build recommendations; visible benchmark and price/performance data; ability to save builds; regional pricing support.
- Should-haves: compare multiple saved builds; compatibility warnings (PSU, clearance, socket); a light/dark theme toggle.
- Could-haves: price-drop alerts, a "Build of the Month" showcase, and contextual tooltips for technical terms.

### Wireframes 🖼️
<details>
<summary>Open wireframe images</summary>

![Home wireframe](/documentation/wireframes/homeWF.png)

![Results wireframe](/documentation/wireframes/resultsWF.png)

![Login wireframe](/documentation/wireframes/loginWF.png)

</details>

Mockups are in `documentation/wireframes/`.

### Color Scheme 🎨
The canonical color palette is taken from `buildmate/static/css/style.css`. A visual swatch is included for reference.

![Color swatch](/documentation/images/color-swatch.svg)

- Accent / Primary — #2e7cf7 (CSS var `--accent`): primary action color for buttons and interactive accents.
- Accent contrast — #ffffff (CSS var `--accent-contrast`): text color used on accent backgrounds.
- Text primary — #e8eefc (CSS var `--text-primary`): primary text color used for headings and hero text.
- Text secondary — #b8c3d9 (CSS var `--text-secondary`): subdued text and metadata.
- Page background — #ececec: used for light page backgrounds.
- Hero overlay — rgba(14,18,28,0.65) (CSS var `--bg-overlay`): translucent overlay for hero imagery.
- Navbar / translucent surfaces — rgba(0,0,0,0.35).
- FPS delta positive — #39b54a (green); negative — #ff6666 (red).

Accessibility
- When producing submission screenshots, verify contrast where text overlays images. The accent color (`#2e7cf7`) is paired with white (`#ffffff`) for good button contrast.

### Fonts 🔤
- Body: Inter (loaded via Google Fonts in `base.html`)
- Headings: IBM Plex Sans (loaded via Google Fonts in `base.html`)

The template includes a system-font fallback stack to ensure legibility if webfonts fail to load.

Fonts are loaded in `buildmate/templates/base.html` with:

```html
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=IBM+Plex+Sans:ital,wght@0,100..700;1,100..700&family=Inter:ital,opsz,wght@0,14..32,100..900;1,14..32,100..900&display=swap" rel="stylesheet">
```

## Features 🔧

### Data & Enrichment 🔎
- Slug-based matching across datasets, optional AI-assisted name normalization, benchmark CSV merging (Blender, UserBenchmark).

### Calculator / Core 🧮
- Compatibility checks (socket, DDR generation, NVMe vs SATA, case/form factor)
- Scoring and ranking of builds by weighted component contributions
- FPS and render time estimates
- Preview and save flows (session-based preview for anonymous users, `UserBuild` model for persistent saves)

## Build Calculator Algorithm 📈
This section summarizes the algorithm implemented in `calculator/services/build_calculator.py`.

Contract (short)
- Input: user constraints (budget, use-case, resolution), optional include/exclude lists.
- Output: ranked candidate builds with compatibility validation, aggregated cost, and estimated performance metrics.

Pipeline
1) Prefilter
   - Exclude parts far outside the soft price range (e.g., GPUs > 2× budget unless explicitly allowed).
   - Exclude items missing critical metadata (socket, TDP, form-factor) unless enrichment provides fallbacks.

2) Compatibility filtering
   - Deterministic checks: CPU ⇄ motherboard (socket), motherboard ⇄ RAM (DDR generation), case ⇄ motherboard form factor and GPU length, PSU ⇄ total wattage and connector requirements.

3) Scoring
   - Per-part scores are derived from benchmark sources (UserBenchmark, Blender) and normalized for cross-part comparison.
   - Example component weighting:
     - CPU: multi-core and single-core metrics depending on workload
     - GPU: benchmark-derived FPS potential, weighted by resolution
     - RAM/storage: capacity and generation bonuses
   - Combined build score:

     $S_{build} = w_{cpu} \cdot S_{cpu} + w_{gpu} \cdot S_{gpu} + w_{ram} \cdot S_{ram} + w_{storage} \cdot S_{storage} - w_{price} \cdot \frac{price}{100}$

   - Weights change by use-case (e.g., gaming increases $w_{gpu}$ for higher resolutions).

4) Ranking & selection
   - Rank by `S_build` and apply heuristics to avoid pathological combinations (very expensive GPU + weak CPU).
   - Present top-k alternatives when useful.

5) Estimation (simplified)
   - FPS estimate (prioritization-level):

     $FPS_{est} = baseFPS \cdot \left(\alpha \cdot \frac{S_{gpu}}{S_{gpu}^{ref}} + (1-\alpha) \cdot \frac{S_{cpu}}{S_{cpu}^{ref}}\right)$

     where $\alpha$ increases with resolution (GPU-dominant at 4K).
   - Render time: inverse proportional to normalized Blender score.

Edge cases
- Missing benchmark numbers: approximate from SKU families and log uncertainty.
- Hard incompatibilities: exclude candidates and surface clear reasons.
- Multi-part upgrades: consider only top-N candidates per slot to keep combinatorics tractable.

### Upgrade Calculator ⚙️

The Upgrade Calculator compares a base build to proposed upgrades and helps users decide whether an upgrade is worth the cost.

High-level flow (form → calculation → recommendation)

1. Inputs

   - Base build identifier or snapshot
   - Context: target resolution (1080p / 1440p / 4K), use-case (gaming / workstation), and budget

2. Preprocessing / Presorting

   - Compatibility pruning: remove candidate upgrade parts that are incompatible with the base (socket mismatches, DDR generation differences, case size issues).
   - Price / performance deltas: for each candidate replacement compute `Δprice = price_new - price_old` and `Δperf = perf_new - perf_old` (where `perf` is Blender score for workstation or UserBenchmark scores for gaming).
   - Presort by `Δperf` descending.

3. Recommendation selection

   - Scoring: compute an "upgrade score" for each candidate or combination:

     $score_{upgrade} = w_{perf} \cdot \frac{Δperf}{perf_{base}} - w_{cost} \cdot \frac{Δprice}{price_{base}}$

     Weights (`w_perf`, `w_cost`) vary by use-case (gaming favors performance gains; workstation favors render time improvements).

   - Bottleneck handling: if a single-slot upgrade yields minimal `Δperf` because another component is limiting, the candidate is annotated so users understand why gains are small.

   - Combination evaluation: for larger upgrades (CPU + motherboard + RAM), the calculator estimates combined `Δprice` and `Δperf` and evaluates the combined score. Presorting keeps the search tractable (top-N per slot).

   - Selection examples:
     - Budget cap: choose the highest-scoring candidate under the cap.
     - Best value: choose the candidate maximizing `Δperf/Δprice`.
     - Best absolute: choose the candidate with the largest `Δperf`.

4. Output & UI
   - The UI shows base vs upgraded parts, absolute and percent FPS/render improvement, price delta, and a short explanation (for example: "GPU upgrade yields +31% FPS at 1440p; CPU remains the bottleneck — consider CPU upgrade for further gains").

### CRUD for saved upgrades

- Create: when a user clicks "Save upgrade" a record is created attached to the `UserBuild` (the app preserves the base build snapshot in JSON so comparisons remain reproducible).
- Read: users can view saved upgrades in their profile; the view reconstructs both the base and upgraded snapshots and renders deltas.
- Update: editing a saved upgrade recomputes deltas and updates the snapshot on save.
- Delete: users can remove an upgrade snapshot; the base `UserBuild` remains unaffected.

Notes: the repo currently stores saved upgrade snapshots as metadata on `UserBuild`. If desired, a dedicated `Upgrade` model with an FK to `UserBuild` can be added to simplify queries.

### Preview builds 👁️

- Anonymous users: a session-backed preview is created when a user requests a build. The preview JSON contains the parts selected, total price, and performance estimates. This preview isn't persisted to the DB until the user clicks "Save".
- Authenticated users: previews can be promoted to persistent `UserBuild` entries on save. The preview serializer includes canonical `slug` fields so the save process maps parts cleanly to model records.
- Implementation notes: previews are stored in `request.session['preview_build']` and rendered by `calculator.views.build_preview`. To make a preview permanent the view copies the snapshot into a `UserBuild` instance and triggers `save()` with `created_by=request.user`.

### Edit builds ✏️

- Two edit modes exist:
  - Basic edit: a budget or quick-tune editor that re-runs the calculator with adjusted constraints and suggests replacements.
  - Advanced edit: a per-part editor (template fragment `edit_build_advanced.html`) allowing manual swap-in of parts with compatibility checks applied on save.
- Workflow: the edit view loads the saved `UserBuild` snapshot, populates form fields with the current part slugs, and validates compatibility server-side on submit. If incompatible selections are submitted, the server returns structured errors to the advanced editor and the UI highlights offending fields.

## Database 🗄️
Primary DB expectations:
- Dev: SQLite (fast, zero-config for local development)
- Prod: PostgreSQL (recommended). The app reads `DATABASE_URL` from the environment; `psycopg2` is listed in `requirements.txt`.

Schema overview (high level)
- `UserBuild` (saved builds)
  - id (PK), user (FK nullable for anonymous saves), parts_json (JSON snapshot of all parts and slugs), total_price (decimal), total_score (float), estimates_json (JSON: fps/render estimates), created_at, updated_at
- Parts tables (CPU, GPU, RAM, Motherboard, Storage, PSU, Cooler, Case)
  - id, slug (unique), manufacturer, model, price, bench_score, socket/tdp/vram/length/form_factor, metadata_json
- `CurrencyRate` / pricing helpers
  - currency, rate, updated_at

Indexes & ops
- Index `slug` columns (unique) on part tables for fast lookup.
- Index numeric columns used for range queries: `price`, `bench_score`.
- Add FK indices (default in Django) for joins (e.g., `UserBuild.user_id`).

Data lifecycle & maintenance
- Seeds/imports: CSV files live under `data/`. Use the provided import scripts / management commands (`hardware/management/commands/` and `calculator` utilities) to create and enrich rows.
- Migrations: use Django migrations; keep migration history small and readable. Squash historic migrations only when safe.
- Backups: for production Postgres, schedule regular pg_dump backups or use the managed provider's automated backups.

Best practices & tips
- Prefer storing canonical `slug` + minimal metadata in `UserBuild` snapshots so imports/renames won't break old saved builds.
- Keep enrichment separate (benchmarks) so you can re-run enrichment jobs without changing original imported records.
- If you expect large datasets, consider partitioning heavy tables (historical price points) and caching common lookups.

Data import flow (quick)
1. Prepare CSVs in `data/` and ensure consistent column names.
2. Run enrichment/clean scripts if needed.
3. Run the import management command to populate part tables and generate slugs.

## Deployment  🚀
This simplified flow focuses on deploying the app quickly using a fork → IDE → Heroku approach.

1) Fork & clone (GitHub)

 - Use the GitHub UI to fork this repository to your account. Then clone your fork locally:

```bash
git clone https://github.com/<your-username>/PCBuildMate.git
cd PCBuildMate
```

2) Open in your IDE and install dependencies

 - Open the project in VS Code (or your preferred editor), create a virtual environment, then install dependencies:

```bash
python -m venv .venv
source .venv/Scripts/activate   # for Windows Bash (Git Bash / WSL)
pip install -r requirements.txt
```

3) Run locally to verify

```bash
python manage.py migrate
python manage.py runserver
# Visit http://127.0.0.1:8000 to confirm the site loads
```

4) Deploy via Heroku dashboard (no CLI required)

 - Create a Heroku app using the Heroku web dashboard.
 - In the app's **Deploy** tab select **GitHub** and connect your fork's repository. Choose the `main` branch and click **Deploy Branch** (you can also enable automatic deploys).
 - In **Settings → Config Vars** add required env vars (e.g., `SECRET_KEY`, `DATABASE_URL` if using an external DB, `EXCHANGE_RATE_API_KEY`, social auth keys if used).
 - After deployment, run migrations from Heroku's web interface: open the app in the dashboard, click **More → Run console** and run `python manage.py migrate`. You can also run `python manage.py collectstatic --noinput` here if needed.

Notes

- If you prefer pushing from the command-line, you can still use the `git push heroku main` flow; this guide emphasizes the Heroku UI approach.
- Ensure OAuth redirect URIs configured for Google/Apple match your Heroku domain.
- Use `Procfile` with `web: gunicorn buildmate.wsgi --log-file -` for production (already present in repo).

## Testing and Validation ✅
- Run unit tests:

```bash
python manage.py test
```

- HTML validation: ensure templates add placeholder first <option value=""> entries for required selects and avoid inline style/script where possible.
- Smoke tests: run the devserver and click through main flows (build preview, edit, upgrade); watch the browser console for JS errors.

## AI integration 🤖
- Optional AI services can enrich part metadata and surface supplementary content (examples: name normalization and fetching review videos). These integrations are optional and not required for the core calculator.

Notes:
- If configured, AI enrichment runs during data import/enrichment or on-demand during preview generation; keep API keys private and set them via environment variables.

## Tech used 🛠️
- Python, Django, Bootstrap, Select2, SQLite/Postgres, Gunicorn, Whitenoise

## Improvements & Future Work 🔭
- Add CI (GitHub Actions) with linters (ruff/black) and tests
- Dockerfile + docker-compose for reproducible dev env
- Live price API integration and alerts
- Separate Upgrade model for cleaner queries and UI workflows

## References 📚
- Blender Open Data, UserBenchmarks, TechPowerUp, Django docs, Bootstrap docs.

## Learning points 💡
- Compatibility engines require conservative fallbacks and good logging.
- Moving inline assets to static files improves caching and maintainability.
- Session previews provide low-friction UX for anonymous experimentation.
```

