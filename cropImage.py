import os
import base64
import json
import math
import shutil
from PIL import Image
from openai import OpenAI
from google import genai
from parasound_defaults import p_secrets

# ==========================================
# OPENAI & GEMINI CONFIGURATION
# ==========================================
# OpenAI Setup
API_KEY = p_secrets.OPENAI_API_KEY
ORG_ID = os.getenv("OPENAI_ORG_ID", None)       
PROJECT_ID = os.getenv("OPENAI_PROJECT_ID", None) 

client = OpenAI(
    api_key=API_KEY,
    organization=ORG_ID,
    project=PROJECT_ID
)

# Gemini Setup
GEMINI_API_KEY = p_secrets.GEMINI_KEY
gemini_client = genai.Client(api_key=GEMINI_API_KEY)
# ==========================================

# Define Target Aspect Ratios per Platform
PLATFORM_RATIOS = {
    "instagram": ["1:1", "4:5", "1.91:1"],
    "threads": ["1:1", "4:5", "1.91:1"],
    "facebook": ["1:1", "4:5", "1.91:1", "16:9"],
    "linkedin": ["1:1", "4:5", "1.91:1", "16:9", "3:4"]
}

# Define Acceptable Native Bounds (Width / Height)
PLATFORM_BOUNDS = {
    "instagram": (0.8, 1.91),
    "threads": (0.8, 1.91),
    "facebook": (0.5625, 2.0),
    "linkedin": (0.4, 2.5)
}

# Display-optimal ratios per platform (best engagement / screen real estate)
# These are the ratios where the image already looks great — no AI consultation needed.
PLATFORM_IDEAL_RATIOS = {
    "instagram": ["4:5"],       # 4:5 dominates feed real estate; 1:1 is acceptable but 4:5 is king
    "threads": ["4:5", "1:1"],
    "facebook": ["1:1", "4:5"],
    "linkedin": ["1:1", "1.91:1"],
}

# Platform-specific display context for the AI to make informed decisions
PLATFORM_DISPLAY_CONTEXT = {
    "instagram": (
        "Instagram feed thumbnails are always cropped to 1:1 in the grid. "
        "4:5 portrait images get ~20% more screen real estate in the feed than 1:1. "
        "Landscape images (wider than 1:1) lose significant vertical space in the feed. "
        "For maximum visual impact, 4:5 is almost always the best choice unless the image "
        "is inherently panoramic/landscape and cropping would destroy the composition."
    ),
    "threads": (
        "Threads displays images similarly to Instagram. 4:5 and 1:1 are the strongest "
        "display ratios. Landscape images get less screen real estate in the feed."
    ),
    "facebook": (
        "Facebook feed images display well at 1:1 and 4:5. 16:9 works for cinematic content. "
        "Very tall or very wide ratios may get awkwardly letterboxed in the feed."
    ),
    "linkedin": (
        "LinkedIn feed images display best at 1:1 or 1.91:1 (landscape). "
        "1.91:1 is ideal for link preview-style images. 1:1 is best for standalone posts. "
        "Tall portrait images (like 4:5) are acceptable but less common on the platform."
    ),
}

# Setup Paths
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
ASSETS_DIR = os.path.abspath(os.path.join(SCRIPT_DIR, '..', 'imageGeneratorAssets'))
INPUT_DIR = os.path.join(ASSETS_DIR, 'imageCropper Input')
OUTPUT_DIR = os.path.join(ASSETS_DIR, 'imageCropper Output')

def setup_directories():
    os.makedirs(INPUT_DIR, exist_ok=True)
    os.makedirs(OUTPUT_DIR, exist_ok=True)

def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

def is_image_acceptable(image_path, platform):
    with Image.open(image_path) as img:
        orig_w, orig_h = img.size
        ratio = orig_w / orig_h
        min_ratio, max_ratio = PLATFORM_BOUNDS[platform]
        return min_ratio <= ratio <= max_ratio

