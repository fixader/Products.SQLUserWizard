"""Install a usable, security-bounded invitation example application."""

from Acquisition import aq_base
from OFS.Image import File
from Products.PythonScripts.PythonScript import PythonScript

from .provisioning import ADMINISTER, COMPLETE, INSPECT, CONTROLLER_ID
from .styles import STYLESHEET_ID


FOLDER_ID = "invitations"
INSPECTOR_ROLE = "InvitationInspector"
COMPLETER_ROLE = "InvitationCompleter"


def _source(script):
    body = getattr(script, "body", None)
    return body() if callable(body) else ""


def _script(container, object_id, title, body, marker, view_roles, proxy_roles=()):
    existing = container._getOb(object_id, None)
    if existing is None:
        container._setObject(object_id, PythonScript(object_id))
        existing = container._getOb(object_id)
    elif not isinstance(aq_base(existing), PythonScript):
        raise ValueError(f"{FOLDER_ID}/{object_id} exists but is not a Script (Python)")
    source = _source(existing)
    if not source or marker in source:
        # Zope refuses to edit a Script (Python) while it carries a proxy role
        # the current Manager does not personally hold. Clear only the managed
        # script's proxy roles during replacement, then restore the reviewed
        # narrow role below. A failed request aborts the ZODB changes.
        existing.manage_proxy(())
        existing.ZPythonScript_edit("", body)
        existing.title = title
    existing.manage_permission("View", roles=tuple(view_roles), acquire=0)
    existing.manage_proxy(tuple(proxy_roles))
    return existing


def _file(container, object_id, title, data, content_type, view_roles, managed_title=None):
    encoded = data.encode("utf-8")
    existing = container._getOb(object_id, None)
    if existing is None:
        container._setObject(object_id, File(object_id, title, encoded, content_type=content_type))
        existing = container._getOb(object_id)
    elif getattr(existing, "meta_type", "") != "File":
        raise ValueError(f"{FOLDER_ID}/{object_id} exists but is not a File")
    elif managed_title is None or getattr(existing, "title", "") == managed_title:
        existing.update_data(encoded, content_type=content_type, size=len(encoded))
        existing.title = title
    existing.manage_permission("View", roles=tuple(view_roles), acquire=0)
    return existing


def _file_text(obj):
    data = aq_base(obj).data
    if isinstance(data, bytes):
        return data.decode("utf-8")
    if isinstance(data, str):
        return data
    chunks = []
    current = data
    while current is not None:
        chunks.append(bytes(current))
        current = current.next
    return b"".join(chunks).decode("utf-8")


