"""
Birthday card image composition (Pillow). Composes:
  background image + member photo (positioned, optionally circular) + name + message

Positions/sizes come from the template's net-new config. Fonts are bundled in
static/fonts/ so this works regardless of system fonts (Windows / on-prem).

Returns a PNG as bytes. Never raises on a missing member photo — it composites
text only in that case.
"""
import os
from io import BytesIO

from django.conf import settings
from PIL import Image, ImageDraw, ImageFont, ImageOps

# Fonts are bundled INSIDE this app (birthdays/fonts/) and located relative to
# THIS module file — so resolution never depends on BASE_DIR, the working
# directory, static collection, or the OS. This is the one path guaranteed
# correct wherever the app is installed.
_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_FONT_DIR = os.path.join(_APP_DIR, "fonts")

# Bundled font families (all OFL-licensed, license files ship alongside).
# key -> (regular filename, bold filename). Bold falls back to regular if a
# family has a single weight (e.g. the script font).
FONT_FAMILIES = {
    "default": ("DejaVuSans.ttf", "DejaVuSans-Bold.ttf"),
    "sans": ("WorkSans-Regular.ttf", "WorkSans-Bold.ttf"),
    "serif": ("Lora-Regular.ttf", "Lora-Bold.ttf"),
    "script": ("NothingYouCouldDo-Regular.ttf", "NothingYouCouldDo-Regular.ttf"),
    "display": ("BigShoulders-Regular.ttf", "BigShoulders-Bold.ttf"),
    "rounded": ("Outfit-Regular.ttf", "Outfit-Bold.ttf"),
}

# Human labels for the picker.
FONT_LABELS = [
    ("default", "Default (DejaVu Sans)"),
    ("sans", "Clean Sans (Work Sans)"),
    ("serif", "Elegant Serif (Lora)"),
    ("script", "Handwriting (Nothing You Could Do)"),
    ("display", "Bold Display (Big Shoulders)"),
    ("rounded", "Rounded Friendly (Outfit)"),
]


def _read_font_file(fname):
    try:
        with open(os.path.join(_FONT_DIR, fname), "rb") as fh:
            return fh.read()
    except OSError:
        return None


# Pre-load all family bytes once at import (path-independent at render time).
_FAMILY_BYTES = {}
for _key, (_reg, _bold) in FONT_FAMILIES.items():
    _FAMILY_BYTES[(_key, False)] = _read_font_file(_reg)
    _FAMILY_BYTES[(_key, True)] = _read_font_file(_bold)

# Back-compat: the old _FONT_BYTES keyed by bold-only (used by diagnose()).
_FONT_BYTES = {
    True: _FAMILY_BYTES.get(("default", True)),
    False: _FAMILY_BYTES.get(("default", False)),
}

_SYSTEM_FALLBACKS = {
    True: ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
           r"C:\Windows\Fonts\arialbd.ttf", r"C:\Windows\Fonts\segoeuib.ttf"],
    False: ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            r"C:\Windows\Fonts\arial.ttf", r"C:\Windows\Fonts\segoeui.ttf"],
}


def _font(bold, size, family="default"):
    size = max(8, int(size))
    family = family if family in FONT_FAMILIES else "default"
    # 1) requested family bytes (bold, then regular of same family)
    data = (_FAMILY_BYTES.get((family, bold))
            or _FAMILY_BYTES.get((family, not bold))
            or _FAMILY_BYTES.get(("default", bold))
            or _FAMILY_BYTES.get(("default", not bold)))
    if data:
        try:
            return ImageFont.truetype(BytesIO(data), size)
        except OSError:
            pass
    # 2) system fallbacks (never the tiny bitmap)
    for path in _SYSTEM_FALLBACKS.get(bold, []) + _SYSTEM_FALLBACKS.get(not bold, []):
        try:
            if os.path.exists(path):
                return ImageFont.truetype(path, size)
        except OSError:
            continue
    # 3) PIL search path, then last-resort bitmap
    try:
        return ImageFont.truetype("DejaVuSans.ttf", size)
    except OSError:
        return ImageFont.load_default()