def does_image_match_anchor(image_path, anchor_ratio):
    with Image.open(image_path) as img:
        orig_w, orig_h = img.size
        ratio = orig_w / orig_h
        t_w, t_h = map(float, anchor_ratio.split(':'))
        target = t_w / t_h
        # Allow a tiny 2% margin of error for pixel rounding
        return math.isclose(ratio, target, rel_tol=0.02)

def get_anchor_ratio_from_ai(image_paths, platform, provider):
    allowed_ratios = PLATFORM_RATIOS[platform]
    prompt = f"""
    You are an expert social media manager preparing a multi-image carousel for {platform}. 
    Look at ALL the attached images. Determine the SINGLE best aspect ratio from this allowed list: {allowed_ratios} that will work best for the entire group, minimizing the need for heavy cropping or padding across the set.
    
    Respond ONLY in valid JSON format like this:
    {{
        "anchor_ratio": "4:5"
    }}
    """

    if provider == "openai":
        content_list = [{"type": "text", "text": prompt}]
        for path in image_paths:
            base64_img = encode_image(path)
            content_list.append({"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_img}"}})
            
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{"role": "user", "content": content_list}],
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content).get("anchor_ratio", "1:1")
        
    elif provider == "gemini":
        contents_list = [prompt]
        for path in image_paths:
            contents_list.append(Image.open(path))
            
        response = gemini_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=contents_list,
            config={"response_mime_type": "application/json"}
        )
        return json.loads(response.text).get("anchor_ratio", "1:1")

def should_optimize_image(image_path, platform, provider):
    """Ask AI whether an image with an acceptable-but-not-ideal ratio should be adjusted."""
    with Image.open(image_path) as img:
        orig_w, orig_h = img.size
        current_ratio = orig_w / orig_h

    allowed_ratios = PLATFORM_RATIOS[platform]
    display_context = PLATFORM_DISPLAY_CONTEXT.get(platform, "")

    prompt = f"""
    You are an expert social media manager optimizing images for {platform}.

    Platform display rules:
    {display_context}

    The attached image has a native aspect ratio of {current_ratio:.3f} (width/height), which is technically accepted by {platform}'s API. However, "accepted" does not mean "optimal for display."

    Consider:
    1. Will the image lose important visual impact at its current ratio on this platform?
    2. Would cropping or padding to a different ratio significantly improve how it appears in the feed/grid?
    3. Is the current composition already strong, making any change unnecessary or harmful?

    Available target ratios: {allowed_ratios}

    Respond ONLY in valid JSON:
    {{
        "should_adjust": true/false,
        "reason": "brief explanation",
        "recommended_ratio": "4:5"
    }}

    Set "should_adjust" to false if the image already displays well as-is. Only recommend adjustment when there's a meaningful display benefit.
    """

    if provider == "openai":
        base64_image = encode_image(image_path)
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[{
                "role": "user",
                "content": [
                    {"type": "text", "text": prompt},
                    {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                ]
            }],
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)

    elif provider == "gemini":
        img_pil = Image.open(image_path)
        response = gemini_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[prompt, img_pil],
            config={"response_mime_type": "application/json"}
        )
        return json.loads(response.text)

def get_crop_data_from_ai(image_path, platform, provider, forced_ratio=None):
    if forced_ratio:
        ratio_instructions = f"You MUST use the aspect ratio {forced_ratio}. Do not choose any other ratio."
    else:
        ratio_instructions = f"Determine the best aspect ratio from this allowed list for {platform}: {PLATFORM_RATIOS[platform]}."
    
    prompt = f"""
    You are an expert social media image editor. 
    Analyze the attached image.
    
    {ratio_instructions}
    
    First, decide whether to "crop" or "pad" the image:
    - Choose "pad" if there are multiple critical elements (like a face AND an award) that span across the image, and forcing a crop would cut them off.
    - Choose "crop" if the subject is relatively centralized and the edges can be safely trimmed without losing context.
    
    If cropping, identify the main focal point of the image so we can crop around it. Provide the focal point as relative coordinates (x, y) where 0.0, 0.0 is top-left and 1.0, 1.0 is bottom-right.
    
    Respond ONLY in valid JSON format like this:
    {{
        "action": "pad", 
        "aspect_ratio": "{forced_ratio if forced_ratio else '4:5'}",
        "focal_x": 0.5,
        "focal_y": 0.5
    }}
    """

    if provider == "openai":
        base64_image = encode_image(image_path)
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=[
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {"type": "image_url", "image_url": {"url": f"data:image/jpeg;base64,{base64_image}"}}
                    ]
                }
            ],
            response_format={"type": "json_object"}
        )
        return json.loads(response.choices[0].message.content)
        
    elif provider == "gemini":
        img_pil = Image.open(image_path)
        response = gemini_client.models.generate_content(
            model='gemini-2.5-flash',
            contents=[prompt, img_pil],
            config={"response_mime_type": "application/json"}
        )
        return json.loads(response.text)

