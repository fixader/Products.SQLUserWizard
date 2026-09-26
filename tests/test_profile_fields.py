import json
from types import SimpleNamespace

import pytest

from Products.SQLUserWizard.admin import SQLUserAdmin
from Products.SQLUserWizard.profile_fields import collect_values
from Products.SQLUserWizard.profile_fields import dump_values
from Products.SQLUserWizard.profile_fields import load_values
from Products.SQLUserWizard.profile_fields import normalize_definition
from Products.SQLUserWizard.profile_fields import render_fields


class EditorRequest(dict):
    def __init__(self, **form):
        super().__init__(form)
        self.form = form
        self.RESPONSE = SimpleNamespace(
            setHeader=lambda *args, **kwargs: None,
            redirect=self._redirect,
        )
        self.redirected_to = ""

    def _redirect(self, url):
        self.redirected_to = url
        return url


def test_select_and_address_fields_are_validated_and_rendered():
    country = normalize_definition(
        "country", "Country", "select", required=True,
        options="NO|Norway\nSE|Sweden", default="NO",
    )
    address = normalize_definition("address_line_1", "Address line 1", required=True)
    html = render_fields((country, address), {"country": "SE", "address_line_1": "Main & 1st"})
    assert 'name="country"' in html
    assert '<option value="SE" selected>Sweden</option>' in html
    assert "Main &amp; 1st" in html


def test_only_configured_fields_are_collected():
    definitions = (
        normalize_definition("user_type", "User type", "select", options="customer|Customer\nstaff|Staff"),
        normalize_definition("city", "City"),
    )
    values = collect_values(definitions, {"user_type": "customer", "city": "Oslo", "is_manager": "1"})
    assert values == {"user_type": "customer", "city": "Oslo"}
    assert load_values(dump_values(values)) == values


def test_invalid_select_value_and_reserved_field_are_rejected():
    definition = normalize_definition("user_type", "User type", "select", options="customer|Customer")
    with pytest.raises(ValueError, match="invalid value"):
        collect_values((definition,), {"user_type": "Manager"})
    with pytest.raises(ValueError, match="reserved"):
        normalize_definition("email", "Other email")


def test_rendering_escapes_manager_controlled_labels_and_values():
    definition = normalize_definition("note", "<script>alert(1)</script>", "textarea")
    html = render_fields((definition,), {"note": "</textarea><script>bad()</script>"})
    assert "<script>" not in html
    assert "&lt;script&gt;" in html


def test_rendered_custom_fields_are_controls_for_the_shared_profile_fieldset():
    definition = normalize_definition("city", "City")

    html = render_fields((definition,), {"city": "Oslo"})

    assert '<input name="city" type="text" value="Oslo">' in html
    assert "Additional profile information" not in html
    assert "<fieldset" not in html


def test_admin_merges_custom_fields_into_the_existing_profile_fieldset():
    custom = render_fields((normalize_definition("city", "City"),), {"city": "Oslo"})
    rendered = "<fieldset><legend>Profile</legend><input name='first_name'></fieldset>"

    html = SQLUserAdmin._merge_profile_controls(rendered, custom)

    assert html.count("<fieldset") == 1
    assert html.index('name="city"') < html.index("</fieldset>")
    assert "Additional profile information" not in html


def test_profile_field_editor_uses_field_id_as_the_edit_link():
    admin = SQLUserAdmin()
    admin.profile_fields = (
        normalize_definition("address1", "Address line 1"),
    )

    html = admin._render_profile_field_editor("", {})

    assert "?field_id=address1#profile-field-editor" in html
    assert ">address1</a>" in html
    assert "Select a field ID to edit or remove" in html
    assert "<th>Actions</th>" not in html


def test_selected_profile_field_explains_what_can_be_changed():
    admin = SQLUserAdmin()
    definition = normalize_definition("address1", "Address line 1")

    html = admin._render_profile_field_editor("", definition)

    assert "The field ID is permanent" in html
    assert "Remove definition takes effect immediately" in html
    assert '<input name="field_id" value="address1" readonly required>' in html
    assert '<input name="label" value="Address line 1" required>' in html


def test_profile_field_save_renders_the_updated_value_without_a_redirect_race(monkeypatch):
    admin = SQLUserAdmin()
    admin.absolute_url = lambda: "http://zope.local/App/sql_user_admin"
    admin.profile_fields = (normalize_definition("address1", "Wrong label"),)
    monkeypatch.setattr("Products.SQLUserWizard.admin.require_post", lambda *args: None)
    monkeypatch.setattr("Products.SQLUserWizard.admin.protect_forms", lambda obj, request, html: html)
    request = EditorRequest(
        save_field="1", field_id="address1", label="Address line 1",
        field_type="text", sort_order="100", active="1",
    )

    html = admin.manage_profile_fields(request)

    assert admin.profile_fields[0]["label"] == "Address line 1"
    assert "Profile field saved" in html
    assert '<input name="label" value="Address line 1" required>' in html
    assert request.redirected_to == ""


def test_profile_field_remove_renders_the_updated_list_without_a_redirect_race(monkeypatch):
    admin = SQLUserAdmin()
    admin.absolute_url = lambda: "http://zope.local/App/sql_user_admin"
    admin.profile_fields = (normalize_definition("address1", "Address line 1"),)
    monkeypatch.setattr("Products.SQLUserWizard.admin.require_post", lambda *args: None)
    monkeypatch.setattr("Products.SQLUserWizard.admin.protect_forms", lambda obj, request, html: html)
    request = EditorRequest(delete_field="1", field_id="address1")

    html = admin.manage_profile_fields(request)

    assert admin.profile_fields == ()
    assert "Profile field removed from the profile forms" in html
    assert "No custom profile fields yet" in html
    assert "field_id=address1" not in html
    assert request.redirected_to == ""