def font_health():
    """Diagnostic: returns whether the bundled fonts loaded. Used by a self-check
    so font problems surface loudly instead of rendering invisible text."""
    return {
        "bold_bundled": _FONT_BYTES.get(True) is not None,
        "regular_bundled": _FONT_BYTES.get(False) is not None,
        "font_dir": _FONT_DIR,
    }


def _resolve_media(path):
    """Turn a stored media path into a readable filesystem path, robustly.
    Prefers Django's storage API (knows the real location) and falls back to
    several MEDIA_ROOT-relative guesses."""
    if not path:
        return None
    from django.core.files.storage import default_storage
    # 1) ask the storage backend directly (handles its own layout)
    try:
        if default_storage.exists(path):
            return default_storage.path(path)
    except (NotImplementedError, ValueError, OSError):
        pass
    # 2) absolute path that exists
    if os.path.isabs(path) and os.path.exists(path):
        return path
    # 3) MEDIA_ROOT-relative variants (strip leading slash and any 'media/' prefix)
    media_root = str(settings.MEDIA_ROOT)
    rel = path.lstrip("/")
    for candidate in (
        os.path.join(media_root, rel),
        os.path.join(media_root, rel.replace("media/", "", 1)),
        os.path.join(media_root, os.path.basename(path)),
    ):
        if os.path.exists(candidate):
            return candidate
    return None


def _circular(img, size):
    """Crop img to a centered square and apply a circular mask, sized size x size."""
    img = ImageOps.fit(img, (size, size), Image.LANCZOS)
    mask = Image.new("L", (size, size), 0)
    ImageDraw.Draw(mask).ellipse((0, 0, size, size), fill=255)
    out = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    out.paste(img, (0, 0), mask)
    return out


def compose_card(template, member, message):
    """Compose a birthday card PNG. Returns bytes.
    `template` is a BirthdayCardTemplate; `member` a Member; `message` the text."""
    bg_path = _resolve_media(template.image_path)
    if bg_path:
        bg = Image.open(bg_path).convert("RGBA")
    else:
        # fallback plain background if the template image is missing
        bg = Image.new("RGBA", (1080, 1080), (30, 41, 59, 255))

    canvas = bg.copy()
    W, H = canvas.width, canvas.height

    # Positions in the template assume a tall canvas. If the uploaded background
    # is a different size/shape (e.g. a short landscape image), fixed positions
    # can land off the visible area and the text disappears. We clamp every
    # position into the canvas, and if positions would push content past the
    # bottom, we scale them proportionally so everything stays visible.
    def _cx(x):
        return max(0, min(int(x), W - 10))

    def _cy(y, text_h=0):
        return max(0, min(int(y), H - max(text_h, 10)))

    # --- member photo (clamp so it fits) ---
    photo_path = _resolve_media(member.official_photo_path or member.display_photo_path)
    if photo_path:
        try:
            photo = Image.open(photo_path).convert("RGBA")
            size = max(20, min(template.photo_size, min(W, H) - 20))
            if template.photo_circle:
                photo = _circular(photo, size)
            else:
                photo = ImageOps.fit(photo, (size, size), Image.LANCZOS)
            px, py = _cx(template.photo_x), max(0, min(template.photo_y, H - size))
            canvas.paste(photo, (px, py), photo)
        except OSError:
            pass  # unreadable photo -> skip, text-only

    draw = ImageDraw.Draw(canvas)
    color = template.text_color or "#FFFFFF"
    # auto-pick an outline colour that contrasts with the fill
    outline = getattr(template, "text_stroke", None) or _auto_stroke(color)

    # --- name ---
    display_name = member.preferred_name or member.other_names or member.surname
    name_font = _font(True, template.name_size, getattr(template, "name_font", "default"))
    name_h = name_font.getbbox("Ay")[3]
    _text_outlined(draw, (_cx(template.name_x), _cy(template.name_y, name_h)),
                   display_name, name_font, color, outline, width=3)

    # --- message (wrapped) ---
    msg_font = _font(False, template.message_size, getattr(template, "message_font", "default"))
    msg_h = msg_font.getbbox("Ay")[3]
    _draw_wrapped(draw, message or "", (_cx(template.message_x), _cy(template.message_y, msg_h)),
                  msg_font, color, max_width=W - _cx(template.message_x) - 40,
                  outline=outline)

    out = BytesIO()
    canvas.convert("RGB").save(out, format="PNG")
    return out.getvalue()


