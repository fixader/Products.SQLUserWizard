from Products.SQLUserWizard.qrcode import qrcode_svg_data_uri


def test_qrcode_svg_data_uri_contains_svg_image():
    uri = qrcode_svg_data_uri("otpauth://totp/SQL_User_Wizard:codex")

    assert uri.startswith("data:image/svg+xml;charset=utf-8,")
    assert "%3Csvg" in uri