def process_image(image_path, output_path, crop_data):
    img = Image.open(image_path).convert("RGB")
    orig_w, orig_h = img.size
    
    ratio_parts = crop_data['aspect_ratio'].split(':')
    target_ratio = float(ratio_parts[0]) / float(ratio_parts[1])
    orig_ratio = orig_w / orig_h
    
    action = crop_data.get('action', 'crop')

    if action == 'pad':
        if orig_ratio > target_ratio:
            canvas_w = orig_w
            canvas_h = int(orig_w / target_ratio)
        else:
            canvas_h = orig_h
            canvas_w = int(orig_h * target_ratio)
            
        bg_color = img.getpixel((0, 0))
        canvas = Image.new('RGB', (canvas_w, canvas_h), bg_color)
        offset_x = (canvas_w - orig_w) // 2
        offset_y = (canvas_h - orig_h) // 2
        canvas.paste(img, (offset_x, offset_y))
        canvas.save(output_path, quality=95)

    else:
        if orig_ratio > target_ratio:
            new_w = int(orig_h * target_ratio)
            new_h = orig_h
        else:
            new_w = orig_w
            new_h = int(orig_w / target_ratio)
            
        focal_x = crop_data['focal_x'] * orig_w
        focal_y = crop_data['focal_y'] * orig_h
        
        left = max(0, int(focal_x - new_w / 2))
        top = max(0, int(focal_y - new_h / 2))
        right = left + new_w
        bottom = top + new_h
        
        if left < 0:
            right -= left
            left = 0
        if top < 0:
            bottom -= top
            top = 0
        if right > orig_w:
            left -= (right - orig_w)
            right = orig_w
            left = max(0, left)
        if bottom > orig_h:
            top -= (bottom - orig_h)
            bottom = orig_h
            top = max(0, top)
            
        cropped_img = img.crop((left, top, right, bottom))
        cropped_img.save(output_path, quality=95)

