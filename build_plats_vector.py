import os
import glob
import subprocess
import shutil
import cv2
import math
from engine.vectorize import map_mask_excluding, extract_polylines, px_to_feet_polylines
from engine.dxf_writer import DXFWriter

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

def process_plats(plats_dir: str, temp_img_dir: str = "temp_images", output_dir: str = "dxf"):
    pdf_files = glob.glob(os.path.join(plats_dir, "*.pdf"))
    
    if not pdf_files:
        print(f"No PDFs found in {plats_dir}")
        return
        
    os.makedirs(output_dir, exist_ok=True)
        
    for pdf in pdf_files:
        print(f"\n=== Vectorizing {os.path.basename(pdf)} ===")
        try:
            images = convert_pdf_to_images(pdf, temp_img_dir, dpi=300)
            
            # Create one DXF per Plat (multi-sheet support)
            dxf = DXFWriter()
            dxf.add_layer("LINEWORK", "cyan", "CONTINUOUS")
            dxf.add_layer("TITLEBLOCK", "yellow", "CONTINUOUS")
            
            # Place sheets sequentially on the X axis
            offset_e = 0.0
            
            for i, img_path in enumerate(images):
                print(f"  Analyzing {os.path.basename(img_path)}...")
                img = cv2.imread(img_path, 0)
                if img is None:
                    continue
                    
                h, w = img.shape
                ft_px = 50 / 300.0  # Assuming 1" = 50' at 300 dpi as default
                
                # 1. Masking & Skeletonization
                mask = map_mask_excluding(img, skeleton=True)
                
                # 2. Extract Exact Polylines (breaks loops at junctions)
                polys = extract_polylines(mask, epsilon=1.5, break_junctions=True)
                
                # 3. Convert to feet
                polys_ft = px_to_feet_polylines(polys, ft_px, origin_px=(0, 0), img_h=h)
                
                # 4. Write to DXF
                drawn_len = 0.0
                min_n = min_e = 1e18; max_n = max_e = -1e18
                
                for poly in polys_ft:
                    # Apply offset for multiple sheets
                    shifted_poly = [(n, e + offset_e) for n, e in poly]
                    dxf.polyline(shifted_poly, layer="LINEWORK", closed=False)
                    
                    # Compute stats
                    for n, e in shifted_poly:
                        min_n = min(min_n, n); max_n = max(max_n, n)
                        min_e = min(min_e, e); max_e = max(max_e, e)
                        
                    # Compute drawn length
                    for idx in range(len(shifted_poly)-1):
                        p1, p2 = shifted_poly[idx], shifted_poly[idx+1]
                        drawn_len += math.hypot(p2[0]-p1[0], p2[1]-p1[1])

                print(f"    Found {len(polys)} continuous polylines ({drawn_len:,.0f} ft of linework)")
                
                # Add label
                label_n = min_n - 50 if min_n != 1e18 else 0
                dxf.text((label_n, offset_e), f"SHEET {i+1} | {len(polys)} polylines", height=20, layer="TITLEBLOCK")
                
                # Move next sheet 2000 ft to the right
                if max_e != -1e18:
                    offset_e = max_e + 2000.0
                else:
                    offset_e += 3000.0
                    
            # Save the DXF
            base_name = os.path.splitext(os.path.basename(pdf))[0]
            out_path = os.path.join(output_dir, f"{base_name}_vectorized.dxf")
            dxf.save(out_path)
            print(f"Saved -> {out_path}")
                    
        except Exception as e:
            print(f"Error converting {pdf}: {e}")
            
    # Cleanup
    if os.path.exists(temp_img_dir):
        shutil.rmtree(temp_img_dir)

if __name__ == "__main__":
    plats_directory = "Plat"
    process_plats(plats_directory)
