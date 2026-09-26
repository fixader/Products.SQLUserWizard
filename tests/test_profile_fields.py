import json

import pytest

from Products.SQLUserWizard.profile_fields import collect_values
from Products.SQLUserWizard.profile_fields import dump_values
from Products.SQLUserWizard.profile_fields import load_values
from Products.SQLUserWizard.profile_fields import normalize_definition
from Products.SQLUserWizard.profile_fields import render_fields


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
