import platform
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps, ExifTags, TiffImagePlugin
from datetime import datetime
import warnings
import re
import csv
import json
import pyexiv2


#################### CONFIGURATION ################


Image.MAX_IMAGE_PIXELS = None # Disable the limit on image size to prevent DecompressionBombError
warnings.simplefilter('ignore', Image.DecompressionBombWarning)

IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.tiff', '.heic', '.bmp']
RAW_EXTENSIONS = ['.cr2', '.nef', '.arw', '.rw2', '.dng', '.tif']
VIDEO_EXTENSIONS = ['.mp4', '.mov', '.avi', '.mkv', '.wmv', '.mts', '.m2ts', '.3gp', '.webm']


################### SUPPORTING FUNCTIONS ###################


def convert_windows_path_to_wsl(path_str) -> str:
        m = re.match(r'^([A-Za-z]):\\', path_str)
        if m:
            drive = m.group(1).lower()
            replaced = path_str[3:].replace('\\', '/')
            return f"/mnt/{drive}/{replaced}"
        return path_str


def format_datetime(dt) -> str:
    if not dt:
        return ""
    # Use ordinal for day (e.g., 1st, 2nd, 3rd, 4th, etc.)
    ordinal = lambda n: f"{n}{'th' if 10 <= n % 100 <= 20 else {1:'st',2:'nd',3:'rd'}.get(n%10,'th')}"
    return f"{ordinal(dt.day)} {dt.strftime('%B')} {dt.year}"


def format_custom_date(date_str) -> str:
    if not date_str: return ""
    if re.fullmatch(r"\d{8}", date_str):
        try: dt = datetime.strptime(date_str, "%Y%m%d"); return format_datetime(dt)
        except: return date_str
    if re.fullmatch(r"\d{6}", date_str):
        try: dt = datetime.strptime(date_str, "%Y%m"); return f"{dt.strftime('%B')} {dt.year}"
        except: return date_str
    if re.fullmatch(r"\d{4}", date_str): return date_str
    return date_str


