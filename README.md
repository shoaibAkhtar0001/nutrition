# NutriTrack AI — Indian nutrition tracking on Django

NutriTrack started as a Django fitness/diet app. This version adds a personalised
nutrition engine for Indian food (new `nutrition` app) and fixes several bugs and
security problems in the original `proapp`.

> **Status: first vertical slice.** See [Completed vs. not yet built](#completed-vs-not-yet-built).
> Nothing below is claimed unless it has been run.

## Quick start

```bash
python -m venv .venv && source .venv/bin/activate     # Windows: .venv\Scripts\activate
pip install "django>=5.1,<5.2" requests google-genai
cp .env.example .env            # edit: set DJANGO_SECRET_KEY; keep DJANGO_DEBUG=1 for local dev
python manage.py migrate
python manage.py seed_foods     # 49 starter foods (ESTIMATES, see "Food data")
python manage.py runserver
```

Open http://127.0.0.1:8000/ → sign up → onboarding → review targets → dashboard.
The app **refuses to start** without `DJANGO_SECRET_KEY` unless `DJANGO_DEBUG=1`.

## Gemini setup

1. Create a Google AI Studio key.
2. Add the values to `.env`:

```dotenv
GEMINI_API_KEY=your_key_here
GEMINI_MODEL=gemini-2.5-flash
```

The project uses the official `google.genai` SDK and reads the env vars at runtime. If the key is missing, the AI coach automatically falls back to the app’s local nutrition guidance instead of breaking the page.

### Model choice

`gemini-2.5-flash` is the recommended default for a lightweight, responsive nutrition assistant and is widely available under Google’s free-tier allocation. The app gracefully handles model errors, rate limits, invalid credentials and unavailable models.

## AI Coach

The Django app includes a real AI coach experience on the existing AI Coach page. It uses the authenticated user record, daily nutrition totals, goals, dietary restrictions and meal history to generate personalised advice.

- Uses the real logged-in user, not a frontend-supplied user ID.
- Validates empty or duplicate messages server-side.
- Persists conversation history per user.
- Falls back cleanly if Gemini is unavailable.
- Keeps nutrition calculations in the deterministic app engine instead of allowing the LLM to invent totals.

## Tests

```bash
DJANGO_DEBUG=1 python manage.py test        # app + Gemini checks
```

## Tests

```bash
DJANGO_DEBUG=1 python manage.py test        # 44 tests
```

## Architecture

```
project1/           Django project (settings read secrets from env / .env)
proapp/             Legacy app: workouts, calorie calculator, simple diet generator (bugs fixed)
nutrition/          New app
  models.py         UserProfile, Food, FoodAlias, ServingUnit, MealEntry, WaterEntry, WeightEntry
  rules.py          Versioned target rules (Mifflin-St Jeor, caps, floors, warnings)
  engine.py         Deterministic Decimal maths: unit conversion, totals, summaries, hard constraints, search
  services.py       The only writers: idempotent logging, edit, copy, suggestions, insight
  views.py/urls.py  Onboarding, targets, dashboard, journal, food DB, water, weight
  management/       seed_foods (starter data), import_foods (CSV with provenance)
templates/nt/       New UI (Tailwind via CDN, forest-green design tokens)
```

Layers from the product spec: (1) deterministic maths → (2) hard user constraints →
(3) ranking (simple next-meal ranker for now) → (4) AI explanation (**not built yet**).
Logged entries store a nutrient **snapshot**: editing or deleting a food never rewrites history.

## Food data (important)

The 49 seeded foods are **approximate starter values: not laboratory data and not copied
from IFCT 2017.** Every row is `confidence=estimated` with a source note, and the UI says so.
To load licensed reference data, prepare a CSV and run `python manage.py import_foods file.csv`
(columns documented in the command). Household measures (roti, katori, glass…) are per-food
`ServingUnit` rows; a unit can never be applied to a different food.

## Safety rules

Targets use conservative versioned defaults in `nutrition/rules.py`: deficit capped at 500 kcal,
1,200 kcal floor, weight-loss goals refused at low BMI, under-18 warning. These are product
defaults, **not official guidance or medical advice**, and should be reviewed by a registered
dietitian. Allergies, diet pattern and excluded ingredients are hard filters; allergen tags depend
on the data and may be incomplete for mixed dishes (the UI says so).

## Fixes to the original code

- Removed hard-coded Django `SECRET_KEY`, Nutritionix keys and a RapidAPI key (now env vars).
  **Those keys are in git history: rotate them.**
- `/meal-log/` needed no login, listed every user's meals, and crashed on save. Now login-only, per-user.
- Streak/progress views used non-existent fields; streak logic broke on the 1st of a month.
- Signup accepted weak/duplicate usernames; signup and login never displayed errors.
- Outbound API calls had no timeout.
- `DEBUG`, `ALLOWED_HOSTS`, secure cookies now environment-driven.
- `venv/`, `__pycache__`, `db.sqlite3` don't belong in git: `.gitignore` added; run
  `git rm -r --cached venv db.sqlite3` and remove tracked `__pycache__`.

## Completed vs. not yet built

| Area | Status |
|---|---|
| Register / login / logout, protected routes | Done |
| Onboarding; target estimate with safety warnings; editable targets | Done |
| Dashboard (calories, macros, water, weight, week, next-meal ideas) from DB data | Done |
| Food journal: date nav, add/edit/delete, copy yesterday, autocomplete, recent foods | Done |
| Indian food DB (49 estimated starter foods), search, aliases, provenance | Done (starter data) |
| Allergy / diet / exclusion hard constraints | Done |
| Tests: engine, rules, isolation, double-submit, legacy fixes | 44 passing |
| Recipes (ingredient-based nutrition, yield/cooking factors) | **Not built** |
| Meal planner, shopping list, swaps | **Not built** (legacy random generator remains) |
| AI coach, photo logging, provider abstraction | **Not built** |
| Progress charts, reports, weekly summaries | **Not built** |
| Full settings page, data export, account deletion | **Not built** (targets editing only) |
| PostgreSQL, Docker, deployment config | **Not set up** (SQLite) |
| Rate limiting, extra security headers | **Not built** |
| Browser / E2E tests | **Not built** (flow smoke-tested with curl only) |

## Known limitations

Tailwind loads from its CDN (compile it for production). Legacy templates keep their original
look. Water entries cannot yet be edited or deleted. Plan / AI Coach / Progress appear in the nav
as disabled "Soon" items.
