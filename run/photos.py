import os
import platform
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps, ExifTags
from datetime import datetime
import warnings
import re

# Disable PIL's decompression bomb protection (remove pixel limit)
Image.MAX_IMAGE_PIXELS = None
warnings.simplefilter('ignore', Image.DecompressionBombWarning)

IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.tiff', '.heic', '.bmp']
RAW_EXTENSIONS = ['.cr2', '.nef', '.arw', '.rw2', '.dng', '.tif']
VIDEO_EXTENSIONS = ['.mp4', '.mov', '.avi', '.mkv', '.wmv', '.mts', '.m2ts', '.3gp', '.webm']


def burn_in_metadata():
    # --- User Input ---
    image_path = input("Enter path to the image or folder: ").strip()
    output_path = input("Enter output path (leave blank to overwrite original): ").strip()
    per_photo_suffix = input("Add suffix to each photo individually? (y/n): ").strip().lower() == 'y'
    custom_text = None if per_photo_suffix else input("Enter custom text to burn in to all photos: ").strip()
    use_custom_date = input("Use custom date? (y/n): ").strip().lower() == 'y'
    custom_date = input("Enter date (YYYYMMDD): ").strip() if use_custom_date else None

    # --- Path Conversion for WSL ---
    def convert_windows_path_to_wsl(path_str):
        m = re.match(r'^([A-Za-z]):\\', path_str)
        if m:
            drive = m.group(1).lower()
            return f"/mnt/{drive}/{path_str[3:].replace('\\', '/')}"
        return path_str

    if platform.system() == 'Linux' and ':' in image_path and '\\' in image_path:
        image_path = convert_windows_path_to_wsl(image_path)
    if output_path and platform.system() == 'Linux' and ':' in output_path and '\\' in output_path:
        output_path = convert_windows_path_to_wsl(output_path)

    include_subdirs = Path(image_path).is_dir() and input("Include subdirectories? (y/n): ").strip().lower() == 'y'

    # --- Inline helpers ---
    ordinal = lambda n: f"{n}{'th' if 10 <= n % 100 <= 20 else {1:'st',2:'nd',3:'rd'}.get(n%10,'th')}"
    def format_custom_date(date_str):
        if not date_str: return ""
        if re.fullmatch(r"\d{8}", date_str):
            try: dt = datetime.strptime(date_str, "%Y%m%d"); return f"{ordinal(dt.day)} {dt.strftime('%B')} {dt.year}"
            except: return date_str
        if re.fullmatch(r"\d{6}", date_str):
            try: dt = datetime.strptime(date_str, "%Y%m"); return f"{dt.strftime('%B')} {dt.year}"
            except: return date_str
        if re.fullmatch(r"\d{4}", date_str): return date_str
        return date_str
    def format_datetime(dt): return f"{ordinal(dt.day)} {dt.strftime('%B')} {dt.year}" if dt else ""

    # --- Main image processing logic ---
    def process_image(in_path, out_path, custom_text=None):
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


def rename_digital():
    folder_path = input("Enter folder path: ").strip()
    include_subdirs = input("Include subdirectories? (y/n): ").strip().lower() == 'y'
    include_raw = input("Include RAW files? (y/n): ").strip().lower() == 'y'
    custom_suffix = input("Custom suffix (leave blank for none): ").strip()
    use_custom_date = input("Use custom date? (y/n): ").strip().lower() == 'y'
    custom_date = input("Enter date (YYYYMMDD): ").strip() if use_custom_date else None
    include_video = input("Include videos? (y/n): ").strip().lower() == 'y'

    def convert_windows_path_to_wsl(path_str):
        m = re.match(r'^([A-Za-z]):\\', path_str)
        if m:
            drive = m.group(1).lower()
            return f"/mnt/{drive}/{path_str[3:].replace('\\', '/')}"
        return path_str

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
    for base, files_list in base_name_to_files.items():
        files_list = sorted(files_list)
        for idx, file_path in enumerate(files_list, start=1):
            suffix = file_path.suffix.lower()
            new_name = f"{base}{f'_{idx}' if len(files_list) > 1 else ''}{suffix}"
            new_path = file_path.with_name(new_name)
            try: file_path.rename(new_path); print(f"Renamed {file_path.name} -> {new_name}")
            except Exception as e: print(f"Failed to rename {file_path.name}: {e}")

def rename_film():
    folder_path = input("Enter folder path: ").strip()
    include_subdirs = input("Include subdirectories? (y/n): ").strip().lower() == 'y'
    include_raw = input("Include RAW files? (y/n): ").strip().lower() == 'y'
    custom_suffix = input("Custom suffix (leave blank for none): ").strip()
    while True:
        custom_date = input("Enter date for all files (YYYYMMDD, YYYYMM, or YYYY): ").strip()
        if custom_date and len(custom_date) in [4, 6, 8] and custom_date.isdigit(): break
        print("Invalid date format. Please enter date as YYYY or YYYYMM or YYYYMMDD.")

    def convert_windows_path_to_wsl(path_str):
        m = re.match(r'^([A-Za-z]):\\', path_str)
        if m:
            drive = m.group(1).lower()
            return f"/mnt/{drive}/{path_str[3:].replace('\\', '/')}"
        return path_str

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