import sqlite3
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier

import pytest
from Shared.DC.ZRDB.DA import nvSQL as SQL

from Products.SQLUserWizard.config import DEFAULT_TABLES
from Products.SQLUserWizard.invitation_sql import (
    DEFAULT_INVITATION_TABLES, invitation_templates, validate_invitation_tables,
)


def render(spec, **kw):
    return SQL(spec["template"])(sql_quote__=lambda s: "'" + s.replace("'", "''") + "'", **kw)


@pytest.mark.parametrize("dialect", ["postgresql", "sqlite", "mysql", "mssql", "oracle11g", "oracle12c"])
def test_invitation_contract_renders_all_dialects(dialect):
    values = dict(invitation_id="id", secret_hash="a" * 64, email="o'hara@example.invalid",
                  phone="", proposed_user_id="", proposed_login="", identity_reference="",
                  creator_id="manager", created_at=1, expires_at=100, now=2,
                  role_id="Member", claim_nonce="b" * 64, user_id="new-user",
                  delivery_channel="manual", delivery_result="sent")
    specs = invitation_templates(dialect)
    for spec in specs.values():
        assert "<dtml" not in render(spec, **values)
    assert "o''hara@example.invalid" in render(specs["create"], **values)
    assert "foreign key" in specs["setup_roles"]["template"]
    assert "secret_hash" not in specs["list"]["template"]


def test_invitation_names_cannot_collide_or_inject_sql():
    validate_invitation_tables(DEFAULT_INVITATION_TABLES, DEFAULT_TABLES)
    for name in ("pas_users", "pas_invitation_roles", "schema.invites", "x; drop table users", "a" * 31):
        with pytest.raises(ValueError):
            validate_invitation_tables(dict(DEFAULT_INVITATION_TABLES, invitations=name), DEFAULT_TABLES)


def test_sqlite_invitation_claim_rotation_revoke_and_rollback():
    db = sqlite3.connect(":memory:")
    specs = invitation_templates("sqlite")

    def run(name, **kw):
        return db.execute(render(specs[name], **kw))

    try:
        run("setup")
        run("setup_roles")
        run("create", invitation_id="id", secret_hash="hash", email="user@example.invalid",
            phone="", proposed_user_id="", proposed_login="", identity_reference="",
            creator_id="manager", created_at=1, expires_at=100)
        run("add_role", invitation_id="id", role_id="Member")
        db.commit()
        assert run("claim", secret_hash="hash", now=2, claim_nonce="one").rowcount == 1
        assert run("claim", secret_hash="hash", now=2, claim_nonce="two").rowcount == 0
        assert run("rotate_secret", invitation_id="id", secret_hash="new", now=2).rowcount == 0
        assert run("consume", invitation_id="id", claim_nonce="two", now=2, user_id="u").rowcount == 0
        assert run("consume", invitation_id="id", claim_nonce="one", now=2, user_id="u").rowcount == 1
        db.rollback()
        assert run("rotate_secret", invitation_id="id", secret_hash="new", now=2).rowcount == 1
        assert run("claim", secret_hash="hash", now=2, claim_nonce="old").rowcount == 0
        assert run("claim", secret_hash="new", now=100, claim_nonce="expired").rowcount == 0
        assert run("revoke", invitation_id="id", now=2).rowcount == 1
        assert run("claim", secret_hash="new", now=3, claim_nonce="revoked").rowcount == 0
    finally:
        db.close()


def test_concurrent_sqlite_completions_have_exactly_one_claim(tmp_path):
    database = str(tmp_path / "invitations.db")
    specs = invitation_templates("sqlite")
    with sqlite3.connect(database) as db:
        db.execute(render(specs["setup"]))
        db.execute(render(specs["create"], invitation_id="id", secret_hash="hash",
                          email="user@example.invalid", phone="", proposed_user_id="",
                          proposed_login="", identity_reference="", creator_id="manager",
                          created_at=1, expires_at=100))
    start = Barrier(2)

    def complete(nonce):
        connection = sqlite3.connect(database, timeout=10)
        try:
            start.wait(timeout=10)
            with connection:
                changed = connection.execute(render(specs["claim"], secret_hash="hash", now=2,
                                                     claim_nonce=nonce)).rowcount
                if changed:
                    connection.execute(render(specs["consume"], invitation_id="id", now=2,
                                              claim_nonce=nonce, user_id=nonce))
                return changed
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(complete, ("first", "second")))
    assert sorted(results) == [0, 1]
