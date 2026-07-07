# AI Content Planner — Architecture

The planner is an **AI Marketing Manager**: it thinks strategically first (a
themed, balanced plan), then writes and schedules the posts. It reuses the same
backend services as the single-post AI Generator — nothing is duplicated.

## Pipeline

```
PlannerSetup ─▶ Signals ─▶ Strategy ─▶ (user reviews) ─▶ Runner ─▶ Posts ─▶ Scheduler
              (context)   (theme +                     (generate +          (existing
                           calendar)                    schedule)            publish loop)
```

| Stage | Module | Responsibility |
|-------|--------|----------------|
| Signals | `signals.py` | Assemble strategy context from pluggable providers |
| Strategy | `strategy.py` + `prompts.py` | One LLM call → `{theme, summary, topics}` |
| Scheduling | `scheduling.py` | Best-time heuristic + timezone-aware distribution |
| Runner | `runner.py` | Background job: per-topic × platform generation → `Post` rows |
| Content | `app/services/ai_service.py` (**shared**) | The same generator the AI Generator uses |
| Publish | `app/services/scheduler.py` (**shared**) | Approved posts flow through the existing loop |

## Shared with the single-post AI Generator (no duplication)
- **Business Profile** → `business_profile_service` (via the signal provider)
- **Post copywriting** → `ai_service.generate_posts` + `prompt_templates.build_user_prompt`
- **Downstream** → the same `posts` table, Scheduler, Calendar, and Post History.
  Planner posts carry `plan_id`; single posts have `plan_id = null`. Both remain
  individually editable everywhere.

## Extensibility: signal providers
The strategy's "brain" is a stack of **signal providers** (`signals.py`). Each
returns a `Signal(context, guidance)` that is merged into the strategy prompt.
Adding a capability = writing one provider and flipping `enabled = True`. The
strategy engine never changes.

| Provider | Status | What it will contribute |
|----------|--------|-------------------------|
| `BusinessProfileProvider` | **active** | Industry, audience, voice, goals grounding |
| `SeasonalProvider` | stub | Ramadan, Eid, Black Friday, New Year… timely moments |
| `TrendingProvider` | stub | Current industry trends as fresh angles |
| `CompetitorProvider` | stub | Differentiation cues (inspire, never copy) |
| `PerformanceProvider` | stub | Bias the mix toward what performed well (needs analytics) |
| `PreferenceLearningProvider` | stub | Learn from the user's edits/regenerations |

`record_edit()` in `signals.py` is the capture hook the learning provider will
read from — call sites can be added when learning ships without a refactor.

### To add "Seasonal campaigns" later
1. Implement `SeasonalProvider.gather()` to return upcoming events for the
   plan's date window + region.
2. Set `enabled = True`.
3. Done — the strategy prompt now includes seasonal context and guidance.

Monthly campaigns, recurring campaigns, and multi-workspace planning layer on
top of `ContentPlan` (a "campaign" row) without touching this pipeline.