def main():
    setup_directories()
    
    print("Available platforms: facebook, instagram, linkedin, threads")
    user_input = input("Enter platforms to process (comma separated) or 'all': ").strip().lower()
    
    if user_input == 'all':
        selected_platforms = list(PLATFORM_RATIOS.keys())
    else:
        selected_platforms = [p.strip() for p in user_input.split(',') if p.strip() in PLATFORM_RATIOS]
        
    if not selected_platforms:
        print("No valid platforms selected. Exiting.")
        return

    image_files = [f for f in os.listdir(INPUT_DIR) if f.lower().endswith(('.png', '.jpg', '.jpeg'))]
    image_paths = [os.path.join(INPUT_DIR, f) for f in image_files]
    
    if not image_files:
        print(f"No images found in {INPUT_DIR}")
        return
        
    is_multi_image = len(image_files) > 1
    if is_multi_image:
        print(f"Detected {len(image_files)} images. Enabling Carousel/Batch Mode for supported platforms.")

    providers = ["openai", "gemini"]
        
    for platform in selected_platforms:
        platform_out_dir = os.path.join(OUTPUT_DIR, platform)
        os.makedirs(platform_out_dir, exist_ok=True)
        
        # Facebook always runs individually. Others group up if multi-image.
        needs_anchor = is_multi_image and platform != "facebook"
        
        for provider in providers:
            anchor_ratio = None
            
            if needs_anchor:
                print(f"\n[{platform.upper()} | {provider.upper()}] Analyzing entire set to find Anchor Ratio...")
                try:
                    anchor_ratio = get_anchor_ratio_from_ai(image_paths, platform, provider)
                    print(f"  -> Selected Anchor Ratio: {anchor_ratio}")
                except Exception as e:
                    print(f"  -> Failed to get anchor ratio: {e}")
                    continue

            for filename in image_files:
                filepath = os.path.join(INPUT_DIR, filename)
                print(f"\n  Processing {filename} for {platform} via {provider.upper()}...")
                
                # --- SMART BYPASS LOGIC ---
                if needs_anchor:
                    # Multi-image mode (IG, Threads, LinkedIn): Must match the anchor ratio exactly
                    if does_image_match_anchor(filepath, anchor_ratio):
                        print(f"    -> Native image perfectly matches anchor ratio ({anchor_ratio}). Bypassing AI...")
                        out_filepath = os.path.join(platform_out_dir, f"native_{provider}_{platform}_{filename}")
                        shutil.copy2(filepath, out_filepath)
                        continue
                else:
                    # Single-image mode OR Facebook: Check if it matches an ideal display ratio first
                    ideal_ratios = PLATFORM_IDEAL_RATIOS.get(platform, [])
                    matches_ideal = any(does_image_match_anchor(filepath, r) for r in ideal_ratios)

                    if matches_ideal:
                        print(f"    -> Native ratio matches an ideal display ratio for {platform.upper()}. Bypassing AI...")
                        out_filepath = os.path.join(platform_out_dir, f"native_{platform}_{filename}")
                        shutil.copy2(filepath, out_filepath)
                        break

                    # Ratio is acceptable by API but not ideal — ask AI if we should optimize for display
                    if is_image_acceptable(filepath, platform):
                        print(f"    -> Ratio is accepted by {platform.upper()} API but may not be display-optimal. Consulting {provider.upper()}...")
                        try:
                            optimization = should_optimize_image(filepath, platform, provider)
                            should_adjust = optimization.get("should_adjust", False)
                            reason = optimization.get("reason", "")
                            print(f"    -> AI says adjust={should_adjust}: {reason}")

                            if not should_adjust:
                                print(f"    -> AI confirms image displays well as-is. Keeping native ratio.")
                                out_filepath = os.path.join(platform_out_dir, f"native_{provider}_{platform}_{filename}")
                                shutil.copy2(filepath, out_filepath)
                                continue

                            # AI recommends adjustment — use recommended ratio as forced ratio
                            recommended = optimization.get("recommended_ratio")
                            if recommended:
                                print(f"    -> AI recommends adjusting to {recommended} for better display.")
                                crop_data = get_crop_data_from_ai(filepath, platform, provider, forced_ratio=recommended)
                                action_taken = crop_data.get('action', 'crop').upper()
                                print(f"    -> AI chose {action_taken} with ratio {crop_data['aspect_ratio']}")
                                out_filepath = os.path.join(platform_out_dir, f"{provider}_{platform}_{filename}")
                                process_image(filepath, out_filepath, crop_data)
                                print(f"    -> Saved to {out_filepath}")
                                continue
                        except Exception as e:
                            print(f"    -> Optimization check failed ({e}), falling through to standard processing...")
                
                # --- AI PROCESSING ---
                try:
                    crop_data = get_crop_data_from_ai(filepath, platform, provider, forced_ratio=anchor_ratio)
                    action_taken = crop_data.get('action', 'crop').upper()
                    print(f"    -> AI chose {action_taken} with ratio {crop_data['aspect_ratio']}")
                    
                    out_filepath = os.path.join(platform_out_dir, f"{provider}_{platform}_{filename}")
                    process_image(filepath, out_filepath, crop_data)
                    print(f"    -> Saved to {out_filepath}")
                    
                except Exception as e:
                    print(f"    -> Error: {e}")

if __name__ == "__main__":
    main()