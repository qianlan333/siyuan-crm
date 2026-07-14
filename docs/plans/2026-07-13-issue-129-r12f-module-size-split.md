# Issue #129 R12-F Module Size Split

## Goal

Continue shrinking the runtime module-size baseline without changing External Effect or Customer Read behavior.

## Implementation

1. Keep `external_effects.repo` as the stable facade and SQLAlchemy owner; move only the in-memory repository to a bounded module.
2. Keep `customer_read_model.repo` as the stable facade and SQLAlchemy owner; move fixture and live-source repositories to bounded modules.
3. Keep all Customer Read query classes and repository-builder patch seams on their original modules; move only Customer360 projection helpers.
4. Add facade identity contracts for every moved class/helper.
5. Remove the three split modules from the shrinking size baseline.

## Verification

- Runtime module-size guard reports four remaining allowlisted modules.
- Existing External Effect and Customer Read Model suites pass.
- Repository ownership, DB boundary, runtime inventory, and full architecture gates pass.
- The GitHub selector requires full PostgreSQL CI for the changed domains.
