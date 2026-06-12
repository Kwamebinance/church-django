"""
QR generation for member attendance. Encodes the member_code (human-readable,
e.g. CEGWARI3-2026-00411) so it doubles as a typed fallback when scanning.
Renders as inline SVG (scales for print, no image storage needed).

Requires the `qrcode` package: pip install qrcode
"""
import io
import qrcode
import qrcode.image.svg


def member_qr_svg(member_code: str) -> str:
    """Return an inline SVG string encoding the given member_code."""
    if not member_code:
        return ""
    qr = qrcode.QRCode(
        version=None, error_correction=qrcode.constants.ERROR_CORRECT_M,
        box_size=10, border=2,
    )
    qr.add_data(member_code)
    qr.make(fit=True)
    img = qr.make_image(image_factory=qrcode.image.svg.SvgPathImage)
    buf = io.BytesIO()
    img.save(buf)
    return buf.getvalue().decode()
