# Authentication decisions

This slice adds sign-in. It does not call Stripe. Each section records the problem, the choice, why that choice was made, and what was left out.

## Auth only

Accounts have to exist before anyone can subscribe. Checkout, the billing portal, and webhooks are a later slice.

Sign-in is live. Billing routes are not. A new account is Free, and nothing in this code writes `pro` or creates a Stripe Customer.

Left out: Checkout, the Customer Portal, webhook handling, and `require_pro`.

## Google and email/password

People need a way to create an account and come back. Both Google and email/password were requested.

One `users` row can hold a password hash, a Google subject, or both. `POST /api/auth/password` lets a signed-in Google user set a password on that same row.

Left out: a second user record per sign-in method, and a way to replace a password that is already set.

## Link on a verified Google email

The same person may register with email and later use Google. Two rows for one email would split their subscription.

If the Google ID token has a verified email that matches an existing user, `google_sub` is stored on that user. If that user already has a different `google_sub`, the request is rejected.

Left out: linking when Google says the email is not verified, and merging two users who already have different Google subjects.

## Separate subscriptions table

Free and Pro will change over time. Putting Stripe fields on the user would mix identity with billing.

`subscriptions.user_id` references `users.id`, and that column is unique, so a person still has one subscription. Signup inserts the user, then the subscription, in one transaction. The subscription starts as `plan=free` with null Stripe ids. An earlier draft kept billing columns on the user, then pointed `users.subscription_id` at the subscription. This table replaces those drafts.

Left out: a subscription history table, and more than one subscription row per user.

## Role and plan

The app needs to tell an admin from a member, and Free from Pro. Those are different facts.

`users.role` is `user` or `admin`, and new accounts are `user`. `subscriptions.plan` is `free` or `pro`. This slice does not add admin routes, and it does not set `pro`.

Left out: inviting admins, and any route that checks `role`.

## Last connection

Support and the product need the last time someone actually signed in.

`last_connection` is set on register, email login, and Google sign-in.

Left out: updating it on token refresh. Refresh keeps a session alive. It is not a new sign-in.

## Soft delete

Closed accounts and ended subscriptions still need to stay in the database so the link between them is not destroyed.

`users.deleted_at` marks a closed account. `subscriptions.deleted_at` marks a closed subscription. `subscriptions.deleted_reason` is set only when `deleted_at` is set, and it stores why: canceled, payment failed, account closed, or a later admin action. Register, login, Google sign-in, refresh, and `GET /api/me` reject a user whose `deleted_at` is set. Email stays unique, including closed accounts, so the same address cannot register a second user.

Left out: a delete route. New rows keep both timestamps and `deleted_reason` null. A later slice will write them.

## No charge at signup

The subscription is optional and starts when the person chooses it.

Registration and Google sign-in never call Stripe. The new subscription row has null `stripe_customer_id`, null `stripe_subscription_id`, null `subscription_status`, and `plan=free`.

Left out: a trial, a card form, and any code that moves `plan` to `pro`.

## PostgreSQL, SQLAlchemy 2, and Alembic

The backend docs already named PostgreSQL as the database. The schema needs migrations.

Runtime configuration is `DATABASE_URL`. Models use SQLAlchemy 2. Alembic revision `20260923_0001` creates `subscriptions`, `users`, and `refresh_tokens`. Local setup does not use Docker. Tests run against SQLite so they do not need a Postgres server. Apply the migration to the real database with `alembic upgrade head`.

Left out: Docker Compose, and running Alembic inside the test suite.

## Argon2 password hashes

Passwords cannot be stored as plain text.

`password_hash` is an Argon2 hash from `pwdlib`. It is written when the user registers with a password or sets one later. Google-only users leave it null. Login with a missing hash is rejected as a bad password.

Left out: password reset. That needs an email provider, which this project does not have yet.

## Short-lived JWT and rotating refresh tokens

The browser needs a way to call `/api/me` without sending the password again, and a way to end that session.

The access token is a JWT signed with `JWT_SECRET`. It expires after 15 minutes and carries the user id. The refresh token is a random string. Only its SHA-256 hash is stored in `refresh_tokens`. Register, login, Google sign-in, and refresh set both values as HttpOnly cookies and do not put them in the JSON body. The access cookie is sent with API requests. The refresh cookie is limited to `/api/auth`. Refresh revokes the old token and sets a new pair. Logout revokes the refresh cookie when it is still valid and clears both cookies. `SameSite` is `Lax`. The cookies are `Secure` when `COOKIE_SECURE` is true.

Left out: a password-reset email, and a CSRF token. `SameSite=Lax` is the cross-site protection for this same-site PWA.

## Google ID token checked on the API

The future client is a web app. The API has to trust Google without running a browser redirect itself.

`POST /api/auth/google` accepts an ID token. The API verifies it against `GOOGLE_CLIENT_ID` and requires `email_verified`. `GOOGLE_CLIENT_SECRET` is not used.

Left out: the authorization-code redirect flow.

## GET /api/me returns the joined subscription

The client needs to know who is signed in and whether they are Free or Pro.

`GET /api/me` returns the user id, email, role, last connection, and the subscription id, plan, status, period end, `deleted_at`, and `deleted_reason`. Stripe customer and subscription ids stay in the database and are not part of this response.

Left out: `require_pro`, Stripe Checkout, and admin-only fields.
