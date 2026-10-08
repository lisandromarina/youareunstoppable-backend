# YouAreUnstoppable — Domain

The rules the API protects. Sign-in is live. The transformation record is live. This file does not list endpoints. The live contract is in [api.md](api.md).

There is no journal and no evening check-in. The coach is Pro-only and writes the same transformation tables. Free accounts keep the catalog path. The product screens are in [product.md](product.md). The coach's product rules are in [coach.md](coach.md).

## The record

One user has one transformation.

A transformation is a copy of a path, not a pointer at the shared catalog. Free copies the catalog in when the user starts. The coach rewrites the current phase's commitments on that same record. Closed days keep the text they were given when the day opened.

The user chooses one or two identities, and one direction for each identity. The catalog supplies the phases and the commitments. The client does not send phase names, frequencies, or commitment text.

Each path has four phases. A free phase is 14 show-up days. The length is stored on the phase, so a later path can use another length.

A day is a calendar date. It is open until the user shows up, then closed. A closed day is the block. The year is a view of those days. It is not a separate stored object.

## Commitments

A planned commitment has an objective and one or more implementations. The objective is the goal. The implementation is the action. Replace never changes the objective. Skip settles the current occurrence. It does not delete the schedule, and it does not count as done.

Each commitment has a recurrence: `daily`, `times_per_week`, `weekly`, `monthly`, or `once`. Frequency is how often. The schedule is when: weekdays for weekly and several-times-a-week commitments, a day of the month from 1 to 28, or `due_on` for a one-time goal. The free catalog sets the frequency. The user can change the days of a weekly, several-times-a-week, or monthly commitment. A several-times-a-week commitment must keep exactly that many weekdays. A weekly commitment keeps one. A one-time goal is due only on `due_on` and does not repeat after it is done or skipped. `reason` is an optional line under the action.

A catalog path starts with one active goal, the first commitment in catalog order. Later commitments stay hidden until they are earned. Each identity keeps its own count. An adaptive path does not use that count.

A progress day is a calendar day with at least one of that path's goals marked done. Skip does not count. Three progress days in a row add the next catalog goal, up to the last one on the path. The new goal is due starting the next day. One day with nothing done breaks that run and does not remove a goal. Two of those days in a row remove the most recently added goal. The count never drops below one.

The open day includes every active goal that is due on that date. A weekly goal does not appear, and is not a miss, on the other days.

The set is chosen when the day opens. Changing the schedule updates an open day: a newly due commitment is added, and an open commitment that is no longer due is removed. A closed day is not rewritten. The day stores a snapshot of the objective and the chosen title.

**I showed up** closes the day when every due commitment is done or skipped. Commitments that are not due do not block it. Closing the day advances every path.

## Promises kept

The product does not show a streak. `promises_kept` is the number of days the user has closed. A missed day does not reduce it. It is computed from closed days. It is not stored.

`commitment_streak` is stored on the path. It is not shown. Closing a day increments it once when that path completed at least one due goal. Skip does not count. Completing several goals still adds one. Closing a day where that path completed none sets it to 0. A path with nothing due keeps its streak. It also resets to 0 when a day opens after a gap, and when that path is replaced. Catalog scheduling does not read it. Adaptive scheduling does. A new phase does not reset it. After the last day of a phase, the path moves to day 1 of the next phase. After the last phase, the path stays on that phase and is marked complete. Phase position does not add or remove goals.

A missed calendar day does not consume a phase day. The read model exposes `prior_closed_on` so the client can recognize that gap, and `tomorrow` so a closed day can show the commitments due the next calendar day. Neither one erases promises already kept.

Completion, misses, skips, and momentum stay computable from days and day commitments. They are not stored as their own fields.

## Changing the path

An unchanged identity and direction keep their phase day and unlock streak. A new or changed path is copied again from the catalog at day 1 with an unlock streak of 0. Adaptive commitments leave with the dropped path. If no path is still coach-written, `origin` returns to `catalog`. If today is still open, its commitments are rebuilt from the current plan. Closed days stay.

Reset deletes the transformation, its paths, and its days. The account stays.

## Accounts

A person has one user row and one subscription row. `subscriptions.user_id` references `users.id`. Signup creates the user, then the subscription.

The user stores email, an optional password hash, an optional Google subject, role (`user` or `admin`), last sign-in, and `deleted_at`. The subscription stores `user_id`, `plan` (`free` or `pro`), Stripe ids, status, period end, `deleted_at`, and `deleted_reason`.

New accounts are `role=user` and `plan=free`. This slice does not call Stripe, so Stripe ids stay null and `plan` stays `free`. A user with `deleted_at` set cannot sign in. Why those choices were made is in [auth-decisions.md](auth-decisions.md).

## Origin

`transformations.origin` is `catalog` for a path copied from the catalog. Confirming a coach plan sets it to `adaptive`. `hybrid` is not a value. `rationale` is one text field. Confirming a plan appends the reason on a new line. It is not replaced.

`context` is one JSON object. The server keeps `idea`, `statement`, `constraints`, `preferences`, `skills`, `obligations`, `availability`, `transcript`, `proposal`, and `today_override`. Unknown keys are dropped. `obligations` are facts the user stated, such as work hours. They are not planned commitments. The transcript is the last eight turns. There is no message table, goal table, or pattern table.

When `context.statement` is set, it is the transformation statement. Otherwise the statement stays the identity sentence.

A path is adaptive when `origin` is `adaptive` and its current-phase commitments have no catalog id. Those days use the streak. Repeating goals that are calendar-due that day contribute `min(5, commitment_streak + 1)`, in position order. One-time goals are eligible on `due_on`. The day is capped at 5 across adaptive identities. Order is the quick win, then due one-time goals, then the other repeating goals. The quick win is not dropped to make room for a one-time goal. A one-time goal that does not fit, or an unfinished one whose date has passed, gets `due_on` moved to the next day. It is not a miss. Goals outside the prefix are not misses.

`context.today_override` replaces that selection for one date. It can show up to five existing goals even when the streak is short, or a shorter title for today. Tomorrow uses the streak again. Tomorrow and Coming up preview the streak this close would produce. If today is still open and at least one due goal is done, the preview adds one. A closed day uses the streak already stored. A miss previews the quick win. The preview does not rewrite closed days.

Catalog paths keep the three-day and two-day rule. The coach does not change that.

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
