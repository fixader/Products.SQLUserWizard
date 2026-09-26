# SQLUserWizard 0.2.0b2

Release date: 2026-09-26. This beta refines the profile-field workflow introduced
in 0.2.0b1.

Built-in and application-configured fields now appear together in one
**Profile** section. The same ordered field set is used by SQL User Admin, the
self-service profile page, and the generated invitation acceptance form. The
built-in identity profile remains fixed, while Managers can add, edit,
deactivate, or remove application-specific definitions through the profile
field editor.

This release also fixes two persistence and workflow problems found during the
chapter lab review:

- saving or removing a field now renders the updated persistent state in the
  response, avoiding a stale view after the mutation;
- invitation acceptance collects the active configured fields and stores their
  validated values in the managed profile JSON within the same explicit
  database transaction as account creation.

The generated public invitation form receives only the narrow
`InvitationInspector` proxy role needed to render a valid token's profile
fields. Completion continues to use only `InvitationCompleter`. Neither script
has a `Manager` proxy role, and POST/CSRF, role allowlists, token replay
protection, ordinary login, and optional TOTP enrollment remain unchanged.

The complete local suite passes with 183 tests. The candidate was installed on
the Plone 6.2.2 / Zope 6.2 chapter lab. Its persistent invitation scripts were
repaired and compiled successfully, and the live SQL User Admin profile renders
one unified fieldset containing all three configured address fields.
