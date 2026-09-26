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
return context.sql_user_provisioning.create_invitation(
    email=req.form.get("email", ""), roles={roles_literal}, REQUEST=req,
    expires_in=86400,
)
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
    user_id=req.form.get("user_id", ""),
    login_name=req.form.get("login_name", ""),
    password=req.form.get("password", ""),
    profile={
        "first_name": req.form.get("first_name", ""),
        "last_name": req.form.get("last_name", ""),
        "display_name": req.form.get("display_name", ""),
        "mobile": req.form.get("mobile", ""),
    },
    REQUEST=req,
)
return result
''', "SQLUSERWIZARD-MANAGED-INVITATION-COMPLETE", ("Anonymous",), (COMPLETER_ROLE,))

    _script(invitations, "form", "Accept invitation", '''# SQLUSERWIZARD-MANAGED-INVITATION-FORM
field = context.sql_user_provisioning.csrf_field(context.REQUEST)
context.REQUEST.RESPONSE.setHeader("Content-Type", "text/html; charset=utf-8")
return """<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Accept invitation</title><link rel="stylesheet" href="sql_wizard.css"></head>
<body class="sqluw-page sqluw-invitation-page"><main class="sqluw-form-shell"><section class="sqluw-form-card">
<h1>Accept invitation</h1><p class="intro">Create your account using the invitation token you received.</p>
<form method="post" action="complete_invitation">%s
<label class="form-field"><span>Invitation token</span><input name="token" autocomplete="off" required></label>
<label class="form-field"><span>User ID</span><input name="user_id" autocomplete="username" required></label>
<label class="form-field"><span>Login name</span><input name="login_name" autocomplete="username" required></label>
<label class="form-field"><span>Password</span><input name="password" type="password" autocomplete="new-password" required></label>
<label class="form-field"><span>First name</span><input name="first_name" autocomplete="given-name"></label>
<label class="form-field"><span>Last name</span><input name="last_name" autocomplete="family-name"></label>
<label class="form-field"><span>Display name</span><input name="display_name"></label>
<label class="form-field"><span>Mobile</span><input name="mobile" type="tel" autocomplete="tel"></label>
<div class="sqluw-form-actions"><button type="submit">Complete invitation</button></div></form>
</section></main></body></html>""" % field
''', "SQLUSERWIZARD-MANAGED-INVITATION-FORM", ("Anonymous",))
    _script(invitations, "create_form", "Create invitation", '''# SQLUSERWIZARD-MANAGED-INVITATION-CREATE-FORM
field = context.sql_user_provisioning.csrf_field(context.REQUEST)
context.REQUEST.RESPONSE.setHeader("Content-Type", "text/html; charset=utf-8")
return """<!doctype html><html><head><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Create invitation</title><link rel="stylesheet" href="sql_wizard.css"></head>
<body class="sqluw-page sqluw-invitation-page"><main class="sqluw-form-shell"><section class="sqluw-form-card">
<h1>Create invitation</h1><p class="intro">Create a one-time invitation for an ordinary application user.</p>
<form method="post" action="create_invitation">%s
<label class="form-field"><span>Email</span><input name="email" type="email" autocomplete="email" required></label>
<div class="sqluw-form-actions"><button type="submit">Create invitation</button></div></form>
</section></main></body></html>""" % field
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
<h2>Editing</h2><p>The forms may be branded and rearranged. Preserve POST actions, input names and generated CSRF fields.
Do not grant Manager proxy roles. The local <code>sql_wizard.css</code> shadows the parent stylesheet through Acquisition;
remove it to inherit the parent file, or edit it for invitation-specific branding.</p></article></main></body></html>'''
    _file(invitations, "README-invitations.html", "SQLUserWizard invitation notes",
          note, "text/html", ("Manager",), managed_title="SQLUserWizard invitation notes")
    return invitations
