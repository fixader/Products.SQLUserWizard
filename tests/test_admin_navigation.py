from types import SimpleNamespace
from urllib.parse import quote_plus

from Products.SQLUserWizard.admin import SQLUserAdmin


class FakeFolder:
    def absolute_url(self):
        return "http://zope.local/App"

    def absolute_url_path(self):
        return "/App"


def _admin():
    admin = SQLUserAdmin()
    admin.aq_parent = FakeFolder()
    return admin


def _user():
    return SimpleNamespace(
        user_id="alice",
        login_name="alice",
        first_name="",
        last_name="",
        display_name="Alice",
        email="",
        mobile="",
        totp_enabled=False,
        totp_required=True,
        totp_secret="JBSWY3DPEHPK3PXP",
    )


def test_profile_page_offers_return_to_app_when_came_from_is_local():
    came_from = "http://zope.local/App/private_page"
    html = _admin()._render_profile_page(_user(), "", {"came_from": came_from})

    assert f'href="{came_from}">Back to app</a>' in html
    assert f'name="came_from" value="{came_from}"' in html
    assert f'my_2fa?came_from={quote_plus(came_from)}' in html


def test_profile_page_rejects_external_came_from():
    html = _admin()._render_profile_page(
        _user(),
        "",
        {"came_from": "https://not-our-site.example/private_page"},
    )

    assert "Back to app" not in html
    assert "not-our-site" not in html


def test_twofa_page_preserves_return_to_app_in_form_and_profile_link():
    came_from = "/App/private_page"
    html = _admin()._render_2fa_page(_user(), "", {"came_from": came_from})

    assert f'href="{came_from}">Back to app</a>' in html
    assert f'name="came_from" value="{came_from}"' in html
    assert f'my_profile?came_from={quote_plus(came_from)}' in html


def test_admin_page_can_take_return_target_from_first_referer():
    admin = _admin()

    came_from = admin._admin_came_from(
        {"HTTP_REFERER": "http://zope.local/App/manage_workspace"}
    )

    assert came_from == "http://zope.local/App/manage_workspace"


def test_admin_user_links_preserve_return_target():
    came_from = "http://zope.local/App/manage_workspace"
    html = _admin()._render_users_table([_user()], came_from)

    assert "user_id=alice" in html
    assert f"came_from={quote_plus(came_from)}" in html


def test_admin_forms_preserve_return_target():
    came_from = "/App/manage_workspace"
    admin = _admin()

    assert f'name="came_from" value="{came_from}"' in admin._render_role_form(came_from)
    assert f'name="came_from" value="{came_from}"' in admin._render_user_form(
        None,
        [],
        [],
        came_from=came_from,
    )


def test_admin_page_rejects_external_referer():
    came_from = _admin()._admin_came_from(
        {"HTTP_REFERER": "https://not-our-site.example/manage_workspace"}
    )

    assert came_from == ""


def test_admin_return_link_is_before_heading():
    admin = _admin()
    admin._plugin = lambda: SimpleNamespace(
        zsql_pas_list_users=lambda: [],
        zsql_pas_list_roles=lambda: [],
    )
    html = admin._render("", "", {"came_from": "/App/manage_workspace"})

    assert html.index("Back to app") < html.index("<h1>SQL User Admin</h1>")