def _text_outlined(draw, xy, text, font, fill, outline, width=3):
    """Draw text with a manual outline by stamping the outline colour at offsets,
    then the fill on top. Works on ANY Pillow version (no stroke_width dependency)
    and guarantees the text is readable on any background."""
    x, y = xy
    for dx in range(-width, width + 1):
        for dy in range(-width, width + 1):
            if dx or dy:
                draw.text((x + dx, y + dy), text, font=font, fill=outline)
    draw.text((x, y), text, font=font, fill=fill)


def _auto_stroke(fill_hex):
    """Pick black or white outline to contrast with the fill colour."""
    try:
        h = fill_hex.lstrip("#")
        if len(h) == 3:
            h = "".join(c * 2 for c in h)
        r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
        luminance = 0.299 * r + 0.587 * g + 0.114 * b
        return "#000000" if luminance > 140 else "#FFFFFF"
    except (ValueError, AttributeError):
        return "#000000"


def _draw_wrapped(draw, text, xy, font, fill, max_width, outline="#000000"):
    x, y = xy
    line_h = (font.getbbox("Ay")[3] - font.getbbox("Ay")[1]) + 12
    for paragraph in text.split("\n"):
        words = paragraph.split()
        line = ""
        for w in words:
            trial = (line + " " + w).strip()
            if draw.textlength(trial, font=font) <= max_width:
                line = trial
            else:
                _text_outlined(draw, (x, y), line, font, fill, outline, width=2)
                y += line_h
                line = w
        _text_outlined(draw, (x, y), line, font, fill, outline, width=2)
        y += line_h


def diagnose():
    """Self-diagnostic run on the LIVE server. Returns a dict of facts about
    font loading + a test render, so font problems become visible instead of
    silent invisible text. Surfaced via the /birthdays/diagnose/ endpoint."""
    import PIL
    info = {
        "pillow_version": PIL.__version__,
        "font_dir": _FONT_DIR,
        "bundled_bold_present": _FONT_BYTES.get(True) is not None,
        "bundled_regular_present": _FONT_BYTES.get(False) is not None,
        "font_dir_exists": os.path.isdir(_FONT_DIR),
        "font_dir_contents": [],
        "loaded_font_repr": None,
        "loaded_font_size_ok": None,
        "test_text_pixels_drawn": None,
        "supports_stroke_width": None,
        "error": None,
    }
    try:
        if os.path.isdir(_FONT_DIR):
            info["font_dir_contents"] = os.listdir(_FONT_DIR)
    except OSError as e:
        info["error"] = f"listdir: {e}"

    try:
        f = _font(True, 60)
        info["loaded_font_repr"] = repr(f)
        # is the loaded font actually scalable (not the tiny bitmap)?
        h = f.getbbox("Ay")[3]
        info["loaded_font_size_ok"] = h > 25  # real 60px font is tall; bitmap ~10
        info["loaded_font_height"] = h

        # actually draw text and count non-background pixels
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (300, 100), (0, 0, 0))
        d = ImageDraw.Draw(img)
        _text_outlined(d, (10, 10), "TEST", f, "#FFFFFF", "#FF0000", width=2)
        # count pixels that aren't pure black background
        nonbg = sum(1 for px in img.getdata() if px != (0, 0, 0))
        info["test_text_pixels_drawn"] = nonbg
    except Exception as e:  # noqa: BLE001 - diagnostic must never crash
        info["error"] = f"{type(e).__name__}: {e}"

    try:
        import inspect
        info["supports_stroke_width"] = "stroke_width" in inspect.signature(
            ImageDraw.ImageDraw.text).parameters
    except Exception:  # noqa: BLE001
        pass
    return info
