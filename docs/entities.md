# Database entities

The tables in PostgreSQL. Identities, directions, and the curated phases live in `src/domain/catalog.py`. They are not tables. Starting a transformation copies that catalog onto the user.

The calendar year, promises kept, and year intensity are computed when the transformation is read. They are not stored. The product does not show a streak.

## Account

```text
users 1──1 subscriptions
users 1──* refresh_tokens
users 1──1 transformations
```

### users

One person. `email` is unique. A Google-only account has `google_sub` and a null `password_hash`. `deleted_at` closes the account; a closed account cannot sign in.

| Column | Type | Notes |
| --- | --- | --- |
| id | uuid | Primary key |
| email | string(320) | Unique, required |
| password_hash | string(255) | Nullable |
| google_sub | string(255) | Unique, nullable |
| role | string | `user` or `admin`. Default `user` |
| last_connection | timestamptz | Nullable |
| created_at | timestamptz | |
| updated_at | timestamptz | |
| deleted_at | timestamptz | Nullable |

### subscriptions

One row per user. Signup creates it. This slice does not call Stripe, so the Stripe ids stay null and `plan` stays `free`.

| Column | Type | Notes |
| --- | --- | --- |
| id | uuid | Primary key |
| user_id | uuid | Unique, foreign key to `users.id` |
| plan | string | `free` or `pro`. Default `free` |
| subscription_status | string(32) | Nullable |
| stripe_customer_id | string(255) | Unique, nullable |
| stripe_subscription_id | string(255) | Unique, nullable |
| current_period_end | timestamptz | Nullable |
| deleted_at | timestamptz | Nullable |
| deleted_reason | text | Nullable. Allowed only when `deleted_at` is set |
| created_at | timestamptz | |
| updated_at | timestamptz | |

### refresh_tokens

Hashed session tokens. The raw token is only in the cookie.

| Column | Type | Notes |
| --- | --- | --- |
| id | uuid | Primary key |
| user_id | uuid | Foreign key to `users.id`, indexed |
| token_hash | string(64) | Unique |
| expires_at | timestamptz | |
| revoked | boolean | Default false |
| created_at | timestamptz | |

## Transformation

```text
transformations 1──* transformation_paths 1──* path_phases
path_phases 1──* planned_commitments 1──* planned_implementations
transformations 1──* days 1──* day_commitments
```

`day_commitments` also point at a path, a planned commitment, and an implementation. Those three foreign keys are nullable and use `ON DELETE SET NULL`, so a replaced path can disappear while the closed day keeps its snapshot text.

Deleting a transformation deletes its paths, phases, planned commitments, planned implementations, days, and day commitments.

### transformations

One per user. `origin` is `catalog` when the path was copied from the catalog. The column also allows `adaptive`, for a later AI that writes the same tables. `rationale` and `context` are unused by the free routes.

| Column | Type | Notes |
| --- | --- | --- |
| id | uuid | Primary key |
| user_id | uuid | Unique, foreign key to `users.id` |
| started_on | date | |
| origin | string | `catalog` or `adaptive`. Default `catalog` |
| rationale | text | Nullable |
| context | json | Nullable |
| created_at | timestamptz | |
| updated_at | timestamptz | |

### transformation_paths

One path per chosen identity. At most two identities. `identity_id` and `direction_id` are catalog slugs stored on the user. `commitment_streak` is the unlock streak for the extra commitment. The calendar streak is not stored here.

| Column | Type | Notes |
| --- | --- | --- |
| id | uuid | Primary key |
| transformation_id | uuid | Foreign key to `transformations.id`, cascade delete |
| identity_id | string(64) | Unique with `transformation_id` |
| direction_id | string(64) | |
| sort_order | integer | |
| current_phase_position | integer | Default 0. Must be ≥ 0 |
| day_in_phase | integer | Default 1. Must be ≥ 1 |
| commitment_streak | integer | Default 0. Must be ≥ 0 |
| completed | boolean | Default false |

### path_phases

The phases copied onto the path. Free phases are 14 days. `length_days` is stored here so a later path can use another length. `name` is the journey label, such as Foundation. `headline` is the phase title, such as Keep One Promise.

| Column | Type | Notes |
| --- | --- | --- |
| id | uuid | Primary key |
| path_id | uuid | Foreign key to `transformation_paths.id`, cascade delete |
| position | integer | Unique with `path_id` |
| name | string(120) | |
| headline | string(120) | |
| length_days | integer | Must be ≥ 1 |
| catalog_phase_id | string(160) | Nullable |

### planned_commitments

The goal is `objective`. The action is a planned implementation. `recurrence` says when that action is due: `daily`, `times_per_week`, `weekly`, or `monthly`. `weekdays` is the schedule for weekly and several-times-a-week commitments, with Monday as 0. `month_day` is the schedule for a monthly commitment, from 1 to 28. `times_per_week` is how many weekdays a several-times-a-week commitment must keep. `unlock_streak` remains on the row and is not what makes a commitment due.

| Column | Type | Notes |
| --- | --- | --- |
| id | uuid | Primary key |
| phase_id | uuid | Foreign key to `path_phases.id`, cascade delete |
| position | integer | Unique with `phase_id` |
| unlock_streak | integer | Must be ≥ 0. Not used to hide a commitment |
| objective | text | The goal. Replace does not change it |
| catalog_commitment_id | string(200) | Nullable |
| recurrence | string(32) | `daily`, `times_per_week`, `weekly`, or `monthly` |
| times_per_week | integer | Nullable. 1–7 when set |
| weekdays | json | List of weekday numbers, Monday = 0 |
| month_day | integer | Nullable. 1–28 when set |

### planned_implementations

Ways to complete one objective. Replace changes which row is chosen. It does not change `planned_commitments.objective`.

| Column | Type | Notes |
| --- | --- | --- |
| id | uuid | Primary key |
| commitment_id | uuid | Foreign key to `planned_commitments.id`, cascade delete |
| position | integer | Unique with `commitment_id` |
| title | text | |
| is_default | boolean | Default false |

### days

One calendar date for the transformation. The day is `open` until the user shows up, then `closed`.

| Column | Type | Notes |
| --- | --- | --- |
| id | uuid | Primary key |
| transformation_id | uuid | Foreign key to `transformations.id`, cascade delete |
| calendar_date | date | Unique with `transformation_id` |
| status | string | `open` or `closed`. Default `open` |
| closed_at | timestamptz | Nullable |

### day_commitments

What was asked on that day. `objective_snapshot` and `title_snapshot` are copied when the day opens and stay after the plan changes. `status` is `open`, `done`, or `skipped`.

| Column | Type | Notes |
| --- | --- | --- |
| id | uuid | Primary key |
| day_id | uuid | Foreign key to `days.id`, cascade delete |
| path_id | uuid | Nullable, foreign key to `transformation_paths.id`, set null on delete |
| planned_commitment_id | uuid | Nullable, foreign key to `planned_commitments.id`, set null on delete |
| implementation_id | uuid | Nullable, foreign key to `planned_implementations.id`, set null on delete |
| status | string | `open`, `done`, or `skipped`. Default `open` |
| objective_snapshot | text | |
| title_snapshot | text | |
