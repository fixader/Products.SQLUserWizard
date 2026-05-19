from io import BytesIO
from urllib.parse import quote


def qrcode_svg_data_uri(text, scale=4, border=2):
    """Return a data URI containing an SVG QR code for ``text``."""

    import segno

    out = BytesIO()
    code = segno.make(text, error="m")
    code.save(out, kind="svg", scale=scale, border=border, xmldecl=False)
    svg = out.getvalue().decode("utf-8")
    return "data:image/svg+xml;charset=utf-8," + quote(svg)
