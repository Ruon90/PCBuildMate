# PCBuildMate 🚀


Live demo: https://pcbuildmate-a48f3a1d143f.herokuapp.com/

Project board: https://github.com/users/Ruon90/projects/13

![Website landing page](/documentation/images/splash.png)

## Index 📑
1. [Overview](#overview)
2. [Agile Working](#agile-working)
3. [UX Design Process](#ux-design-process)
   - [User Stories](#user-stories)
   - [Wireframes](#wireframes)
   - [Mockup](#mockup)
   - [Color Scheme](#color-scheme)
   - [Fonts](#fonts)
4. [Features](#features)
   - [Data & Enrichment](#data-&-enrichment)
   - [Calculator / Core](#core)
   - [Calculator services / Build algorithm](#calculator)
   - [Upgrade Calculator](#upgrade-calculator)
   - [CRUD for saved upgrades](#crud)
   - [Preview builds](#preview)
   - [Edit builds](#edit-builds)
   - [API usage](#api-usage)
5. [Database](#database)
6. [Deployment (Git → IDE → Heroku)](#deployment)
7. [Testing and Validation](#testing-and-validation)
   - [HTML Validation](#html-validation)
   - [CSS Validation](#css-validation)
   - [JavaScript Validation](#javascript-validation)
   - [PEP8 / Python Validation](#pep8-validation)
   - [Lighthouse / Audits](#lighthouse)
8. [AI integration](#ai-integration)
9. [Tech used](#tech-used)
10. [Improvements & Future Work](#improvements--future-work)
11. [References](#references)

---

<a id="learning-points"></a>

<a id="overview"></a>
## Overview 🎯
PCBuildMate is a Django web app that recommends PC builds based on a user's budget and target use case (gaming or workstation). The app ingests and enriches hardware datasets, applies deterministic compatibility rules, and ranks candidate builds using a weighted scoring model. Users can preview, edit, save builds, and explore targeted upgrades.

Key features
- Data ingestion and enrichment (CSV imports, benchmark merging)
- Build calculator (compatibility checks, scoring, pricing, FPS/render estimates)
- UX: budget entry, preview, basic & advanced edit, upgrade calculator, saved builds
- Authentication and persistence (django-allauth + `UserBuild` model)

<a id="agile-working"></a>

## Agile Working 🔁
This project used agile development. User stories were created using a MoSCoW system and then split into smaller, bite-sized tasks to make progress incrementally.

User stories were categorised as Must-haves, Should-haves, Could-haves, and Won't-haves and moved through the workflow as tasks were started.

The main benefit of agile working is prioritising the MVP; during development an AI agent was implementable within scope and was added to the project.

Project board: https://github.com/users/Ruon90/projects/13

<a id="ux-design-process"></a>

## UX Design Process 🎨

<a id="user-stories"></a>

### User stories 👥
- Must-haves: budget-based build recommendations; visible benchmark and price/performance data; ability to save builds; regional pricing support.
- Should-haves: compare multiple saved builds; compatibility warnings (PSU, clearance, socket); a light/dark theme toggle.
- Could-haves: price-drop alerts, a "Build of the Month" showcase, and contextual tooltips for technical terms.

<a id="wireframes"></a>

### Wireframes 🖼️
<details>
<summary>Open wireframe images</summary>
Home

![Home wireframe](/documentation/wireframes/homeWF.png)

Results

![Results wireframe](/documentation/wireframes/resultsWF.png)

Login

![Login wireframe](/documentation/wireframes/loginWF.png)

</details>

<a id="mockup"></a>

### Mockup 🖼️

<details>

![Mockup](/documentation/images/mockup.png)

</details>

<a id="color-scheme"></a>

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

<a id="fonts"></a>

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

<a id="features"></a>

## Features 🔧

<a id="data-&-enrichment"></a>

### Data & Enrichment 🔎
- Slug-based matching across datasets, optional AI-assisted name normalization, benchmark CSV merging (Blender, UserBenchmark).

<a id="core"></a>

### Calculator / Core 🧮
- Compatibility checks (socket, DDR generation, power supply requirements, case/form factor)
- Scoring and ranking of builds by weighted component contributions
- FPS and render time estimates
- Preview and save flows (session-based preview for anonymous users, `UserBuild` model for persistent saves)

<a id="calculator"></a>

<a id="build-calculator-algorithm"></a>
### Build Calculator Algorithm 📈
This section summarizes the algorithm implemented in `calculator/services/build_calculator.py`.

Contract (short)
- Input: user constraints (budget, use-case, resolution), optional include/exclude lists.
- Output: ranked candidate builds with compatibility validation, aggregated cost, and estimated performance metrics.

Pipeline
1) Prefilter
   - Exclude parts far outside the soft price range (e.g., GPUs > 2× budget unless explicitly allowed).
   - Exclude items missing critical metadata (socket, TDP, form-factor) unless enrichment provides fallbacks.

2) Compatibility filtering
   - Deterministic checks: CPU ⇄ motherboard (socket), motherboard ⇄ RAM (DDR generation), case ⇄ motherboard form factor and GPU length, PSU ⇄ total wattage and connector requirements, Z series motherboards required for k series intel.

3) Scoring
   - Per-part scores are derived from benchmark sources (UserBenchmark, Blender) depending on application (gaming or workstation).
   - Example component weighting:
     - CPU: 1080p CPU is weighted higher as it will impact performance more than at higher resolutions
     - GPU: benchmark-derived FPS potential, weighted by resolution
     - RAM/storage: raw benchmark data collected from UserBenchmark
   - Combined build score:

     $S_{build} = w_{cpu} \cdot S_{cpu} + w_{gpu} \cdot S_{gpu} + w_{ram} \cdot S_{ram} + w_{storage} \cdot S_{storage} - w_{price} \cdot \frac{price}{100}$

   - Weights change by use-case (e.g. gaming increases $w_{gpu}$ for higher resolutions).

4) Ranking & selection
   - Rank by `S_build` and apply heuristics to avoid pathological combinations (very expensive GPU + weak CPU) and prefilters to reduce the size of the iterative loop.
   - Present top-k alternatives when useful.

5) Estimation (simplified)
   - FPS estimate:

     $FPS_{est} = baseFPS \cdot \left(\alpha \cdot \frac{S_{gpu}}{S_{gpu}^{ref}} + (1-\alpha) \cdot \frac{S_{cpu}}{S_{cpu}^{ref}}\right)$

     where $\alpha$ increases with resolution (GPU-dominant at 4K).
   - Render time: inverse proportional to normalized Blender score.

Edge cases
- Missing benchmark numbers: approximate from SKU families and log uncertainty.
- Hard incompatibilities: exclude candidates and surface clear reasons.
- Multi-part upgrades: consider only top-N candidates per slot to keep combinatorics tractable.

<a id="upgrade-calculator"></a>

### Upgrade Calculator ⚙️

The Upgrade Calculator compares a base build to proposed upgrades and helps users decide whether an upgrade is worth the cost.

High-level flow (form → calculation → recommendation)

1. Inputs

   - Base build component choices.
   - Context: target resolution (1080p / 1440p / 4K), use-case (gaming / workstation), and budget

2. Preprocessing / Presorting

   - Compatibility pruning: remove components that are out of budget and/or worse benchmarked performance than the current build, then prune incompatible components for the iterative loop (DDR generation differences, case size issues).
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
     - Choose the highest scoring compatible ram and CPU / GPU.

     - Check compatible components within budget.

     - Offer multiple proposals with the option to view or save upgrade suggestions.

4. Output & UI
   - The UI shows base vs upgraded parts, absolute and percent FPS/render improvement, price delta, and a short explanation (for example: "Bottleneck: CPU 25% consider replacement CPU for future upgrades").

<a id="crud"></a>

### CRUD for saved upgrades 💾

- Create: when a user clicks "Save upgrade" a record is created attached to the `UserBuild` (the app preserves the base build snapshot in JSON so comparisons remain reproducible).
- Read: users can view saved upgrades in their profile; the view reconstructs both the base and upgraded snapshots and renders deltas.
- Update: editing a saved upgrade recomputes deltas and updates the snapshot on save.
- Delete: users can remove an upgrade snapshot; the base `UserBuild` remains unaffected.

Notes: the repo currently stores saved upgrade snapshots as metadata on `UserBuild`. If desired, a dedicated `Upgrade` model with an FK to `UserBuild` can be added to simplify queries but is currently unnecessary.

<a id="preview"></a>

### Preview builds 👁️

- Anonymous users: a session-backed preview is created when a user requests a build. The preview JSON contains the parts selected, total price, and performance estimates. This preview isn't persisted to the DB until the user clicks "Save".

- Authenticated users: previews can be promoted to persistent `UserBuild` entries on save. The preview serializer includes canonical `slug` fields so the save process maps parts cleanly to model records.

- Implementation notes: previews are stored in `request.session['preview_build']` and rendered by `calculator.views.build_preview`. To make a preview permanent the view copies the snapshot into a `UserBuild` instance and triggers `save()` with `created_by=request.user`.

- There are icons at the bottom of each component, an icon for further information displaying all held information in the model, an icon for a hook to the Youtube API to return review results for the component and an amazon link for purchase, as I was unable to get Amazon API access this is just a search form using python template literal.

 - There are icons at the bottom of each component: an info icon that displays model details, an icon that hooks to the YouTube API to return review results, and an Amazon search link for purchase (direct Amazon API access was not obtained; the link performs a search).

<a id="edit-builds"></a>

### Edit builds ✏️

- Two edit modes exist:
  - Basic edit: a budget or quick-tune editor that re-runs the calculator with adjusted constraints and suggests replacements.

  - Advanced edit: a per-part editor (template fragment `edit_build_advanced.html`) allowing manual swap-in of parts with compatibility checks shown while choosing components, any mismatched builds will not be allowed to save..

- Workflow: the edit view loads the saved `UserBuild` snapshot, populates form fields with the current part slugs, and validates compatibility server-side on submit. If incompatible selections are submitted, the server returns structured errors to the advanced editor and the UI highlights offending fields.

<a id="api-usage"></a>

### API usage 🔌
Multiple APIs have been used in this project.
- YouTube API - used for fetching YouTube videos and details.
- Exchange Rate API - used for fetching up-to-date exchange rates for price calculations; this is configured on Heroku to refresh automatically.
- GitHub-hosted models - used for AI interaction; two models are configured (gpt-4.1-mini and gpt-4.1).
- Google OAuth for google signin.

<a id="database"></a>

## Database 🗄️
 PostgreSQL database is used to store the models, The app reads `DATABASE_URL` from the environment (Heroku Config Vars when deployed).

Schema overview (high level)
- `UserBuild` (saved builds)
  - id (PK), user (FK nullable for anonymous saves), parts_json (JSON snapshot of all parts and slugs), total_price (decimal), total_score (float), estimates_json (JSON: fps/render estimates), created_at, updated_at
- Parts tables (CPU, GPU, RAM, Motherboard, Storage, PSU, Cooler, Case)
  - id, slug (unique), manufacturer, model, price, bench_score, socket/tdp/vram/length/form_factor, metadata_json
- `CurrencyRate`
  - Currency API call, used for budget calculations and stored within `CurrencyRate` to then be used within the `UserBuild` calculations.

<details>
<summary>ERD</summary>

![ERD](/documentation/images/PCBMERD.png)

</details>

Indexes & ops

- Index `slug` columns (unique) on part tables for fast lookup.
- Index numeric columns used for range queries: `price`, `bench_score`.
- Add FK indices (default in Django) for joins (e.g., `UserBuild.user_id`).

Data lifecycle & maintenance
- Seeds/imports: CSV files live under `data/`. Use the provided import scripts / management commands (`hardware/management/commands/` and `calculator` utilities) to create and enrich rows.
- Migrations: use Django migrations; keep migration history small and readable. Squash historic migrations only when safe.
- Backups: for production Postgres, schedule regular pg_dump backups or use the managed provider's automated backups.

Best practices
- Prefer storing canonical `slug` + minimal metadata in `UserBuild` snapshots so imports/renames won't break old saved builds.
- Keep enrichment separate (benchmarks) so you can re-run enrichment jobs without changing original imported records.
- If you expect large datasets, consider partitioning heavy tables (historical price points) and caching common lookups.

Data import flow (quick)
1. Prepare CSVs in `data/` and ensure consistent column names.
2. Run enrichment/clean scripts if needed.
3. Run the import management command to populate part tables and generate slugs.

<a id="deployment"></a>

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

<a id="testing-and-validation"></a>

## Testing and Validation ✅
Manual testing was carried out to verify that users can login and signup, as well as create, read update and delete items from the database, as well as receive notifications when logging in and signing out.

Testing and validation have been carried out in multiple ways: Python tests and linters, online validators, and CI/PEP8 checks.

<a id="html-validation"></a>

<details>
<summary>HTML — Testing & validation images</summary>

The following screenshots show HTML-related pages and validation snapshots used during testing.

![Home HTML](/documentation/images/html/home-html.png)

![Builds HTML](/documentation/images/html/builds-html.png)

![Edit build HTML](/documentation/images/html/editbuild-html.png)

![Build preview HTML](/documentation/images/html/build-preview-html.png)

![Upgrade calculator HTML](/documentation/images/html/upgrade-calculator-html.png)

</details>

<a id="css-validation"></a>

<details>
<summary>CSS Validation</summary>

Style.css

![CSS](/documentation/images/css-validation.png)

</details>

<a id="javascript-validation"></a>

<details>
<summary>JavaScript — Testing & validation images</summary>

The following images show UI states and JavaScript-driven behaviors captured during testing. Filenames are labelled for clarity.

- `home_java.png` — Home (JavaScript-driven interactions)

![Home JS](/documentation/images/javascript/home_java.png)

- `editbuild_java.png` — Edit build (JavaScript interactions)

![Edit build JS](/documentation/images/javascript/editbuild_java.png)

- `editbuildpreview_java.png` — Edit build preview

![Edit build preview JS](/documentation/images/javascript/editbuildpreview_java.png)

- `upgrade_preview_java.png` — Upgrade preview

![Upgrade preview JS](/documentation/images/javascript/upgrade_preview_java.png)

- `upgrade_calculator_java.png` — Upgrade calculator

![Upgrade calculator JS](/documentation/images/javascript/upgrade_calculator_java.png)

</details>


<a id="pep8-validation"></a>
<details>

<summary>PEP8 and Python Validation</summary>

Python-related test runs and CI snapshots used during development.

- `views-pep8.png` — Views PEP8 / linting snapshot

![Views PEP8](/documentation/images/python/views-pep8.png)

- `calculator-tests.png` — Calculator test run

![Calculator tests](/documentation/images/python/calculator-tests.png)

- `buildcalculator-ci.png` — Build calculator CI / run

![Build calculator CI](/documentation/images/python/buildcalculator-ci.png)

</details>

<a id="lighthouse"></a>

<details>

<summary>Lighthouse and Wave</summary>

![Lighthouse desktop](/documentation/images/lighthouse-home.png)

![Lighthouse mobile](/documentation/images/lighthouse-homem.png)

![Wave](/documentation/images/wave.png)

</details>

<a id="ai-integration"></a>

## AI integration 🤖
AI has been used throughout the creation of this project, it is the only reason I was able to achieve a large scoped project in only three weeks.

AI has added code, debugged code, helped with design choices and helped to plan workflow. 

AI has also been implemented into the core site itself.

- An AI agent was added to the site to answer queries relating to computer building; the agent is also connected to the YouTube API and can suggest videos related to the user's prompt.

- Optional AI services can enrich part metadata and surface supplementary content (examples: name normalization and fetching review videos). These integrations are optional and not required for the core calculator.

Notes:
- If configured, AI enrichment runs during data import/enrichment or on-demand during preview generation; keep API keys private and set them via environment variables.


<a id="tech-used"></a>

## Tech used 🛠️
- HTML, CSS, JavaScript, Python, Django, Bootstrap, Select2, Postgres, Gunicorn, Whitenoise, Numpy, Pandas

<a id="improvements--future-work"></a>

## Improvements & Future Work 🔭
- Live price API integration and alerts.
- Separate Upgrade model for cleaner queries and UI workflows.
- Forum.
- Improve FPS accuracy.
- Add extra sets of benchmarks for normalisation.
- Create benchmarking software.

<a id="references"></a>

## References 📚
- Blender Open Data, UserBenchmarks, TechPowerUp, Django docs, Bootstrap docs.

