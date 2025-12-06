#!/usr/bin/env python3
"""
HTML ➜ Branded Social Image Generator (Parasound-branded)

Requirements:
    pip install imgkit

Also install wkhtmltoimage and make sure it's installed.
We point directly to the wkhtmltoimage binary via WKHTMLTOIMAGE_CMD.
"""

import os
import textwrap
import imgkit

# Point directly to wkhtmltoimage so we don't depend on PATH quirks.
WKHTMLTOIMAGE_CMD = r"C:\Program Files\wkhtmltopdf\bin\wkhtmltoimage.exe"

# ---------- Platform presets (sizes in pixels) ----------
PLATFORMS = {
    "1": {
        "name": "instagram",
        "width": 1080,
        "height": 1350,  # 4:5 portrait
    },
    "2": {
        "name": "facebook",
        "width": 1200,
        "height": 630,   # ~1.91:1
    },
    "3": {
        "name": "linkedin",
        "width": 1200,
        "height": 627,   # LinkedIn recommended
    },
    "4": {
        "name": "threads",
        "width": 1080,
        "height": 1350,  # mirror Instagram
    },
}

BASE_CSS = """
/* Non-critical extras can go here; key styling is injected dynamically. */
"""


def get_html_from_user() -> str:
    print("Paste your raw HTML below.")
    print("When you're done, type a single line with 'END' and press Enter.\n")

    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip() == "END":
            break
        lines.append(line)
    html = "\n".join(lines).strip()
    if not html:
        print("No HTML detected, using a sample heading + paragraph.")
        html = "<h1>Sample Heading</h1><p>Replace this with your HTML.</p>"
    return html


def get_css_overrides_from_user() -> str:
    print("\nWould you like to add/override any CSS rules? (y/n)")
    choice = input("> ").strip().lower()

    if choice not in ("y", "yes"):
        return ""

    print("\nPaste extra CSS rules below (they will override defaults if conflicting).")
    print("When you're done, type a single line with 'END' and press Enter.\n")

    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip() == "END":
            break
        lines.append(line)

    css = "\n".join(lines).strip()
    if css:
        print("\nCustom CSS added.\n")
    else:
        print("\nNo custom CSS entered.\n")
    return css


def choose_platforms():
    print(textwrap.dedent("""
        Which social image(s) would you like to generate?

        1. Instagram (1080 x 1350, 4:5)
        2. Facebook  (1200 x 630)
        3. LinkedIn  (1200 x 627)
        4. Threads   (1080 x 1350)
        5. All of the above
    """))

    choice = input("Enter 1, 2, 3, 4, or 5: ").strip()
    if choice == "5":
        return list(PLATFORMS.keys())
    elif choice in PLATFORMS:
        return [choice]
    else:
        print("Invalid choice, defaulting to option 5 (all).")
        return list(PLATFORMS.keys())


def compute_typography(width: int, height: int):
    """
    Compute a base body font and related sizes based on canvas size.
    Portrait gets more aggressive scaling than landscape.
    """
    aspect = height / float(width)

    if aspect >= 1.2:
        # Portrait (IG / Threads) – use height as main driver
        base = int(height * 0.028)  # 1350 -> ~37
        base = max(24, min(base, 36))
    else:
        # Landscape (FB / LinkedIn)
        base = int(height * 0.024)  # 630 -> ~15
        base = max(16, min(base, 24))

    h1 = int(base * 2.0)       # heading relative to body
    h3 = int(base * 1.4)
    line_height = int(base * 1.6)

    return {
        "base": base,
        "h1": h1,
        "h3": h3,
        "line_height": line_height,
    }


