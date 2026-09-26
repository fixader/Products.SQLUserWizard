"""Explicit, opt-in invitation storage installation; never called at startup."""

import json

from AccessControl import getSecurityManager
from AccessControl.Permissions import manage_users
from Acquisition import aq_base
from zExceptions import Unauthorized

from .config import DEFAULT_MANIFEST_ID, DEFAULT_PAS_ID
from .installer import SQLUserWizardInstaller
from .invitation_sql import DEFAULT_INVITATION_TABLES, invitation_templates, validate_invitation_tables
from .schema import _existing_names, check_installation


def enable_invitation_storage(folder, tables=None, allowed_roles=("Member",),
                              privileged_roles=(), totp_required=False):
    """Manager-only explicit schema operation, separate from normal repair."""
    if not getSecurityManager().checkPermission(manage_users, folder):
        raise Unauthorized("Manage users permission is required")
    from .provisioning import CONTROLLER_ID, SQLUserProvisioning, ordinary_roles
    allowed_roles = ordinary_roles(allowed_roles, privileged_roles)
    reader = SQLUserWizardInstaller(folder, "unused")
    pas = reader._local_object(folder, DEFAULT_PAS_ID)
    manifest = reader._local_object(pas, DEFAULT_MANIFEST_ID) if pas is not None else None
    if manifest is None:
        raise ValueError("A completed managed SQLUserWizard installation is required")
    data = json.loads(reader._object_source(manifest))
    if data.get("product") != "Products.SQLUserWizard" or data.get("mode") != "managed":
        raise ValueError("Invitations require a managed SQLUserWizard installation")
    installer = SQLUserWizardInstaller(folder, data["connection_id"],
                                       dialect=data["sql_dialect"], tables=data["tables"],
                                       plugin_id=data["plugin_id"])
    # Existing customized/legacy identity SQL needs explicit review before adding
    # provisioning; do not infer the actual database contract from stale metadata.
    check_installation(installer)
    tables = dict(DEFAULT_INVITATION_TABLES if tables is None else tables)
    validate_invitation_tables(tables, data["tables"])
    plugin = installer._local_object(pas, data["plugin_id"])
    specs = invitation_templates(data["sql_dialect"], tables, data["tables"])
    recorded = data.get("invitations")
    controller = installer._local_object(folder, CONTROLLER_ID)
    if controller is not None and (recorded is None or not isinstance(controller, SQLUserProvisioning)):
        raise ValueError("Provisioning controller id is already in use")
    if controller is not None and (controller.allowed_roles != tuple(allowed_roles)
            or controller.privileged_roles != tuple(privileged_roles)
            or controller.totp_required != bool(totp_required)):
        raise ValueError("Invitation repair cannot silently change enrollment policy")
    if recorded is not None:
        if (recorded.get("schema_revision") != 1 or recorded.get("tables") != tables
                or recorded.get("connection_id") != data["connection_id"]
                or recorded.get("dialect") != data["sql_dialect"]):
            raise ValueError("Invitation repair must preserve recorded storage settings")
        for spec in specs.values():
            method = installer._local_object(plugin, spec["id"])
            if method is not None and (getattr(method, "src", None) != spec["template"]
                    or getattr(method, "arguments_src", None) != spec["arguments"]
                    or getattr(method, "connection_id", None) != installer.connection_id):
                raise ValueError("Customized invitation SQL requires manual review")
    else:
        collisions = {name.lower() for name in tables.values()} & _existing_names(installer)
        if collisions:
            raise ValueError("Invitation tables already exist without ownership: " + ", ".join(sorted(collisions)))
        if any(installer._local_object(plugin, spec["id"]) is not None for spec in specs.values()):
            raise ValueError("Unrecorded invitation methods require manual review")
    # Finish all preflight checks before editing methods or issuing DDL.
    for spec in specs.values():
        installer._upsert_zsql_method(plugin, spec)
        method = installer._local_object(plugin, spec["id"])
        method.manage_advanced(max_rows=1000, max_cache=0, cache_time=0,
                               class_name="", class_file="")
    if recorded is None:
        plugin.zsql_invitation_setup()
        plugin.zsql_invitation_setup_roles()
    data["invitations"] = dict(schema_revision=1, tables=tables,
                                connection_id=data["connection_id"], dialect=data["sql_dialect"])
    manifest.manage_edit(title=manifest.title, data=json.dumps(data, indent=2, sort_keys=True))
    if controller is None:
        folder._setObject(CONTROLLER_ID, SQLUserProvisioning(allowed_roles, privileged_roles, totp_required))
    from .invitation_examples import install_invitation_examples
    install_invitation_examples(folder, allowed_roles)
    return dict(schema_revision=1, tables=dict(tables), examples_path="invitations")
