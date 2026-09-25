from Products.SQLUserWizard.wizard import SQLUserWizard










def test_wizard_preflight_catches_duplicate_table_names():
    wizard = SQLUserWizard()
    wizard.users_table = "pas_users"
    wizard.profiles_table = "pas_users"

    html = wizard._render_preflight()

    assert "Stop First" in html
    assert "Use distinct tables" in html


def test_wizard_screen_links_back_to_zmi_context():
    wizard = SQLUserWizard()

    html = wizard._render_form("")

    assert "Back to containing folder" in html
    assert 'href="../manage_workspace"' in html
    assert 'href="/manage_workspace"' in html
