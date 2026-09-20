import os
import glob
import subprocess
import shutil
from engine.street_extraction import extract_streets, pair_intersections
from engine.georeference import get_intersection_gps

def convert_pdf_to_images(pdf_path: str, output_dir: str, dpi: int = 300) -> list[str]:
    """Convert PDF pages to PNG images using pdftoppm."""
    base_name = os.path.splitext(os.path.basename(pdf_path))[0]
    os.makedirs(output_dir, exist_ok=True)
    
    # Run pdftoppm
    prefix = os.path.join(output_dir, base_name)
    cmd = ["pdftoppm", "-png", "-r", str(dpi), pdf_path, prefix]
    print(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)
    
    # Get generated images
    images = glob.glob(f"{prefix}*.png")
    return sorted(images)

def process_plats(plats_dir: str, temp_img_dir: str = "temp_images"):
    pdf_files = glob.glob(os.path.join(plats_dir, "*.pdf"))
    
    if not pdf_files:
        print(f"No PDFs found in {plats_dir}")
        return
        
    for pdf in pdf_files:
        print(f"\n--- Processing {os.path.basename(pdf)} ---")
        try:
            images = convert_pdf_to_images(pdf, temp_img_dir)
            for img in images:
                print(f"  Analyzing {os.path.basename(img)}...")
                try:
                    # 1. 4-Orientation OCR with CLAHE and Highlight Masking
                    extracted = extract_streets(img)
                    
                    # 2. Dual-Axis Intersection Consensus
                    pairs = pair_intersections(extracted)
                    
                    if not pairs:
                        print("    No street intersections found.")
                    
                    # 3. Natural Physical GPS Mapping
                    for h_street, v_street in pairs:
                        print(f"    Found candidate intersection: {h_street} & {v_street}")
                        coords = get_intersection_gps(h_street, v_street)
                        if coords:
                            print(f"      -> True WGS84 GPS: {coords[0]} N, {coords[1]} W")
                        else:
                            print(f"      -> No physical GPS coordinates mapped (Missing from DB).")
                except Exception as e:
                    print(f"    Error processing {img}: {e}")
                    
        except Exception as e:
            print(f"Error converting {pdf}: {e}")
            
    # Cleanup temporary images
    if os.path.exists(temp_img_dir):
        shutil.rmtree(temp_img_dir)

if __name__ == "__main__":
    plats_directory = "Plat"
    process_plats(plats_directory)
