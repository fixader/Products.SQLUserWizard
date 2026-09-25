"""Single-statement invitation writes for PostgreSQL, including autocommit DAs."""


def atomic_templates(tables, identity):
    invites, invite_roles = tables["invitations"], tables["roles"]
    users, profiles, roles, assignments = (identity[k] for k in ("users", "profiles", "roles", "user_roles"))

    def v(name, integer=False):
        return '<dtml-sqlvar %s type=%s>' % (name, "int" if integer else "string")

    fields = "invitation_id secret_hash email phone proposed_user_id proposed_login identity_reference creator_id created_at expires_at"
    create = f"""with created as (
insert into {invites} ({', '.join(fields.split())})
values ({', '.join(v(f, f.endswith('_at')) for f in fields.split())})
returning invitation_id
), assigned as (
insert into {invite_roles} (invitation_id, role_id)
select created.invitation_id, selected.role_id from created
cross join jsonb_array_elements_text(cast({v('roles_json')} as jsonb)) as selected(role_id)
returning invitation_id
)
select invitation_id from created"""
    # jsonb_exists avoids the '?' operator, which ODBC treats as a parameter.
    # SELECT FOR UPDATE locks the invitation. Do not UPDATE it twice in one
    # statement: PostgreSQL deliberately does not define that ordering.
    complete = f"""with eligible as (
select i.* from {invites} i
where i.secret_hash={v('secret_hash')}
and i.accepted_at is null and i.revoked_at is null and i.claim_nonce is null
and i.expires_at > extract(epoch from statement_timestamp())
and (coalesce(i.proposed_user_id, '')='' or i.proposed_user_id={v('user_id')})
and (coalesce(i.proposed_login, '')='' or i.proposed_login={v('login_name')})
and not exists (
    select 1 from {invite_roles} ir where ir.invitation_id=i.invitation_id
    and not jsonb_exists(cast({v('allowed_roles_json')} as jsonb), ir.role_id)
)
for update of i
), created as (
insert into {users} (user_id, username, password, password_hash_id, recovery_email,
                    enabled, totp_required, totp_enabled)
select {v('user_id')}, {v('login_name')}, {v('password')}, {v('password_hash_id')},
       email, true, ({v('totp_required', True)}=1), false from eligible
returning user_id
), profile_created as (
insert into {profiles} (user_id, first_name, last_name, display_name, email, mobile)
select created.user_id, {v('first_name')}, {v('last_name')}, {v('display_name')},
       eligible.email, {v('mobile')} from created cross join eligible
returning user_id
), catalog_created as (
insert into {roles} (role_id, title, enabled)
select ir.role_id, ir.role_id, true from {invite_roles} ir
join eligible e on e.invitation_id=ir.invitation_id
cross join created
on conflict (role_id) do nothing
returning role_id
), roles_created as (
insert into {assignments} (user_id, role_id)
select created.user_id, ir.role_id from created cross join eligible e
join {invite_roles} ir on ir.invitation_id=e.invitation_id
where (select count(*) from catalog_created)>=0
returning user_id
), consumed as (
update {invites} i
set accepted_at=extract(epoch from statement_timestamp()), result_user_id=created.user_id
from eligible e, created
where i.invitation_id=e.invitation_id
and (select count(*) from profile_created)=1
and (select count(*) from roles_created)>=0
returning i.result_user_id as user_id
)
select user_id from consumed"""
    return {
        "create_atomic": dict(id="zsql_invitation_create_atomic", title="Create invitation atomically",
                              arguments=fields + " roles_json", template=create),
        "complete_atomic": dict(id="zsql_invitation_complete_atomic", title="Complete invitation atomically",
                                arguments="secret_hash user_id login_name password password_hash_id allowed_roles_json totp_required first_name last_name display_name mobile",
                                template=complete),
    }
