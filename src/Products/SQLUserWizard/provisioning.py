"""Narrow permission-checked API for application-owned invitation scripts."""

import hashlib
import hmac
import json
import re
import secrets
import time

import transaction
from AccessControl import ClassSecurityInfo, getSecurityManager
from Acquisition import aq_base, aq_parent
from BTrees.OOBTree import OOBTree
from OFS.SimpleItem import SimpleItem
from zExceptions import Forbidden, Unauthorized

from .compat import InitializeClass
from .config import DEFAULT_MANIFEST_ID, DEFAULT_PAS_ID
from .password import encode_password
from .security import csrf_field, require_post
from .sqladmin import first_row, save_sql_user


ADMINISTER = "SQLUserWizard: Administer invitations"
COMPLETE = "SQLUserWizard: Complete invitations"
INSPECT = "SQLUserWizard: Inspect invitations"
CONTROLLER_ID = "sql_user_provisioning"
FORBIDDEN_ROLES = frozenset(("Manager", "Owner", "Anonymous", "Authenticated"))


def text(value, name, limit, required=False):
    if not isinstance(value, str) or len(value) > limit or any(ord(c) < 32 for c in value):
        raise ValueError("Invalid " + name)
    value = value.strip()
    if required and not value:
        raise ValueError(name + " is required")
    return value


def ordinary_roles(roles, privileged=()):
    if not isinstance(roles, (tuple, list)) or len(roles) > 32:
        raise ValueError("Provide a list of ordinary roles")
    result = sorted(set(text(role, "role", 80, True) for role in roles))
    forbidden = {role.casefold() for role in FORBIDDEN_ROLES.union(privileged)}
    if any(role.casefold() in forbidden for role in result):
        raise ValueError("Invitations cannot grant privileged or pseudo-roles")
    return result