def install_invitation_examples(application, allowed_roles):
    """Create or repair the application-owned invitation folder and wrappers."""
    invitations = application._getOb(FOLDER_ID, None)
    if invitations is None:
        application.manage_addFolder(FOLDER_ID, "Invitation examples")
        invitations = application._getOb(FOLDER_ID)
    elif getattr(invitations, "meta_type", "") != "Folder":
        raise ValueError("invitations exists but is not a Folder")

    for role in (INSPECTOR_ROLE, COMPLETER_ROLE):
        if role not in application.valid_roles():
            application._addRole(role)
    controller = application._getOb(CONTROLLER_ID)
    controller.manage_permission(ADMINISTER, roles=("Manager",), acquire=0)
    controller.manage_permission(INSPECT, roles=("Manager", INSPECTOR_ROLE), acquire=0)
    controller.manage_permission(COMPLETE, roles=("Manager", COMPLETER_ROLE), acquire=0)

    roles_literal = repr(list(allowed_roles))
    _script(invitations, "create_invitation", "Create invitation", f'''# SQLUSERWIZARD-MANAGED-INVITATION-CREATE
req = context.REQUEST
result = context.sql_user_provisioning.create_invitation(
    email=req.form.get("email", ""), roles={roles_literal}, REQUEST=req,
    expires_in=86400,
)
result["delivery"] = "manual"
delivery = context.sql_user_provisioning.deliver_invitation_email(
    result["invitation_id"], result["token"], req.form.get("email", ""), req)
result.update(delivery)
return result
''', "SQLUSERWIZARD-MANAGED-INVITATION-CREATE", ("Manager",))
    _script(invitations, "inspect_invitation", "Inspect invitation", '''# SQLUSERWIZARD-MANAGED-INVITATION-INSPECT
req = context.REQUEST
return context.sql_user_provisioning.inspect_invitation(
    token=req.form.get("token", ""), REQUEST=req,
)
''', "SQLUSERWIZARD-MANAGED-INVITATION-INSPECT", ("Anonymous",), (INSPECTOR_ROLE,))
    _script(invitations, "complete_invitation", "Complete invitation", '''# SQLUSERWIZARD-MANAGED-INVITATION-COMPLETE
req = context.REQUEST
result = context.sql_user_provisioning.complete_invitation(
    token=req.form.get("token", ""),
    user_id=req.form.get("login_name", ""),
    login_name=req.form.get("login_name", ""),
    password=req.form.get("password", ""),
    profile=context.sql_user_provisioning.invitation_profile_from_request(req),
    REQUEST=req,
)
req.RESPONSE.setHeader("Content-Type", "text/html; charset=utf-8")
return """<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Account created</title><link rel="stylesheet" href="sql_wizard.css"></head>
<body class="sqluw-page sqluw-invitation-page"><main class="sqluw-form-shell"><section class="sqluw-form-card">
<h1>Account created</h1>
<p>Your account is ready. For security, accepting an invitation does not sign you in automatically.</p>
<div class="sqluw-form-actions"><a class="button" href="%s">Continue to login</a></div>
</section></main></body></html>""" % result["login_url"]
''', "SQLUSERWIZARD-MANAGED-INVITATION-COMPLETE", ("Anonymous",), (COMPLETER_ROLE,))

    _script(invitations, "form", "Accept invitation", '''# SQLUSERWIZARD-MANAGED-INVITATION-FORM
field = context.sql_user_provisioning.csrf_field(context.REQUEST)
token = context.REQUEST.form.get("token", "")
profile_fields = context.sql_user_provisioning.render_invitation_profile_fields(token, context.REQUEST)
context.REQUEST.RESPONSE.setHeader("Content-Type", "text/html; charset=utf-8")
return """<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Accept invitation</title><link rel="stylesheet" href="sql_wizard.css"></head>
<body class="sqluw-page sqluw-invitation-page"><main class="sqluw-form-shell"><section class="sqluw-form-card">
<h1>Accept invitation</h1><p class="intro">Create your account using the invitation token you received.</p>
<form method="post" action="complete_invitation">%s
<label class="form-field"><span>Invitation token</span><input name="token" value="%s" autocomplete="off" title="The one-time token from your invitation email" required></label>
<label class="form-field"><span>Login name</span><input name="login_name" autocomplete="username" placeholder="For example: rf or rf@bina.no" title="Choose a nickname or use your email address" required>
<small>Choose a nickname, or simply use your email address. You will enter this when signing in.</small></label>
<label class="form-field"><span>Password</span><input name="password" type="password" autocomplete="new-password" placeholder="At least 12 characters" title="Use at least 12 characters" minlength="12" required>
<small>Use at least 12 characters.</small></label>
%s
<div class="sqluw-form-actions"><button type="submit">Complete invitation</button></div></form>
</section></main></body></html>""" % (field, token, profile_fields)
''', "SQLUSERWIZARD-MANAGED-INVITATION-FORM", ("Anonymous",), (INSPECTOR_ROLE,))
    _script(invitations, "create_form", "Create invitation", '''# SQLUSERWIZARD-MANAGED-INVITATION-CREATE-FORM
field = context.sql_user_provisioning.csrf_field(context.REQUEST)
mailhosts = context.objectValues("Mail Host")
mail_status = "<p class='notice'>No local MailHost is configured. The invitation token must be delivered manually.</p>"
if mailhosts and context.getProperty("sqluw_mail_enabled", False):
    mail_status = "<p class='notice'>The invitation will be sent automatically by the local MailHost.</p>"
elif mailhosts:
    mail_status = "<p class='notice'>The local MailHost is disabled for invitations. Deliver the token manually.</p>"
context.REQUEST.RESPONSE.setHeader("Content-Type", "text/html; charset=utf-8")
return """<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Create invitation</title><link rel="stylesheet" href="sql_wizard.css"></head>
<body class="sqluw-page sqluw-invitation-page"><main class="sqluw-form-shell"><section class="sqluw-form-card">
<h1>Create invitation</h1><p class="intro">Create a one-time invitation for an ordinary application user.</p>%s
<form method="post" action="create_invitation">%s
<label class="form-field"><span>Email</span><input name="email" type="email" autocomplete="email" required></label>
<div class="sqluw-form-actions"><button type="submit">Create invitation</button></div></form>
</section></main></body></html>""" % (mail_status, field)
''', "SQLUSERWIZARD-MANAGED-INVITATION-CREATE-FORM", ("Manager",))

    parent_css = _file_text(application._getOb(STYLESHEET_ID))
    invitation_css = '''\n/* SQLUSERWIZARD-MANAGED-INVITATION-CSS */
.sqluw-form-shell{max-width:820px;margin:0 auto;padding:2rem clamp(1rem,4vw,2.5rem)}
.sqluw-form-card{border:1px solid var(--sqluw-border);border-radius:.5rem;padding:1.25rem;background:var(--sqluw-surface)}
.sqluw-form-actions{display:flex;gap:.75rem;align-items:center;margin-top:1rem}
'''
    _file(invitations, STYLESHEET_ID, "SQLUserWizard invitation stylesheet",
          parent_css.rstrip() + invitation_css, "text/css", ("Anonymous",),
          managed_title="SQLUserWizard invitation stylesheet")

    note = '''<!doctype html><html><head><meta charset="utf-8"><title>Invitation notes</title>
<link rel="stylesheet" href="sql_wizard.css"></head><body class="sqluw-page"><main class="sqluw-editor-shell">
<article class="panel"><h1>Invitation customization notes</h1>
<p>This Manager-only page documents the generated invitation example.</p>
<h2>Expected behavior</h2><ol><li>A Manager creates a one-time invitation.</li>
<li>The recipient completes the public form.</li><li>Acceptance creates the account but does not log the browser in.</li>
<li>The user logs in normally and completes TOTP enrollment when required.</li>
<li>Used, expired, revoked, or replayed tokens are rejected.</li></ol>
<h2>Email delivery</h2><p>Add and configure a MailHost directly in this <code>invitations</code> folder to enable
automatic delivery from the creation form. Enable it and configure the sender, subject and public invitation URL through
SQL User Admin. Only local MailHost objects are considered; a MailHost acquired from a parent is deliberately ignored.
Without an enabled local MailHost, create the invitation and deliver its one-time token manually.</p>
<h2>Editing</h2><p>The forms may be branded and rearranged. Preserve POST actions, input names and generated CSRF fields.
Do not grant Manager proxy roles. The local <code>sql_wizard.css</code> shadows the parent stylesheet through Acquisition;
remove it to inherit the parent file, or edit it for invitation-specific branding.</p></article></main></body></html>'''
    _file(invitations, "README-invitations.html", "SQLUserWizard invitation notes",
          note, "text/html", ("Manager",), managed_title="SQLUserWizard invitation notes")
    return invitations
