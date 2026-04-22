#!/usr/bin/env python3
"""
Modern HTML ➜ Branded Social Image Generator (Parasound-branded)
"""

import os
import textwrap
from playwright.sync_api import sync_playwright

PLATFORMS = {
    "1": {"name": "instagram", "width": 1080, "height": 1350},
    "2": {"name": "facebook",  "width": 1200, "height": 630},
    "3": {"name": "linkedin",  "width": 1200, "height": 627},
    "4": {"name": "threads",   "width": 1080, "height": 1350},
}

BASE_CSS = """
/* Pre-baked Gold Banner */
.gold-banner {
    background-color: #2b2721;
    color: #e7b95f; /* Changed to White */
    font-family: "Archivo Narrow", system-ui, sans-serif;
    font-weight: bold;
    font-size: 1.2em;
    letter-spacing: 0.2em;
    margin-right: -0.2em; /* FIXES THE OFF-CENTER BUG */
    text-transform: uppercase;
    display: inline-block;
    padding: 0.6em 1.2em;
    margin-bottom: 1.5em;
    white-space: nowrap; /* PREVENTS CLIPPING */
}

p { margin: 0; padding: 0; }
"""

def get_html_from_user() -> str:
    print("Paste your raw HTML below. Type 'END' on a new line when done.\n")
    lines = []
    while True:
        try:
            line = input()
        except EOFError:
            break
        if line.strip() == "END":
            break
        lines.append(line)
    return "\n".join(lines).strip()

def choose_platforms():
    print(textwrap.dedent("""
        Which social image(s) would you like to generate?
        1. Instagram (1080 x 1350)
        2. Facebook  (1200 x 630)
        3. LinkedIn  (1200 x 627)
        4. Threads   (1080 x 1350)
        5. All of the above
    """))
    choice = input("Enter 1, 2, 3, 4, or 5: ").strip()
    return list(PLATFORMS.keys()) if choice == "5" or choice not in PLATFORMS else [choice]

def compute_typography(width: int, height: int):
    aspect = height / float(width)
    base = max(24, min(int(height * 0.028), 36)) if aspect >= 1.2 else max(16, min(int(height * 0.024), 24))
    return {"base": base, "h1": int(base * 2.2), "lh": int(base * 1.6)}

def build_full_html(user_html: str, width: int, height: int) -> str:
    typo = compute_typography(width, height)
    
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="utf-8">
    <link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Archivo:wght@500;600;700&family=Archivo+Narrow:wght@500;600;700&family=Barlow:wght@400;500;600;700&display=swap">
    <style>
    {BASE_CSS}
    html, body {{
        margin: 0; padding: 0;
        width: {width}px; height: {height}px;
        background-color: #1C1C1C;
        display: flex; align-items: center; justify-content: center;
        box-sizing: border-box;
    }}
    .content-wrapper {{
        width: 85%; text-align: center;
        display: flex; flex-direction: column; align-items: center; justify-content: center;
    }}
    h1 {{
        color: #ffffff;
        font-family: "Archivo Narrow", system-ui, sans-serif;
        font-size: {typo['h1']}px; line-height: 1.1;
        letter-spacing: 0.05em; margin-right: -0.05em; /* FIXES OFF-CENTER */
        text-transform: uppercase; margin-top: 0; margin-bottom: 0.3em;
    }}
    p, span, div {{
        color: #F5F5F5; font-family: "Barlow", system-ui, sans-serif;
        font-size: {typo['base']}px; line-height: {typo['lh']}px;
    }}
    strong {{
        color: #E7B95F; font-family: "Archivo", system-ui, sans-serif;
    }}
    .divider {{
        width: 150px; height: 5px; background-color: #E7B95F; margin: 1.5em auto;
    }}
    </style>
</head>
<body>
    <div class="content-wrapper">
        {user_html}
    </div>
</body>
</html>
"""

def generate_image_for_platform(playwright, user_html: str, platform_key: str, out_dir: str):
    plat = PLATFORMS[platform_key]
    html = build_full_html(user_html, plat["width"], plat["height"])
    out_path = os.path.join(out_dir, f"{plat['name']}.png")
    
    browser = playwright.chromium.launch(headless=True)
    page = browser.new_page(viewport={"width": plat["width"], "height": plat["height"]})
    page.set_content(html)
    
    # CRITICAL FIX: Forces script to wait for fonts to load before calculating the gold box width
    page.evaluate("document.fonts.ready") 
    
    page.screenshot(path=out_path)
    browser.close()
    print(f"Generated -> {out_path}")

def main():
    platform_keys = choose_platforms()
    user_html = get_html_from_user()
    out_dir = "output_images"
    os.makedirs(out_dir, exist_ok=True)

    with sync_playwright() as playwright:
        for key in platform_keys:
            generate_image_for_platform(playwright, user_html, key, out_dir)

if __name__ == "__main__":
    main()