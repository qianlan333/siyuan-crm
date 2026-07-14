# R13-A Questionnaire Editor Asset Split

## Goal

Split the only template above 3000 lines without changing its DOM, styling, API calls, or business behavior.

## Implementation

1. Move the existing inline CSS verbatim into a questionnaire-owned static stylesheet.
2. Move the existing executable inline JavaScript into a questionnaire-owned static script.
3. Serialize the Jinja editor configuration into a non-executable JSON script element and parse it during boot.
4. Mount the questionnaire static directory before the general static mount.
5. Add asset-route, DOM/config, size-budget, and permanent Full CI coverage.

## Verification

- Questionnaire editor template and page contract tests.
- Static asset HTTP checks.
- Inline-script and template-size guards.
- Full architecture gates.
