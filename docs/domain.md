# YouAreUnstoppable — Domain

The rules the API protects. Sign-in is live. The transformation record is live. This file does not list endpoints. The live contract is in [api.md](api.md).

There is no journal, no coach, and no evening check-in. Premium AI is not built. Free and a later Premium write the same tables. The product screens are in [product.md](product.md).

## The record

One user has one transformation.

A transformation is a copy of a path, not a pointer at the shared catalog. Free copies the catalog in when the user starts. A later AI can rewrite that same user's phases, objectives, and implementations. Closed days keep the text they were given when the day opened.

The user chooses one or two identities, and one direction for each identity. The catalog supplies the phases and the commitments. The client does not send phase names, frequencies, or commitment text.

Each path has four phases. A free phase is 14 show-up days. The length is stored on the phase, so a later path can use another length.

A day is a calendar date. It is open until the user shows up, then closed. A closed day is the block. The year is a view of those days. It is not a separate stored object.

## Commitments

A planned commitment has an objective and one or more implementations. The objective is the goal. The implementation is the action. Replace never changes the objective. Skip settles the current occurrence. It does not delete the schedule, and it does not count as done.

Each commitment has a recurrence: `daily`, `times_per_week`, `weekly`, or `monthly`. Frequency is how often. The schedule is when: weekdays for weekly and several-times-a-week commitments, or a day of the month from 1 to 28. The free catalog sets the frequency. The user can change the days. A several-times-a-week commitment must keep exactly that many weekdays. A weekly commitment keeps one.

The open day includes every current-phase commitment that is due on that date. A weekly commitment does not appear, and is not a miss, on the other days. Two identities keep their own due commitments.

The set is chosen when the day opens. Changing the schedule updates an open day: a newly due commitment is added, and an open commitment that is no longer due is removed. A closed day is not rewritten. The day stores a snapshot of the objective and the chosen title.

**I showed up** closes the day when every due commitment is done or skipped. Commitments that are not due do not block it. Closing the day advances every path.

## Promises kept

The product does not show a streak. `promises_kept` is the number of days the user has closed. A missed day does not reduce it. It is computed from closed days. It is not stored.

`commitment_streak` is still stored on the path. It increments when the day closes. It resets to 0 when a day opens after a gap, and when that path is replaced. It does not decide which commitments are due, and it is not shown. A new phase does not reset it. After the last day of a phase, the path moves to day 1 of the next phase. After the last phase, the path stays on that phase and is marked complete. Later days still offer that phase's commitments.

A missed calendar day does not consume a phase day.

Completion, misses, skips, and momentum stay computable from days and day commitments. They are not stored as their own fields.

## Changing the path

An unchanged identity and direction keep their phase day and unlock streak. A new or changed path is copied again at day 1 with an unlock streak of 0. If today is still open, its commitments are rebuilt from the current plan. Closed days stay.

Reset deletes the transformation, its paths, and its days. The account stays.

## Accounts

A person has one user row and one subscription row. `subscriptions.user_id` references `users.id`. Signup creates the user, then the subscription.

The user stores email, an optional password hash, an optional Google subject, role (`user` or `admin`), last sign-in, and `deleted_at`. The subscription stores `user_id`, `plan` (`free` or `pro`), Stripe ids, status, period end, `deleted_at`, and `deleted_reason`.

New accounts are `role=user` and `plan=free`. This slice does not call Stripe, so Stripe ids stay null and `plan` stays `free`. A user with `deleted_at` set cannot sign in. Why those choices were made is in [auth-decisions.md](auth-decisions.md).

## Origin

`transformations.origin` is `catalog` for a path copied from the catalog. The column also allows `adaptive`, for a path a later AI writes. `hybrid` is not a value yet. `rationale` and `context` are nullable and unused by the free routes. When a later recommendation replaces the reason, it must be appended, not overwritten. This slice stores a single `rationale` and does not add AI tables.

## Year intensity

The year is 1 January through 31 December of the client's year. A leap year includes 29 February. Each date is `0` to `2`. `intensity` counts the commitments that were due that day, across identities. A weekly or monthly commitment that was not due is not part of the day, so it cannot turn the day into a miss. `identities` uses the same scale for each identity on its own. A day that is still open counts too, so the current day changes as goals are checked.

| Intensity | Meaning |
| --- | --- |
| 0 | Nothing was completed. The day may be missing, still open, or closed with every commitment skipped |
| 1 | At least one commitment was completed, and at least one was not |
| 2 | Every commitment that day was completed |

`closed` is true when that calendar day was closed with "I showed up."

## Progress counts

Commitments done and commitments total count closed days only, and only occurrences that came due. A future weekly or monthly commitment is not incomplete. A skip is part of the total and is not done. The phase name, day, and next phase on the progress block come from the first selected identity.