class SQLUserProvisioning(SimpleItem):
    """Methods are callable by authorized scripts, not HTTP traversal."""

    meta_type = "SQL User Provisioning"
    security = ClassSecurityInfo()
    security.declareObjectProtected(ADMINISTER)
    security.setPermissionDefault(ADMINISTER, ("Manager",))
    security.setPermissionDefault(COMPLETE, ("Manager",))
    security.setPermissionDefault(INSPECT, ("Manager",))

    def __init__(self, allowed_roles, privileged_roles=(), totp_required=False):
        self.id = CONTROLLER_ID
        self.allowed_roles = tuple(ordinary_roles(allowed_roles, privileged_roles))
        self.privileged_roles = tuple(privileged_roles)
        self.totp_required = bool(totp_required)
        self._attempts = OOBTree()

    def __bobo_traverse__(self, REQUEST, name):
        if name in ("create_invitation", "inspect_invitation", "list_invitations",
                    "rotate_invitation_secret", "revoke_invitation",
                    "complete_invitation", "record_delivery"):
            raise Forbidden("Use an authorized application script")
        return getattr(self, name)

    def _check(self, permission, request, mutate=True):
        if not getSecurityManager().checkPermission(permission, self):
            raise Unauthorized("Invitation permission required")
        if request is None:
            raise Forbidden("An application request is required")
        request.RESPONSE.setHeader("Cache-Control", "no-store")
        request.RESPONSE.setHeader("Referrer-Policy", "no-referrer")
        if mutate:
            require_post(self, request)

    def _plugin(self):
        folder = aq_parent(self)
        pas = folder._getOb(DEFAULT_PAS_ID)
        manifest = json.loads(pas._getOb(DEFAULT_MANIFEST_ID).read())
        feature = manifest.get("invitations", {})
        if feature.get("schema_revision") != 1:
            raise ValueError("Invitation storage is not enabled")
        if feature.get("connection_id") != manifest["connection_id"]:
            raise ValueError("Invitation connection has changed")
        return pas._getOb(manifest["plugin_id"])

    def _hash(self, token, request):
        # Throttle by caller address, not by attacker-selected token. Use the
        # direct publisher address; deployments must configure trusted proxies.
        now = int(time.time())
        key = hashlib.sha256(str(request.get("REMOTE_ADDR", "local")).encode()).hexdigest()
        for old, (until, count) in list(self._attempts.items()):
            if until <= now:
                del self._attempts[old]
        until, count = self._attempts.get(key, (now + 300, 0))
        if count >= 30 or len(self._attempts) >= 10000 and key not in self._attempts:
            raise ValueError("Too many invitation attempts")
        self._attempts[key] = (until, count + 1)
        if not isinstance(token, str) or not re.fullmatch(r"[A-Za-z0-9_-]{43}", token):
            raise ValueError("Invitation is invalid or unavailable")
        return hashlib.sha256(token.encode("ascii")).hexdigest()

    def _pending(self, row):
        return (row is not None and row.accepted_at is None and row.revoked_at is None
                and int(row.expires_at) > int(time.time()))

    def _summary(self, row):
        return {key: getattr(row, key) for key in (
            "invitation_id", "email", "phone", "proposed_user_id", "proposed_login",
            "identity_reference", "creator_id", "created_at", "expires_at",
            "accepted_at", "revoked_at", "result_user_id", "delivery_channel", "delivery_result")}

    security.declarePublic("csrf_field")
    def csrf_field(self, REQUEST):
        return csrf_field(self, REQUEST)

    security.declareProtected(ADMINISTER, "create_invitation")
    def create_invitation(self, email, roles, REQUEST, phone="", user_id="", login_name="",
                          identity_reference="", expires_in=86400):
        self._check(ADMINISTER, REQUEST)
        email = text(email, "email", 255, True).casefold()
        if not re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+", email):
            raise ValueError("Invalid email")
        roles = ordinary_roles(roles, self.privileged_roles)
        if not set(roles).issubset(self.allowed_roles):
            raise ValueError("Role is not approved for invitations")
        if type(expires_in) is not int or not 300 <= expires_in <= 604800:
            raise ValueError("Expiry must be 300-604800 seconds")
        now, invitation_id, token = int(time.time()), secrets.token_hex(16), secrets.token_urlsafe(32)
        values = dict(invitation_id=invitation_id, secret_hash=hashlib.sha256(token.encode()).hexdigest(),
                      email=email, phone=text(phone, "phone", 80),
                      proposed_user_id=text(user_id, "user id", 80),
                      proposed_login=text(login_name, "login", 80),
                      identity_reference=text(identity_reference, "identity reference", 255),
                      creator_id=getSecurityManager().getUser().getId() or "unknown",
                      created_at=now, expires_at=now + expires_in)
        plugin = self._plugin()
        try:
            plugin.zsql_invitation_create(**values)
            for role in roles:
                plugin.zsql_invitation_add_role(invitation_id=invitation_id, role_id=role)
        except Exception:
            transaction.doom()
            raise ValueError("Invitation creation failed") from None
        return dict(invitation_id=invitation_id, token=token, expires_at=now + expires_in)

    security.declareProtected(INSPECT, "inspect_invitation")
    def inspect_invitation(self, token, REQUEST):
        self._check(INSPECT, REQUEST, mutate=False)
        row = first_row(self._plugin().zsql_invitation_get_by_hash(secret_hash=self._hash(token, REQUEST)))
        if not self._pending(row) or row.claim_nonce:
            return dict(valid=False)
        return dict(valid=True, expires_at=int(row.expires_at),
                    proposed_login=row.proposed_login or "")

    security.declareProtected(ADMINISTER, "list_invitations")
    def list_invitations(self, REQUEST):
        self._check(ADMINISTER, REQUEST, mutate=False)
        return [self._summary(row) for row in self._plugin().zsql_invitation_list()]

    security.declareProtected(ADMINISTER, "rotate_invitation_secret")
    def rotate_invitation_secret(self, invitation_id, REQUEST):
        self._check(ADMINISTER, REQUEST)
        invitation_id = text(invitation_id, "invitation id", 64, True)
        token = secrets.token_urlsafe(32)
        digest = hashlib.sha256(token.encode()).hexdigest()
        plugin = self._plugin()
        plugin.zsql_invitation_rotate_secret(invitation_id=invitation_id, secret_hash=digest, now=int(time.time()))
        row = first_row(plugin.zsql_invitation_get_by_hash(secret_hash=digest))
        if row is None or row.invitation_id != invitation_id:
            raise ValueError("Invitation is invalid or unavailable")
        return dict(invitation_id=invitation_id, token=token)

    security.declareProtected(ADMINISTER, "revoke_invitation")
    def revoke_invitation(self, invitation_id, REQUEST):
        self._check(ADMINISTER, REQUEST)
        invitation_id = text(invitation_id, "invitation id", 64, True)
        plugin = self._plugin()
        plugin.zsql_invitation_revoke(invitation_id=invitation_id, now=int(time.time()))
        row = first_row(plugin.zsql_invitation_get(invitation_id=invitation_id))
        return dict(revoked=row is not None and row.revoked_at is not None)

    security.declareProtected(ADMINISTER, "record_delivery")
    def record_delivery(self, invitation_id, channel, result, REQUEST):
        self._check(ADMINISTER, REQUEST)
        if channel not in ("manual", "email") or result not in ("sent", "failed", "pending"):
            raise ValueError("Unsupported delivery status")
        self._plugin().zsql_invitation_record_delivery(
            invitation_id=text(invitation_id, "invitation id", 64, True),
            delivery_channel=channel, delivery_result=result)
        return dict(recorded=True)

    security.declareProtected(COMPLETE, "complete_invitation")
    def complete_invitation(self, token, user_id, login_name, password, profile, REQUEST):
        self._check(COMPLETE, REQUEST)
        digest = self._hash(token, REQUEST)
        user_id = text(user_id, "user id", 80, True)
        login_name = text(login_name, "login", 80, True)
        if not isinstance(password, str) or not 12 <= len(password) <= 1024:
            raise ValueError("Password must contain 12-1024 characters")
        if not isinstance(profile, dict) or set(profile) - {"first_name", "last_name", "display_name", "mobile"}:
            raise ValueError("Unsupported profile fields")
        profile = {k: text(v, k, 160 if k == "display_name" else 80) for k, v in profile.items()}
        plugin = self._plugin()
        row = first_row(plugin.zsql_invitation_get_by_hash(secret_hash=digest))
        if not self._pending(row) or row.claim_nonce:
            raise ValueError("Invitation is invalid or unavailable")
        if row.proposed_user_id and row.proposed_user_id != user_id or row.proposed_login and row.proposed_login != login_name:
            raise ValueError("Identity does not match invitation")
        # Require the actual connection to be registered in the current Zope
        # transaction. Autocommit/non-participating adapters cannot provision.
        method = plugin.zsql_invitation_get_by_hash
        connection = getattr(plugin, method.connection_id)()
        if not any(resource is connection or aq_base(resource) is aq_base(connection)
                   for resource in transaction.get()._resources):
            raise ValueError("Database adapter must participate in the Zope transaction")
        roles = ordinary_roles([r.role_id for r in plugin.zsql_invitation_roles(invitation_id=row.invitation_id)],
                               self.privileged_roles)
        if not set(roles).issubset(self.allowed_roles):
            raise ValueError("Invitation roles are no longer approved")
        pas = aq_parent(self)._getOb(DEFAULT_PAS_ID)
        if pas.getUserById(user_id) or pas.getUser(login_name):
            raise ValueError("Identity already exists")
        nonce, now = secrets.token_hex(32), int(time.time())
        try:
            plugin.zsql_invitation_claim(secret_hash=digest, now=now, claim_nonce=nonce)
            claimed = first_row(plugin.zsql_invitation_get_by_hash(secret_hash=digest))
            if claimed is None or not hmac.compare_digest(str(claimed.claim_nonce), nonce):
                raise ValueError("Invitation unavailable")
            stored, hash_id = encode_password(password)
            plugin.zsql_invitation_insert_user(user_id=user_id, login_name=login_name,
                                               password=stored, password_hash_id=hash_id, email=row.email)
            save_sql_user(plugin, user_id, login_name, recovery_email=row.email, email=row.email,
                          roles=roles, totp_required=self.totp_required, **profile)
            plugin.zsql_invitation_consume(invitation_id=row.invitation_id, claim_nonce=nonce,
                                           now=int(time.time()), user_id=user_id)
            completed = first_row(plugin.zsql_invitation_get(invitation_id=row.invitation_id))
            if completed.accepted_at is None or completed.result_user_id != user_id:
                raise ValueError("Invitation unavailable")
        except Exception:
            # Even if an application script catches this error, its transaction
            # cannot commit a partial identity. The publisher owns final commit.
            transaction.doom()
            raise ValueError("Invitation completion failed; no changes may be committed") from None
        return dict(user_id=user_id, login_name=login_name,
                    login_url=aq_parent(self).absolute_url() + "/sql_user_login_form")


InitializeClass(SQLUserProvisioning)
