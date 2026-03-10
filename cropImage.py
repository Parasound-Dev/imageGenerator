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

# Define Target Aspect Ratios per Platform (For the AI to choose from if cropping is needed)
PLATFORM_RATIOS = {
    "instagram": ["1:1", "4:5", "1.91:1"],
    "threads": ["1:1", "4:5", "1.91:1"],
    "facebook": ["1:1", "4:5", "1.91:1", "16:9"],
    "linkedin": ["1:1", "4:5", "1.91:1", "16:9", "3:4"]
}

# Define Acceptable Native Bounds (Width / Height)
# If the original image ratio falls between these numbers, NO action is needed.
PLATFORM_BOUNDS = {
    "instagram": (0.8, 1.91),     # 4:5 to 1.91:1
    "threads": (0.8, 1.91),       # 4:5 to 1.91:1
    "facebook": (0.5625, 2.0),    # 9:16 to 2:1 (Very forgiving)
    "linkedin": (0.4, 2.5)        # Highly forgiving
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

def get_crop_data_from_ai(image_path, platform, provider):
    allowed_ratios = PLATFORM_RATIOS[platform]
    
    prompt = f"""
    You are an expert social media image editor. 
    Analyze the attached image and determine the best aspect ratio from this allowed list for {platform}: {allowed_ratios}.
    
    First, decide whether to "crop" or "pad" the image:
    - Choose "pad" if there are multiple critical elements (like a face AND an award) that span across the image, and forcing a crop would cut them off.
    - Choose "crop" if the subject is relatively centralized and the edges can be safely trimmed without losing context.
    
    If cropping, identify the main focal point of the image so we can crop around it. Provide the focal point as relative coordinates (x, y) where 0.0, 0.0 is top-left and 1.0, 1.0 is bottom-right.
    
    Respond ONLY in valid JSON format like this:
    {{
        "action": "pad", 
        "aspect_ratio": "4:5",
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
    
    if not image_files:
        print(f"No images found in {INPUT_DIR}")
        return
        
    providers = ["openai", "gemini"]
        
    for filename in image_files:
        filepath = os.path.join(INPUT_DIR, filename)
        
        print(f"\nProcessing: {filename}")
        
        for platform in selected_platforms:
            platform_out_dir = os.path.join(OUTPUT_DIR, platform)
            os.makedirs(platform_out_dir, exist_ok=True)
            
            # --- THE NEW PRE-CHECK ---
            if is_image_acceptable(filepath, platform):
                print(f"  -> {platform.upper()} natively accepts this image's ratio. Bypassing AI...")
                out_filepath = os.path.join(platform_out_dir, f"native_{platform}_{filename}")
                shutil.copy2(filepath, out_filepath)
                print(f"     Saved unedited original to {out_filepath}")
                continue # Skip the AI loop entirely for this platform
            
            # If the image is NOT acceptable, call the AIs to process it
            for provider in providers:
                print(f"  -> Getting AI crop data for {platform} via {provider.upper()}...")
                try:
                    crop_data = get_crop_data_from_ai(filepath, platform, provider)
                    action_taken = crop_data.get('action', 'crop').upper()
                    print(f"     {provider.upper()} chose {action_taken} with ratio {crop_data['aspect_ratio']}")
                    
                    out_filepath = os.path.join(platform_out_dir, f"{provider}_{platform}_{filename}")
                    process_image(filepath, out_filepath, crop_data)
                    print(f"     Saved to {out_filepath}")
                    
                except Exception as e:
                    print(f"     Error processing {platform} via {provider}: {e}")

if __name__ == "__main__":
    main()