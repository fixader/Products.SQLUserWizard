import pytest

from Products.SQLUserWizard.sqladmin import (
    delete_sql_user,
    normalize_roles,
    save_sql_user,
    seed_standard_roles,
    split_roles,
)


def test_split_roles_accepts_commas_and_newlines():
    assert split_roles("Manager, Editor\nViewer") == [
        "Manager",
        "Editor",
        "Viewer",
    ]


def test_split_roles_removes_empty_values_and_duplicates():
    assert split_roles("Manager,, Manager, ") == ["Manager"]


def test_normalize_roles_accepts_request_lists():
    assert normalize_roles(["Manager", "Editor, Viewer"]) == [
        "Manager",
        "Editor",
        "Viewer",
    ]


class FakePlugin:
    def __init__(self):
        self.calls = []

    def zsql_pas_clear_roles(self, **kwargs):
        self.calls.append(("clear_roles", kwargs))

    def zsql_pas_delete_profile(self, **kwargs):
        self.calls.append(("delete_profile", kwargs))

    def zsql_pas_delete_user(self, **kwargs):
        self.calls.append(("delete_user", kwargs))


class FakeSavePlugin(FakePlugin):
    def __init__(self, existing=True):
        super().__init__()
        self.existing = existing

    def zsql_pas_get_user(self, **kwargs):
        if self.existing:
            return [object()]
        return []

    def zsql_pas_update_user(self, **kwargs):
        self.calls.append(("update_user", kwargs))

    def zsql_pas_upsert_user(self, **kwargs):
        self.calls.append(("upsert_user", kwargs))

    def zsql_pas_update_2fa(self, **kwargs):
        self.calls.append(("update_2fa", kwargs))

    def zsql_pas_upsert_role(self, **kwargs):
        self.calls.append(("upsert_role", kwargs))

    def zsql_pas_assign_role(self, **kwargs):
        self.calls.append(("assign_role", kwargs))

    def zsql_pas_upsert_profile(self, **kwargs):
        self.calls.append(("upsert_profile", kwargs))


def test_delete_sql_user_removes_roles_before_user():
    plugin = FakePlugin()

    delete_sql_user(plugin, " alice ")

    assert plugin.calls == [
        ("clear_roles", {"user_id": "alice"}),
        ("delete_profile", {"user_id": "alice"}),
        ("delete_user", {"user_id": "alice"}),
    ]


def test_delete_sql_user_requires_user_id():
    with pytest.raises(ValueError):
        delete_sql_user(FakePlugin(), "")


def test_save_sql_user_updates_2fa_settings():
    plugin = FakeSavePlugin()

    save_sql_user(
        plugin,
        user_id="alice",
        login_name="alice",
        totp_enabled=True,
        totp_secret="jbsw y3dp",
        roles=[],
        save_profile=False,
    )

    assert (
        "update_2fa",
        {
            "user_id": "alice",
            "totp_required": "",
            "totp_enabled": "1",
            "totp_secret": "JBSWY3DP",
        },
    ) in plugin.calls


def test_seed_standard_roles_adds_zope_role_catalog_rows():
    plugin = FakeSavePlugin()

    seed_standard_roles(plugin)

    assert ("upsert_role", {"role_id": "Manager", "title": "Zope Manager", "enabled": "1"}) in plugin.calls
    assert ("upsert_role", {"role_id": "Owner", "title": "Zope Owner", "enabled": "1"}) in plugin.calls
    assert (
        "upsert_role",
        {"role_id": "Authenticated", "title": "Zope Authenticated", "enabled": "1"},
    ) in plugin.calls
    assert (
        "upsert_role",
        {"role_id": "Anonymous", "title": "Zope Anonymous", "enabled": "1"},
    ) in plugin.calls
