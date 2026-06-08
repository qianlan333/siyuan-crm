# CRM Assistant Patterns

## Silent Reactivation

1. Inspect dimensions.
2. Reuse an existing segment or propose a validated one.
3. Preview members and interaction stats.
4. Request copy variants when needed.
5. Propose a campaign and submit for CRM review.

Keep the cadence short, usually three or four steps, and set `stop_on_reply`
when the workflow supports it.

## Time-Limited Campaign

Use `anchor_mode=campaign_start_date` so every recipient follows the same event
calendar. Keep steps tied to the actual offer window.

## Questionnaire-Based Audience

1. Find the questionnaire.
2. Inspect questions and option ids.
3. Preview the population using exact option ids.
4. Compose or validate segment SQL.
5. Propose the segment and then the campaign.

Prefer exact option ids over fuzzy text whenever possible.

## Review And Improve

For a weak campaign, query recent outcomes, pause if needed, then propose a new
draft. Do not mutate a running plan invisibly.

## One-Off Broadcast

Use the single-broadcast draft path only for simple one-step notices. Otherwise
prefer campaign drafts so segmentation, cadence, and review stay explicit.

## Ambiguous Requests

Ask one clarifying question when the target audience or business meaning is
unclear. If the user delegates judgment, state the assumptions in the draft
summary.