def build_full_html(user_html: str, extra_css: str, width: int, height: int) -> str:
    """
    Wrap user HTML in a vertically-centered container and apply
    brand styling as inline + simple CSS, with font sizes based
    on the target canvas width/height.
    """
    typo = compute_typography(width, height)
    base = typo["base"]
    h1 = typo["h1"]
    h3 = typo["h3"]
    lh = typo["line_height"]

    extra = f"\n/* User overrides */\n{extra_css}" if extra_css else ""

    # Content wrapper width: narrower for better wrapping, esp. on tall formats.
    content_max_width = min(int(width * 0.8), 960)

    full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">

    <!-- Google Fonts for Archivo / Barlow -->
    <link rel="stylesheet"
          href="https://fonts.googleapis.com/css2?family=Archivo:wght@500;600;700&family=Archivo+Narrow:wght@500;600;700&family=Barlow:wght@400;500;600;700&display=swap">

    <style>
    {BASE_CSS}

    html, body {{
        margin: 0;
        padding: 0;
        width: 100%;
        height: 100%;
    }}

    /* Headings: Archivo Narrow, gold */
    h1, h2, h3, h4, h5, h6 {{
        color: #E7B95F;
        font-family: "Archivo Narrow", system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        letter-spacing: 0.07em;      /* slightly tighter to avoid clipping */
        text-transform: uppercase;
        margin-bottom: 0.4em;
        word-wrap: break-word;
        overflow-wrap: break-word;
    }}

    h1 {{
        font-size: {h1}px;
        line-height: 1.15;
        margin-bottom: {int(base * 1.0)}px;
    }}

    h3 {{
        font-size: {h3}px;
        margin-top: {int(base * 1.3)}px;
        margin-bottom: {int(base * 0.7)}px;
    }}

    /* Body text: Barlow, light color */
    p, li, span, div {{
        color: #F5F5F5;
        font-family: "Barlow", system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
        font-size: {base}px;
        line-height: {lh}px;
    }}

    /* Accent (strong/em) uses Archivo + gold */
    strong, b, em, i, a, .accent {{
        color: #E7B95F;
        font-family: "Archivo", system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}

    /* Center bullets nicely */
    ul {{
        list-style-position: inside;
        padding-left: 0;
        margin: {int(base * 0.4)}px auto 0 auto;
        text-align: left;
        display: inline-block;
    }}

    ul li {{
        margin: {int(base * 0.2)}px 0;
    }}

    {extra}
    </style>
</head>

<body style="
    margin:0;
    background-color:#1C1C1C;
    color:#F5F5F5;
    font-family:'Barlow', system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    font-size:{base}px;
">
    <div style="
        width:100%;
        height:{height}px;
        padding-top:{int(base * 0.5)}px;
        padding-bottom:{int(base * 1.8)}px;
        box-sizing:border-box;
        display:flex;
        align-items:center;
        justify-content:center;
        text-align:center;
    ">
        <div style="
            max-width:{content_max_width}px;
            width:86%;
            margin:0 auto;
        ">
            {user_html}
        </div>
    </div>
</body>
</html>
"""
    return full_html


def ensure_output_dir(path: str = "output_images") -> str:
    os.makedirs(path, exist_ok=True)
    return path


def generate_image_for_platform(user_html: str, extra_css: str,
                                platform_key: str, out_dir: str):
    plat = PLATFORMS[platform_key]
    name = plat["name"]
    width = plat["width"]
    height = plat["height"]

    html = build_full_html(user_html, extra_css, width, height)

    options = {
        "format": "png",
        "width": width,
        "height": height,
        "encoding": "UTF-8",
        # Disable content-based auto width; we want exact canvas size:
        "disable-smart-width": "",
    }

    config = None
    if WKHTMLTOIMAGE_CMD:
        config = imgkit.config(wkhtmltoimage=WKHTMLTOIMAGE_CMD)

    out_path = os.path.join(out_dir, f"{name}.png")

    print(f"Generating {name} image ({width}x{height}) -> {out_path}")
    imgkit.from_string(html, out_path, options=options, config=config)
    print(f"Done: {out_path}\n")


def main():
    print("=== HTML ➜ Branded Social Images ===\n")

    platform_keys = choose_platforms()
    user_html = get_html_from_user()
    extra_css = get_css_overrides_from_user()

    out_dir = ensure_output_dir()

    for key in platform_keys:
        generate_image_for_platform(user_html, extra_css, key, out_dir)

    print("All requested images generated.")
    print(f"Check the '{out_dir}' folder in the current directory.")


if __name__ == "__main__":
    main()