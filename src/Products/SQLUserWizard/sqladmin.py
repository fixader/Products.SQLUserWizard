from .config import DEFAULT_PASSWORD_HASH_ID
from .totp import generate_totp_secret
from .totp import normalize_totp_secret
from .password import encode_password


STANDARD_ZOPE_ROLES = (
    ("Manager", "Zope Manager"),
    ("Owner", "Zope Owner"),
    ("Authenticated", "Zope Authenticated"),
    ("Anonymous", "Zope Anonymous"),
)


def normalize_roles(raw_roles):
    """Return normalized role ids from strings or request list values."""

    if raw_roles is None:
        values = []
    elif isinstance(raw_roles, (list, tuple)):
        values = raw_roles
    else:
        values = str(raw_roles).replace("\n", ",").split(",")

    roles = []
    seen = set()
    for raw_part in values:
        for nested_part in str(raw_part).replace("\n", ",").split(","):
            role = nested_part.strip()
            if role and role not in seen:
                roles.append(role)
                seen.add(role)
    return roles


def split_roles(roles_text):
    """Backward-compatible alias used by older tests and wizard inputs."""

    return normalize_roles(roles_text)


def first_row(rows):
    for row in rows:
        return row
    return None


def save_sql_role(plugin, role_id, title="", enabled=True):
    """Create or update a role in the SQL role catalog."""

    if not role_id or not role_id.strip():
        raise ValueError("Role id is required")

    plugin.zsql_pas_upsert_role(
        role_id=role_id.strip(),
        title=title,
        enabled="1" if enabled else "",
    )


def seed_standard_roles(plugin):
    """Ensure the SQL role catalog contains the standard Zope role names."""

    for role_id, title in STANDARD_ZOPE_ROLES:
        save_sql_role(plugin, role_id, title=title, enabled=True)


def save_sql_profile(
    plugin,
    user_id,
    first_name="",
    last_name="",
    display_name="",
    email="",
    mobile="",
):
    """Create or update the editable profile fields for a SQL user."""

    if not user_id or not user_id.strip():
        raise ValueError("User id is required")

    plugin.zsql_pas_upsert_profile(
        user_id=user_id.strip(),
        first_name=first_name,
        last_name=last_name,
        display_name=display_name,
        email=email,
        mobile=mobile,
    )


def save_sql_user(
    plugin,
    user_id,
    login_name,
    password="",
    password_hash_id=DEFAULT_PASSWORD_HASH_ID,
    recovery_email="",
    first_name="",
    last_name="",
    display_name="",
    email="",
    mobile="",
    enabled=True,
    totp_required=False,
    totp_enabled=False,
    totp_secret="",
    generate_new_totp_secret=False,
    roles_text="",
    roles=None,
    save_profile=True,
):
    """Create or update a SQL user, profile, and role assignments."""

    existing = first_row(plugin.zsql_pas_get_user(user_id=user_id))
    enabled_value = "1" if enabled else ""
    password_hash_id = password_hash_id or DEFAULT_PASSWORD_HASH_ID
    if existing is None:
        if not password:
            raise ValueError("Password is required for a new user")
        stored_password, stored_hash_id = encode_password(password, password_hash_id)
        plugin.zsql_pas_upsert_user(
            user_id=user_id,
            login_name=login_name,
            password=stored_password,
            password_hash_id=stored_hash_id,
            recovery_email=recovery_email,
            enabled=enabled_value,
        )
    else:
        plugin.zsql_pas_update_user(
            user_id=user_id,
            login_name=login_name,
            recovery_email=recovery_email,
            enabled=enabled_value,
        )
        if password:
            stored_password, stored_hash_id = encode_password(password, password_hash_id)
            plugin.zsql_pas_update_password(
                user_id=user_id,
                password=stored_password,
                password_hash_id=stored_hash_id,
            )

    clean_totp_secret = normalize_totp_secret(totp_secret)
    if generate_new_totp_secret:
        clean_totp_secret = generate_totp_secret()
    update_2fa = getattr(plugin, "zsql_pas_update_2fa", None)
    if update_2fa is not None:
        update_2fa(
            user_id=user_id,
            totp_required="1" if totp_required else "",
            totp_enabled="1" if totp_enabled else "",
            totp_secret=clean_totp_secret,
        )

    if save_profile:
        save_sql_profile(
            plugin,
            user_id=user_id,
            first_name=first_name,
            last_name=last_name,
            display_name=display_name,
            email=email,
            mobile=mobile,
        )

    selected_roles = normalize_roles(roles if roles is not None else roles_text)
    plugin.zsql_pas_clear_roles(user_id=user_id)
    for role in selected_roles:
        save_sql_role(plugin, role)
        plugin.zsql_pas_assign_role(user_id=user_id, role=role)


def delete_sql_user(plugin, user_id):
    """Delete a SQL user, profile, and role assignments."""

    if not user_id or not user_id.strip():
        raise ValueError("User id is required")

    clean_user_id = user_id.strip()
    plugin.zsql_pas_clear_roles(user_id=clean_user_id)
    plugin.zsql_pas_delete_profile(user_id=clean_user_id)
    plugin.zsql_pas_delete_user(user_id=clean_user_id)
