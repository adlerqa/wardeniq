# PRD: Self-Service Password Reset

## Summary

Registered users who forget their password can reset it themselves by email,
without contacting support. This is the standard "forgot password" flow: request
a reset link, receive it by email, follow it to a reset form, and sign in with the
new password.

## Goals

- Let a user regain access to their account without a support ticket.
- Never reveal whether a given email address has an account (prevents account
  enumeration).
- Expire reset links quickly and rate-limit requests to reduce abuse.

## Out of scope

- Account recovery via SMS or security questions.
- Changing a password while already signed in (that's a separate, authenticated
  "Change password" flow).

## Functional requirements

- **FR-1**: On the sign-in screen, a "Forgot password?" link takes the user to a
  password reset request form.
- **FR-2**: The reset request form accepts an email address and, on submit, sends
  a password reset email to that address if an account with that email exists.
- **FR-3**: The response to a reset request is identical regardless of whether the
  email address is registered ("If an account exists for that address, we've sent
  a reset link.") — the system must not reveal account existence.
- **FR-4**: The reset email contains a single-use link containing a reset token.
  Following the link opens a "Set a new password" form.
- **FR-5**: The new password must be at least 12 characters and contain at least
  one letter and one number.
- **FR-6**: Submitting a valid new password on the reset form invalidates the
  reset token, updates the stored password, and signs the user out of all other
  active sessions.
- **FR-7**: After a successful reset, the user is redirected to the sign-in screen
  with a confirmation message and can immediately sign in with the new password.

## API surface

- `POST /api/auth/request-password-reset`
  - Body: `{ "email": string }`
  - Always returns `200 OK` with a generic confirmation message (see FR-3),
    regardless of whether the email is registered.
  - Rate limited per email address (see NFR-2).
- `POST /api/auth/reset-password`
  - Body: `{ "token": string, "new_password": string }`
  - Returns `200 OK` and invalidates the token on success.
  - Returns `400 Bad Request` if the token is invalid, expired, or already used.
  - Returns `422 Unprocessable Entity` if the new password fails the complexity
    rule in FR-5.

## UI

- **Sign-in screen**: add a "Forgot password?" link below the password field.
- **Request reset form**: a single email field and a "Send reset link" button.
  After submit, replace the form with the generic confirmation message from FR-3.
- **Reset password form** (reached via the emailed link): "New password" and
  "Confirm new password" fields, a password-strength hint showing the FR-5 rule,
  and a "Reset password" button. Disabled until both fields match and satisfy
  FR-5.
- **Expired/invalid link state**: if the token is invalid or expired, show
  "This reset link is no longer valid" with a link back to the request form,
  instead of a raw error.

## Non-functional requirements

- **NFR-1**: A reset token expires 30 minutes after it is issued.
- **NFR-2**: A single email address may not request more than 4 password resets
  within a 30-minute window; further requests in that window return the same
  generic confirmation message from FR-3 without sending another email.
- **NFR-3**: Reset tokens are single-use — following the same link twice must not
  reset the password twice, and the second attempt must show the expired/invalid
  state.
- **NFR-4**: Password reset requests and completions are written to the audit log
  (email address, timestamp, success/failure), without logging the token or the
  new password value itself.

## Open questions

- Should a successful reset also send a "your password was changed" confirmation
  email, separate from the reset link itself, as an extra signal to the account
  owner? Not required for v1; worth revisiting.
