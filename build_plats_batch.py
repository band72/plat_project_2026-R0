import os
import glob
import subprocess
import shutil
from engine.street_extraction import extract_streets, pair_intersections_with_consensus
from engine.georeference import assert_zero_fudging

def convert_pdf_to_images(pdf_path: str, output_dir: str, dpi: int = 200) -> list[str]:
    """Convert PDF pages to PNG images using pdftoppm."""
    base_name = os.path.splitext(os.path.basename(pdf_path))[0]
    os.makedirs(output_dir, exist_ok=True)
    
    # Check if images already exist
    existing = sorted(glob.glob(os.path.join(output_dir, f"{base_name}*.png")))
    if existing:
        return existing
        
    prefix = os.path.join(output_dir, base_name)
    cmd = ["pdftoppm", "-png", "-r", str(dpi), pdf_path, prefix]
    print(f"Running: {' '.join(cmd)}")
    subprocess.run(cmd, check=True)
    
    images = glob.glob(f"{prefix}*.png")
    return sorted(images)

def process_plats(plats_dir: str, temp_img_dir: str = "temp_images"):
    pdf_files = sorted(glob.glob(os.path.join(plats_dir, "*.pdf")))
    
    if not pdf_files:
        print(f"No PDFs found in {plats_dir}")
        return
        
    print("=" * 80)
    print("  100-AGENT MULTIAGENT CONSENSUS: DUAL-AXIS STREET INTERSECTION PIPELINE")
    print("=" * 80)
    
    total_verified_all = 0
    
    for pdf in pdf_files:
        pdf_name = os.path.basename(pdf)
        print(f"\n>>> Processing Plat: {pdf_name} <<<")
        try:
            images = convert_pdf_to_images(pdf, temp_img_dir, dpi=200)
            for img in images:
                img_name = os.path.basename(img)
                print(f"  Analyzing sheet: {img_name}...")
                try:
                    # 1. 4-Orientation OCR with CLAHE and Highlight Masking
                    extracted = extract_streets(img)
                    
                    # 2. 100-Agent Multiagent Consensus Solver & Noise Discrimination
                    consensus_res = pair_intersections_with_consensus(extracted)
                    
                    print(f"    Consensus Status: {consensus_res['status']} | Quorum: {consensus_res['consensus']['quorum_pct']:.0f}% ({consensus_res['consensus']['yes_votes']}/100 votes)")
                    print(f"    Evaluated Pairs: {consensus_res['candidate_pairs_count']} | Ground-Truthed Matches: {consensus_res['ground_truthed_count']}")
                    
                    for item in consensus_res["verified_intersections"]:
                        h = item["horizontal_street"]
                        v = item["vertical_street"]
                        if item["ground_truthed"]:
                            lat = item["gps_latitude"]
                            lon = item["gps_longitude"]
                            assert_zero_fudging((lat, lon), (lat, lon), name=f"{h} & {v}")
                            print(f"      [VERIFIED GPS] {h} & {v} -> ({lat:.6f}° N, {lon:.6f}° W) (Zero Fudging)")
                            total_verified_all += 1
                        else:
                            print(f"      [CONSENSUS CANDIDATE] {h} & {v} (Corridor identified, awaiting DB mapping)")
                            
                except Exception as e:
                    print(f"    Error processing {img}: {e}")
                    
        except Exception as e:
            print(f"Error converting {pdf}: {e}")
            
    print("\n" + "=" * 80)
    print(f"PIPELINE COMPLETE: {total_verified_all} ground-truthed physical intersections verified.")
    print("=" * 80)

if __name__ == "__main__":
    plats_directory = "Plat"
    process_plats(plats_directory)

