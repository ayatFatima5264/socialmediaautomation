"""AI Content Planner service package.

Modular, reusable services behind the planner feature:

    strategy    — Strategy Service      (AI builds the content calendar)
    prompts     — Prompt Builder        (planner-specific prompt construction)
    scheduling  — Scheduling Service     (best day/time heuristic + distribution)
    runner      — Planner Service        (orchestrates generation as a job)

Content generation reuses `app.services.ai_service`; publishing reuses
`app.services.scheduler`. Nothing here is coupled to the API or UI layer.
"""
