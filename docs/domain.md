# YouAreUnstoppable — Domain

The rules the API will have to protect. Days, the journal, and the coach are specified and not built. Sign-in is live. This file does not list endpoints. The live contract is in [api.md](api.md).

The user-facing screens live in the frontend repo at `frontend/docs/experience.md`.

## The record

A user has one transformation.

A transformation has:

- An identity: the selected traits, plus the future-self statement
- A start date
- A sequence of days

A day has:

- A calendar date
- A day number counted from the start date
- A set of commitments
- A status
- An optional feeling from the evening check-in
- An optional journal note

The journey grid is a view of those days. It is not a separate stored object.

The fundamental unit is the day. Schema and API names use day, commitment, transformation, and journey.

## Accounts

A person has one user row and one subscription row. `subscriptions.user_id` references `users.id`. Signup creates the user, then the subscription.

The user stores email, an optional password hash, an optional Google subject, role (`user` or `admin`), last sign-in, and `deleted_at`. The subscription stores `user_id`, `plan` (`free` or `pro`), Stripe ids, status, period end, `deleted_at`, and `deleted_reason`.

New accounts are `role=user` and `plan=free`. This slice does not call Stripe, so Stripe ids stay null and `plan` stays `free`. A user with `deleted_at` set cannot sign in. Why those choices were made is in [auth-decisions.md](auth-decisions.md).

## Day status

| Status | Meaning |
| --- | --- |
| Empty | Nothing recorded |
| Started | At least one commitment is done, and the day is still open |
| Completed | The day was closed after the required commitments |
| Exceptional | A completed day that stood out. The prototype uses this as a stronger block. The exact rule can wait until insights exist. |

Completing the required commitments makes the day eligible to close. The evening check-in is what closes the day and appends the block to the journey. A missed day stays incomplete.

## Streaks

A streak is consecutive completed days.

Current streak and longest streak are derived from the day sequence. They are not fields a client edits. A missed day ends the current streak. The longest streak is the maximum run of completed days since the transformation started.

## Stats

Define these once so the Journey labels and later API fields match.

| Stat | Definition |
| --- | --- |
| Days completed | Count of days with status completed or exceptional |
| Current streak | Length of the latest run of completed days, ending today if today is completed, otherwise ending yesterday |
| Longest streak | Longest run of completed days |
| Commitments completed | Completed commitments divided by commitments that were on the plan, across the history in view |
| Days shown up | Days completed divided by days since the transformation started, including today |

The prototype displays fixed figures for the fictional user: 187 completed days, a 23-day current streak, a 41-day longest streak, 87% commitments completed, and 73% days shown up, starting March 18, 2026. Those numbers are mock data until the API exists. When the API exists, the same definitions produce the numbers.

## Journal

A journal entry belongs to a day. The timeline on the Journal screen is those notes in date order. Closing a day can store the check-in line ("Today I realized…") as that day's note.

## Coach

The coach reads the identity and recent days and returns a short insight plus the four actions:

- Plan tomorrow
- I'm procrastinating
- I'm losing motivation
- Review my progress

It is not a general chat log, and it is not the core record. The core record is the sequence of days.

## Free and Pro

Free stays genuinely useful:

- Define who you're becoming
- Daily commitments
- Daily completion
- Current streak
- Monthly journey grid
- Basic journal
- 7-day history
- Limited coaching

Pro, at $9.99 / month, adds:

- Full 365-day journey
- Unlimited history
- Personalized daily plans
- The full transformation coach
- Unlimited journal
- Weekly transformation reviews
- Advanced insights
- Multiple transformation areas
- Personalized challenges
- Custom commitments

Entitlement checks for Pro routes belong on the server when billing exists. Accounts exist now, and every new subscription is Free. Stripe is not connected yet, so the API does not move anyone to Pro.
