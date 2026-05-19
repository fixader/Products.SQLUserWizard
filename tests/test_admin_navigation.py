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
