import os
import base64
import json
import math
from PIL import Image
from openai import OpenAI
import google.generativeai as genai
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
genai.configure(api_key=GEMINI_API_KEY)
gemini_model = genai.GenerativeModel('gemini-1.5-pro')
# ==========================================

# Define Aspect Ratios per Platform
PLATFORM_RATIOS = {
    "instagram": ["1:1", "4:5", "1.91:1"],
    "threads": ["1:1", "4:5", "1.91:1"],
    "facebook": ["1:1", "4:5", "1.91:1", "16:9"],
    "linkedin": ["1:1", "4:5", "1.91:1", "16:9", "3:4"]
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
        response = gemini_model.generate_content(
            [prompt, img_pil],
            generation_config={"response_mime_type": "application/json"}
        )
        return json.loads(response.text)

def process_image(image_path, output_path, crop_data):
    # Convert to RGB to ensure smooth color sampling and saving
    img = Image.open(image_path).convert("RGB")
    orig_w, orig_h = img.size
    
    # Parse target ratio
    ratio_parts = crop_data['aspect_ratio'].split(':')
    target_ratio = float(ratio_parts[0]) / float(ratio_parts[1])
    orig_ratio = orig_w / orig_h
    
    action = crop_data.get('action', 'crop')

    if action == 'pad':
        # --- PADDING LOGIC ---
        # Determine canvas dimensions
        if orig_ratio > target_ratio:
            # Image is too wide, add padding to top and bottom
            canvas_w = orig_w
            canvas_h = int(orig_w / target_ratio)
        else:
            # Image is too tall, add padding to left and right
            canvas_h = orig_h
            canvas_w = int(orig_h * target_ratio)
            
        # Sample the background color from the top-left corner
        bg_color = img.getpixel((0, 0))
        
        # Create new canvas and paste original image in the center
        canvas = Image.new('RGB', (canvas_w, canvas_h), bg_color)
        offset_x = (canvas_w - orig_w) // 2
        offset_y = (canvas_h - orig_h) // 2
        canvas.paste(img, (offset_x, offset_y))
        
        canvas.save(output_path, quality=95)

    else:
        # --- CROPPING LOGIC ---
        # Determine new dimensions
        if orig_ratio > target_ratio:
            # Image is too wide, crop width
            new_w = int(orig_h * target_ratio)
            new_h = orig_h
        else:
            # Image is too tall, crop height
            new_w = orig_w
            new_h = int(orig_w / target_ratio)
            
        # Calculate crop box using focal point
        focal_x = crop_data['focal_x'] * orig_w
        focal_y = crop_data['focal_y'] * orig_h
        
        left = max(0, int(focal_x - new_w / 2))
        top = max(0, int(focal_y - new_h / 2))
        right = left + new_w
        bottom = top + new_h
        
        # Adjust if box goes outside image bounds
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
    
    # UI: Get platforms from user
    print("Available platforms: facebook, instagram, linkedin, threads")
    user_input = input("Enter platforms to process (comma separated) or 'all': ").strip().lower()
    
    if user_input == 'all':
        selected_platforms = list(PLATFORM_RATIOS.keys())
    else:
        selected_platforms = [p.strip() for p in user_input.split(',') if p.strip() in PLATFORM_RATIOS]
        
    if not selected_platforms:
        print("No valid platforms selected. Exiting.")
        return

    # Process images
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