def export_json(path, data):

        with open(path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        print(f"Metadata exported to {path} (JSON)")


def export_csv(path, data, fieldnames=None):
    
    if not fieldnames:
        # Use keys from the first item if not provided
        if data:
            fieldnames = list(data[0].keys())
        else:
            fieldnames = []

    with open(path, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        for meta in data:
            row = meta.copy()
            # Convert dict fields to string for CSV compatibility
            for k, v in row.items():
                if isinstance(v, dict):
                    row[k] = str(v)
            writer.writerow(row)
    print(f"Metadata exported to {path} (CSV)")


#################### MAIN OPERATIONAL FUNCTIONS ###################


# Burn-in metadata to photographs with optional custom text and date for longjevity
def burn_in_metadata() -> None:
    print("\n" + "═" * 50)
    print("🔥  Burn-in Metadata to Photographs  🔥".center(50))
    print("═" * 50)
    image_path = input(" Enter path to the image or folder: ").strip()
    output_path = input(" Enter output path (leave blank to overwrite original): ").strip()
    per_photo_suffix = input(" Add suffix to each photo individually? (y/n): ").strip().lower() == 'y'
    custom_text = None if per_photo_suffix else input(" Enter custom text to burn in to all photos: ").strip()
    use_custom_date = input(" Use custom date? (y/n): ").strip().lower() == 'y'
    custom_date = input(" Enter date (YYYYMMDD): ").strip() if use_custom_date else None

    # Convert Windows paths to WSL format if running on Linux
    if platform.system() == 'Linux' and ':' in image_path and '\\' in image_path:
        image_path = convert_windows_path_to_wsl(image_path)
    if output_path and platform.system() == 'Linux' and ':' in output_path and '\\' in output_path:
        output_path = convert_windows_path_to_wsl(output_path)

    # Validate paths
    if Path(image_path).is_dir():
        include_subdirs = input(" Include subdirectories? (y/n): ").strip().lower() == 'y'
    else:
        include_subdirs = False

    # Main image processing logic
    def process_image(in_path, out_path, custom_text=None) -> None:
        try: img = Image.open(in_path); img = ImageOps.exif_transpose(img).convert("RGBA")
        except Exception as e: print(f"Error opening image {in_path}: {e}"); return
        try: raw = img._getexif(); exif = {ExifTags.TAGS.get(k, k): v for k, v in raw.items()} if raw else {}
        except: exif = {}
        dt_obj = None
        for k in ['SubSecDateTimeOriginal', 'DateTimeOriginal', 'SubSecCreateDate']:
            if k in exif:
                for fmt in ('%Y:%m:%d %H:%M:%S.%f', '%Y:%m:%d %H:%M:%S'):
                    try: dt_obj = datetime.strptime(exif[k], fmt); break
                    except: continue
            if dt_obj: break
        if not dt_obj:
            m = re.search(r'(\d{8})[_\-]?(\d{6})', in_path.name)
            if m:
                try: dt_obj = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
                except: pass
            if not dt_obj:
                m = re.search(r'(\d{8})', in_path.name)
                if m:
                    try: dt_obj = datetime.strptime(m.group(1), "%Y%m%d")
                    except: pass
        if not dt_obj:
            stat = in_path.stat()
            dt_obj = datetime.fromtimestamp(stat.st_mtime)
        timestamp = format_custom_date(custom_date) if custom_date else format_datetime(dt_obj)
        display_text = f"{timestamp}{f' | {custom_text}' if custom_text else ''}"
        txt_overlay = Image.new("RGBA", img.size, (255,255,255,0))
        draw = ImageDraw.Draw(txt_overlay)
        font_size = int(min(img.size) * 0.045)
        try: font = ImageFont.truetype("arial.ttf", font_size)
        except: font = ImageFont.load_default()
        text_bbox = draw.textbbox((0,0), display_text, font=font)
        pos = (img.width - (text_bbox[2]-text_bbox[0]) - int(min(img.size)*0.01), img.height - (text_bbox[3]-text_bbox[1]) - int(min(img.size)*0.01))
        for dx in range(-1,2):
            for dy in range(-1,2):
                if (dx or dy) and abs(dx)+abs(dy)<=2:
                    draw.text((pos[0]+dx,pos[1]+dy), display_text, font=font, fill=(0,0,0,255))
        draw.text(pos, display_text, font=font, fill=(255,255,255,160))
        out_file = Path(out_path).with_name(re.sub(r'[ \(\)]', '_', Path(out_path).name))
        Image.alpha_composite(img, txt_overlay).convert("RGB").save(out_file)
        print(f"Burned-in metadata to {out_file}")

    path = Path(image_path)
    if not path.exists(): print(f"Path not found: {image_path}"); return
    if path.is_dir():
        output_folder = Path(output_path) if output_path else None
        if output_folder: output_folder.mkdir(parents=True, exist_ok=True)
        files = path.rglob('*') if include_subdirs else path.glob('*')
        images = [p for p in files if p.suffix.lower() in ['.jpg', '.jpeg', '.png']]
        if not images: print(f"No images found in {image_path}"); return
        for img_path in images:
            out_file = (output_folder / img_path.name) if output_folder else img_path
            if per_photo_suffix:
                try: custom_text = input(f"Enter custom suffix for '{img_path.name}' (leave blank for none): ").strip()
                except EOFError: custom_text = ""
                process_image(img_path, out_file, custom_text if custom_text else None)
            else: process_image(img_path, out_file, custom_text)
    else:
        if not path.suffix.lower() in [".jpg", ".jpeg", ".png"]:
            print(f"File is not a supported image: {image_path}"); return
        out_file = Path(output_path) if output_path else path
        if per_photo_suffix:
            try: custom_text = input(f"Enter custom suffix for '{path.name}' (leave blank for none): ").strip()
            except EOFError: custom_text = ""
            process_image(path, out_file, custom_text if custom_text else None)
        else: process_image(path, out_file, custom_text)


# Rename digital or film photographs based on EXIF data or custom date
def rename_digital() -> None:
    print("\n" + "═" * 50)
    print("🖼️  Rename Digital Photographs  🖼️".center(50))
    print("═" * 50)
    folder_path = input(" Enter folder path: ").strip()
    include_subdirs = input(" Include subdirectories? (y/n): ").strip().lower() == 'y'
    include_raw = input(" Include RAW files? (y/n): ").strip().lower() == 'y'
    custom_suffix = input(" Custom suffix (leave blank for none): ").strip()
    use_custom_date = input(" Use custom date? (y/n): ").strip().lower() == 'y'
    custom_date = input(" Enter date (YYYYMMDD): ").strip() if use_custom_date else None
    include_video = input(" Include videos? (y/n): ").strip().lower() == 'y'

    # Convert Windows paths to WSL format if running on Linux
    folder = convert_windows_path_to_wsl(folder_path) if (platform.system() == 'Linux' and ':' in folder_path and '\\' in folder_path) else folder_path
    folder = Path(folder).resolve()
    if not folder.is_dir(): raise ValueError(f"Not a directory: {folder}")
    files = folder.rglob('*') if include_subdirs else folder.iterdir()
    valid_exts = IMAGE_EXTENSIONS + RAW_EXTENSIONS if include_raw else IMAGE_EXTENSIONS
    if include_video: valid_exts += VIDEO_EXTENSIONS
    custom_suffix = '_'.join(custom_suffix.split()).lower() if custom_suffix else ""
    base_name_to_files = {}
    for file_path in files:
        if not file_path.is_file() or file_path.suffix.lower() not in valid_exts: continue
        # --- Get EXIF or fallback date ---
        try: img = Image.open(file_path); raw = img._getexif(); exif = {ExifTags.TAGS.get(k, k): v for k, v in raw.items()} if raw else {}
        except: exif = {}
        dt = None
        for k in ['SubSecDateTimeOriginal', 'DateTimeOriginal', 'SubSecCreateDate']:
            if k in exif:
                for fmt in ('%Y:%m:%d %H:%M:%S.%f', '%Y:%m:%d %H:%M:%S'):
                    try: dt = datetime.strptime(exif[k], fmt); break
                    except: continue
            if dt: break
        if not dt:
            m = re.search(r'(\d{8})[_\-]?(\d{6})', file_path.name)
            if m:
                try: dt = datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
                except: pass
            if not dt:
                m = re.search(r'(\d{8})', file_path.name)
                if m:
                    try: dt = datetime.strptime(m.group(1), "%Y%m%d")
                    except: pass
        if not dt:
            stat = file_path.stat()
            dt = datetime.fromtimestamp(stat.st_mtime)
        if custom_date:
            try: custom_date_obj = datetime.strptime(custom_date, "%Y%m%d")
            except: custom_date_obj = None
            time_part = dt.strftime('%H%M%S') if dt else "000000"
            base = f"{custom_date_obj.strftime('%Y%m%d') if custom_date_obj else custom_date}_{time_part}"
        elif dt:
            base = dt.strftime('%Y%m%d_%H%M%S')
        else:
            base = "00000000_000000"
        if custom_suffix: base += f"_{custom_suffix}"
        base_name_to_files.setdefault(base, []).append(file_path)

    # Preview changes
    preview = []
    for base, files_list in base_name_to_files.items():
        files_list = sorted(files_list)
        for idx, file_path in enumerate(files_list, start=1):
            suffix = file_path.suffix.lower()
            new_name = f"{base}{f'_{idx}' if len(files_list) > 1 else ''}{suffix}"
            new_path = file_path.with_name(new_name)
            preview.append((file_path, new_path))

    print("\nPlanned renames:")
    for old, new in preview:
        print(f"{old.name} -> {new.name}")

    confirm = input("\nProceed with renaming? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Aborted.")
        return

    for old, new in preview:
        try:
            old.rename(new)
            print(f"Renamed {old.name} -> {new.name}")
        except Exception as e:
            print(f"Failed to rename {old.name}: {e}")


# Rename digital or film photographs based on EXIF data or custom date
def rename_film() -> None:
    print("\n" + "═" * 50)
    print("🎞️  Rename Film Photographs  🎞️".center(50))
    print("═" * 50)
    folder_path = input(" Enter folder path: ").strip()
    include_subdirs = input(" Include subdirectories? (y/n): ").strip().lower() == 'y'
    include_raw = input(" Include RAW files? (y/n): ").strip().lower() == 'y'
    custom_suffix = input(" Custom suffix (leave blank for none): ").strip()
    while True:
        custom_date = input(" 📆  Enter date for all files (YYYYMMDD, YYYYMM, or YYYY): ").strip()
        if custom_date and len(custom_date) in [4, 6, 8] and custom_date.isdigit(): break
        print("❌  Invalid date format. Please enter date as YYYY or YYYYMM or YYYYMMDD.")

    folder = convert_windows_path_to_wsl(folder_path) if (platform.system() == 'Linux' and ':' in folder_path and '\\' in folder_path) else folder_path
    folder = Path(folder).resolve()
    if not folder.is_dir(): raise ValueError(f"Not a directory: {folder}")
    date_str = custom_date.strip()
    if re.fullmatch(r"\d{8}", date_str): fmt = "%Y%m%d"
    elif re.fullmatch(r"\d{6}", date_str): fmt = "%Y%m"
    elif re.fullmatch(r"\d{4}", date_str): fmt = "%Y"
    else: raise ValueError("Invalid date format. Use YYYYMMDD, YYYYMM, or YYYY.")
    try:
        padded = date_str + ("0101" if fmt == "%Y" else "01" if fmt == "%Y%m" else "")
        datetime.strptime(padded, "%Y%m%d")
    except: raise ValueError("Invalid date value. Use YYYYMMDD, YYYYMM, or YYYY.")
    base_name = date_str
    files = folder.rglob('*') if include_subdirs else folder.iterdir()
    valid_exts = IMAGE_EXTENSIONS + RAW_EXTENSIONS if include_raw else IMAGE_EXTENSIONS
    custom_suffix = '_'.join(custom_suffix.split()).lower() if custom_suffix else ""
    if custom_suffix: base_name += f"_{custom_suffix}"
    files_list = sorted([f for f in files if f.is_file() and f.suffix.lower() in valid_exts])
    for idx, file_path in enumerate(files_list, start=1):
        suffix = file_path.suffix.lower()
        new_name = f"{base_name}_{idx}{suffix}" if len(files_list) > 1 else f"{base_name}{suffix}"
        new_path = file_path.with_name(new_name)
        try: file_path.rename(new_path); print(f"Renamed {file_path.name} -> {new_name}")
        except Exception as e: print(f"Failed to rename {file_path.name}: {e}")


# Export metadata from images in a folder to CSV or JSON for longjevity
def export_metadata() -> None:
    print("\n" + "═" * 50)
    print("📤  Export Image Metadata  📤".center(50))
    print("═" * 50)
    folder_path = input(" Enter folder path: ").strip()
    include_subdirs = input(" Include subdirectories? (y/n): ").strip().lower() == 'y'
    output_dir = input(" Enter output directory: ").strip()
    output_formats = input(" Export format? (csv/json/both): ").strip().lower()

    folder = convert_windows_path_to_wsl(folder_path) if (platform.system() == 'Linux' and ':' in folder_path and '\\' in folder_path) else folder_path
    folder = Path(folder).resolve()
    if not folder.is_dir():
        raise ValueError(f"Not a directory: {folder}")

    output_dir = convert_windows_path_to_wsl(output_dir) if (platform.system() == 'Linux' and ':' in output_dir and '\\' in output_dir) else output_dir
    output_dir = Path(output_dir).resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    files = folder.rglob('*') if include_subdirs else folder.iterdir()
    metadata_list = []

    for file_path in files:
        if (
            not file_path.is_file()
            or file_path.suffix.lower() not in IMAGE_EXTENSIONS
        ):
            continue
        try:
            img = Image.open(file_path)
            raw = img._getexif() if hasattr(img, '_getexif') else None
            exif_data = {ExifTags.TAGS.get(k, k): v for k, v in raw.items()} if raw else {}
            # Convert all EXIF values to strings for JSON serialization
            exif_data_str = {k: str(v) for k, v in exif_data.items()}
            date_created = datetime.fromtimestamp(file_path.stat().st_ctime).strftime('%Y-%m-%d %H:%M:%S')
            date_modified = datetime.fromtimestamp(file_path.stat().st_mtime).strftime('%Y-%m-%d %H:%M:%S')
            metadata = {
                'File Name': file_path.name,
                'File Size': file_path.stat().st_size,
                'Date Created': date_created,
                'Date Modified': date_modified,
                'EXIF Data': exif_data_str
            }
            metadata_list.append(metadata)
        except Exception as e:
            print(f"Error processing {file_path.name}: {e}")

    if output_formats == 'json':
        export_json(output_dir / "metadata.json", metadata_list)
    elif output_formats == 'csv':
        export_csv(output_dir / "metadata.csv", metadata_list)
    elif output_formats == 'both':
        export_json(output_dir / "metadata.json", metadata_list)
        export_csv(output_dir / "metadata.csv", metadata_list)
    else:
        print("Unknown format. Please choose 'csv', 'json', or 'both'.")


def rewrite_metadata_from_file() -> None:
    print("\n" + "═" * 50)
    print("✏️  Rewrite Metadata from File (using pyexiv2)  ✏️".center(50))
    print("═" * 50)
    meta_path = input(" Enter path to metadata file (CSV or JSON): ").strip()
    meta_file = Path(meta_path).expanduser().resolve()
    if not meta_file.exists():
        print(f"❌  File not found: {meta_file}")
        return
    if meta_file.suffix.lower() not in ['.csv', '.json']:
        print("❌  File must be a .csv or .json")
        return

    print(f"✅  Found metadata file: {meta_file}")
    confirm = input("Is this the correct file? (y/n): ").strip().lower()
    if confirm != 'y':
        print("Aborted.")
        return

    # Load metadata
    metadata_list = []
    if meta_file.suffix.lower() == '.json':
        with open(meta_file, 'r', encoding='utf-8') as f:
            metadata_list = json.load(f)
    else:
        with open(meta_file, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            for row in reader:
                # Expecting EXIF Data, IPTC Data, XMP Data as dicts or JSON strings
                for key in ['EXIF Data', 'IPTC Data', 'XMP Data']:
                    if key in row and isinstance(row[key], str):
                        try:
                            row[key] = json.loads(row[key])
                        except Exception:
                            row[key] = {}
                metadata_list.append(row)

    # Ask for folder containing images
    img_folder = input(" 📁  Enter folder containing images to update: ").strip()
    img_folder = Path(img_folder).expanduser().resolve()
    if not img_folder.is_dir():
        print(f"❌  Not a directory: {img_folder}")
        return

    # Build lookup for images in folder
    all_files = {f.name: f for f in img_folder.glob('*') if f.is_file()}

    updated = 0
    for meta in metadata_list:
        fname = meta.get('File Name')
        if not fname or fname not in all_files:
            print(f"Skipping {fname}: not found in folder.")
            continue
        img_path = all_files[fname]
        exif_data = meta.get('EXIF Data', {})
        iptc_data = meta.get('IPTC Data', {})
        xmp_data = meta.get('XMP Data', {})

        try:
            img = pyexiv2.Image(str(img_path))
            img.read_metadata()
            # Overwrite EXIF
            for tag, value in exif_data.items():
                img[tag] = value
            # Overwrite IPTC
            for tag, value in iptc_data.items():
                img[tag] = value
            # Overwrite XMP
            for tag, value in xmp_data.items():
                img[tag] = value
            img.write_metadata()
            print(f"Updated all metadata for {fname}")
            updated += 1
        except Exception as e:
            print(f"Failed to update {fname}: {e}")

    print(f"Done. Updated {updated} files.")