"""Private invitation SQL contracts; application scripts use the controller."""

import re

from .dialects import normalize_managed_dialect


DEFAULT_INVITATION_TABLES = {
    "invitations": "pas_invitations",
    "roles": "pas_invitation_roles",
}


def validate_invitation_tables(tables, identity_tables):
    if set(tables) != set(DEFAULT_INVITATION_TABLES):
        raise ValueError("Provide invitation and invitation-role table names")
    names = list(tables.values())
    if any(not isinstance(name, str) or not re.fullmatch(r"[A-Za-z][A-Za-z0-9_]{0,29}", name)
           for name in names):
        raise ValueError("Invitation table names must be simple identifiers of 1-30 characters")
    names = [name.lower() for name in names + list(identity_tables.values())]
    if len(names) != len(set(names)):
        raise ValueError("Invitation tables must be distinct from all identity tables")


def invitation_templates(dialect, tables=None, identity_tables=None):
    dialect = normalize_managed_dialect(dialect)
    if dialect is None:
        raise ValueError("Unsupported invitation database dialect")
    tables = dict(DEFAULT_INVITATION_TABLES if tables is None else tables)
    validate_invitation_tables(tables, {})
    invitations, roles = tables["invitations"], tables["roles"]
    varchar = "varchar2" if dialect.startswith("oracle") else "varchar"
    epoch = "decimal(20,0)"

    def value(name, integer=False):
        return '<dtml-sqlvar %s type=%s>' % (name, "int" if integer else "string")

    specs = {}

    def add(name, arguments, sql):
        key = "zsql_invitation_" + name
        specs[name] = dict(id=key, title="Invitation " + name.replace("_", " "),
                           arguments=arguments, template=sql)

    # Intentionally no IF NOT EXISTS: ownership/collision checks precede DDL.
    add("setup", "", f"""create table {invitations} (
    invitation_id {varchar}(64) primary key,
    secret_hash {varchar}(64) unique not null,
    email {varchar}(255) not null,
    phone {varchar}(80),
    proposed_user_id {varchar}(80),
    proposed_login {varchar}(80),
    identity_reference {varchar}(255),
    creator_id {varchar}(255) not null,
    created_at {epoch} not null,
    expires_at {epoch} not null,
    accepted_at {epoch},
    revoked_at {epoch},
    result_user_id {varchar}(80),
    claim_nonce {varchar}(64),
    delivery_channel {varchar}(20),
    delivery_result {varchar}(20)
)""" + (" engine=InnoDB" if dialect == "mysql" else ""))
    add("setup_roles", "", f"""create table {roles} (
    invitation_id {varchar}(64) not null,
    role_id {varchar}(80) not null,
    primary key (invitation_id, role_id),
    foreign key (invitation_id) references {invitations}(invitation_id)
)""" + (" engine=InnoDB" if dialect == "mysql" else ""))

    fields = "invitation_id secret_hash email phone proposed_user_id proposed_login identity_reference creator_id created_at expires_at"
    add("create", fields, f"insert into {invitations} ({', '.join(fields.split())}) values (" +
        ", ".join(value(f, f.endswith("_at")) for f in fields.split()) + ")")
    add("add_role", "invitation_id role_id", f"insert into {roles} (invitation_id, role_id) values ({value('invitation_id')}, {value('role_id')})")
    add("roles", "invitation_id", f"select role_id from {roles} where invitation_id={value('invitation_id')} order by role_id")
    columns = ("invitation_id, email, phone, proposed_user_id, proposed_login, identity_reference, "
               "creator_id, created_at, expires_at, accepted_at, revoked_at, result_user_id, "
               "claim_nonce, delivery_channel, delivery_result")
    add("get_by_hash", "secret_hash", f"select {columns} from {invitations} where secret_hash={value('secret_hash')}")
    add("get", "invitation_id", f"select {columns} from {invitations} where invitation_id={value('invitation_id')}")
    listing = f"select {columns} from {invitations} order by created_at desc, invitation_id"
    if dialect == "mssql":
        listing = listing.replace("select ", "select top 100 ", 1)
    elif dialect == "oracle11g":
        listing = f"select * from ({listing}) where rownum <= 100"
    elif dialect == "oracle12c":
        listing += " fetch first 100 rows only"
    else:
        listing += " limit 100"
    add("list", "", listing)
    pending = f"accepted_at is null and revoked_at is null and expires_at > {value('now', True)}"
    add("claim", "secret_hash now claim_nonce", f"""update {invitations}
set claim_nonce={value('claim_nonce')}
where secret_hash={value('secret_hash')} and {pending} and claim_nonce is null""")
    add("consume", "invitation_id claim_nonce now user_id", f"""update {invitations}
set accepted_at={value('now', True)}, result_user_id={value('user_id')}
where invitation_id={value('invitation_id')} and claim_nonce={value('claim_nonce')} and {pending}""")
    add("rotate_secret", "invitation_id secret_hash now", f"""update {invitations}
set secret_hash={value('secret_hash')}, delivery_channel=null, delivery_result=null
where invitation_id={value('invitation_id')} and {pending} and claim_nonce is null""")
    add("revoke", "invitation_id now", f"""update {invitations}
set revoked_at={value('now', True)} where invitation_id={value('invitation_id')}
and accepted_at is null and revoked_at is null and claim_nonce is null""")
    add("record_delivery", "invitation_id delivery_channel delivery_result", f"""update {invitations}
set delivery_channel={value('delivery_channel')}, delivery_result={value('delivery_result')}
where invitation_id={value('invitation_id')}""")
    if identity_tables is not None:
        from .schema import validate_tables
        from .dialects import _sql_true
        validate_tables(identity_tables)
        # Unlike ordinary administration's upsert, completion must never update
        # an existing identity when another transaction wins a uniqueness race.
        add("insert_user", "user_id login_name password password_hash_id email", f"""insert into {identity_tables['users']}
(user_id, username, password, password_hash_id, recovery_email, enabled)
values ({value('user_id')}, {value('login_name')}, {value('password')},
{value('password_hash_id')}, {value('email')}, {_sql_true(dialect)})""")
        if dialect == "postgresql":
            from .invitation_postgresql import atomic_templates
            specs.update(atomic_templates(tables, identity_tables))
    return specs
