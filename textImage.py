#!/usr/bin/env python3
"""
HTML ➜ Branded Social Image Generator

Requirements:
    pip install imgkit

Also install wkhtmltoimage and make sure it's on your PATH.
"""

import os
import textwrap
import imgkit

# If wkhtmltoimage is not on PATH, set its full path here, e.g.:
# WKHTMLTOIMAGE_CMD = r"C:\Program Files\wkhtmltopdf\bin\wkhtmltoimage.exe"
WKHTMLTOIMAGE_CMD = None  # leave as None if it's already on PATH

# ---------- Platform presets (sizes in pixels) ----------
PLATFORMS = {
    "1": {
        "name": "instagram",
        "width": 1080,
        "height": 1350,  # 4:5 portrait, ideal for feed
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
/* --------- Brand Defaults --------- */
@import url('https://fonts.googleapis.com/css2?family=Archivo:wght@500;600;700&family=Archivo+Narrow:wght@500;600;700&family=Barlow:wght@400;500;600;700&display=swap');

:root {
    --bg-color: #1C1C1C;
    --header-color: #E7B95F;
    --body-color: #F5F5F5;
    --accent-color: #E7B95F;
}

/* Reset-ish */
* {
    box-sizing: border-box;
    margin: 0;
    padding: 0;
}

/* Full canvas */
html, body {
    width: 100%;
    height: 100%;
}

/* Center content on the canvas */
body {
    background-color: var(--bg-color);
    color: var(--body-color);
    font-family: "Barlow", system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    display: flex;
    align-items: center;
    justify-content: center;
    text-align: center;
}

/* Wrapper to keep content nicely centered + padded */
.wrapper {
    width: 90%;
    max-width: 900px;
    margin: 0 auto;
    padding: 40px 40px 48px;
    border-radius: 24px;
}

/* Optional subtle "card" effect if you want to differentiate text from background */
.card {
    background: rgba(255, 255, 255, 0.02);
    border-radius: 24px;
    padding: 32px 32px 40px;
}

/* Headings */
h1, h2, h3, h4, h5, h6 {
    color: var(--header-color);
    font-family: "Archivo Narrow", system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    letter-spacing: 0.08em;
    text-transform: uppercase;
    margin-bottom: 0.4em;
}

h1 { font-size: 2.7rem; }
h2 { font-size: 2.1rem; }
h3 { font-size: 1.7rem; }
h4 { font-size: 1.4rem; }
h5 { font-size: 1.2rem; }
h6 { font-size: 1rem; }

/* Body text */
p, li, span, div {
    font-size: 1rem;
    line-height: 1.5;
}

/* Accent / emphasis */
strong, b, em, i, a, .accent {
    color: var(--accent-color);
    font-family: "Archivo", system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}

/* Links (if any) */
a {
    text-decoration: none;
}

/* Simple vertical spacing utility */
.stack > * + * {
    margin-top: 0.65em;
}

/* Optional small caption style */
.caption {
    opacity: 0.8;
    font-size: 0.85rem;
}
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


def build_full_html(user_html: str, extra_css: str = "") -> str:
    """
    Wrap user HTML in a centered wrapper and attach CSS.
    """
    full_css = BASE_CSS
    if extra_css:
        full_css += "\n\n/* ---- User Overrides ---- */\n" + extra_css

    # Ensure content is centered in a nice container.
    wrapped_html = f"""
    <div class="wrapper">
      <div class="card stack">
        {user_html}
      </div>
    </div>
    """

    full_html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <style>
    {full_css}
    </style>
</head>
<body>
{wrapped_html}
</body>
</html>
"""
    return full_html


def ensure_output_dir(path: str = "output_images") -> str:
    os.makedirs(path, exist_ok=True)
    return path


def generate_image_for_platform(html: str, platform_key: str, out_dir: str):
    plat = PLATFORMS[platform_key]
    name = plat["name"]
    width = plat["width"]
    height = plat["height"]

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

    full_html = build_full_html(user_html, extra_css)
    out_dir = ensure_output_dir()

    for key in platform_keys:
        generate_image_for_platform(full_html, key, out_dir)

    print("All requested images generated.")
    print(f"Check the '{out_dir}' folder in the current directory.")


if __name__ == "__main__":
    main()