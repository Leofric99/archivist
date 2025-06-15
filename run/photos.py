import os
import platform
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageOps
from datetime import datetime
from PIL.ExifTags import TAGS
import warnings
import re

warnings.simplefilter('ignore', Image.DecompressionBombWarning)

IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.tiff', '.heic', '.bmp']
RAW_EXTENSIONS = ['.cr2', '.nef', '.arw', '.rw2', '.dng', '.tif']


def sanitize_filename(filename):
    return re.sub(r'[ \(\)]', '_', filename)


def get_exif_data(img):
    try:
        raw = img._getexif()
        return {TAGS.get(k, k): v for k, v in raw.items()} if raw else {}
    except Exception:
        return {}


def parse_datetime(val):
    for fmt in ('%Y:%m:%d %H:%M:%S.%f', '%Y:%m:%d %H:%M:%S'):
        try:
            return datetime.strptime(val, fmt)
        except Exception:
            continue
    return None


def extract_datetime_from_filename(name):
    m = re.search(r'(\d{8})[_\-]?(\d{6})', name)
    if m:
        try: return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
        except: pass
    m = re.search(r'(\d{8})', name)
    if m:
        try: return datetime.strptime(m.group(1), "%Y%m%d")
        except: pass
    return None


def get_file_dates(path):
    stat = path.stat()
    ctime = datetime.fromtimestamp(stat.st_ctime)
    mtime = datetime.fromtimestamp(stat.st_mtime)
    return ctime, mtime


def find_datetime_for_file(file_path, exif_data, custom_date=None):
    keys = ['SubSecDateTimeOriginal', 'DateTimeOriginal', 'SubSecCreateDate']
    metadata_dt = next((parse_datetime(exif_data.get(k, "")) for k in keys if k in exif_data), None)
    filename_dt = extract_datetime_from_filename(file_path.name)
    ctime, mtime = get_file_dates(file_path)
    if custom_date:
        try: custom_date_obj = datetime.strptime(custom_date, "%Y%m%d")
        except: custom_date_obj = None
        time_part = (metadata_dt or mtime or ctime).strftime('%H%M%S') if (metadata_dt or mtime or ctime) else "000000"
        return f"{custom_date_obj.strftime('%Y%m%d') if custom_date_obj else custom_date}_{time_part}"
    if filename_dt and not metadata_dt:
        if filename_dt.hour == 0 and filename_dt.minute == 0 and filename_dt.second == 0:
            time_part = (metadata_dt or mtime or ctime).strftime('%H%M%S') if (metadata_dt or mtime or ctime) else "000000"
            return f"{filename_dt.strftime('%Y%m%d')}_{time_part}"
        return filename_dt.strftime('%Y%m%d_%H%M%S')
    chosen_dt = metadata_dt or mtime or ctime
    return chosen_dt.strftime('%Y%m%d_%H%M%S') if chosen_dt else "00000000_000000"


def convert_windows_path_to_wsl(path_str):
    m = re.match(r'^([A-Za-z]):\\', path_str)
    if m:
        drive = m.group(1).lower()
        return Path(f"/mnt/{drive}/{path_str[3:].replace('\\', '/')}")
    return Path(path_str)


def burn_in_metadata(image_path, output_path=None, text=None, exif_data=None, custom_date=None, include_subdirs=False):
    def ordinal(n):
        if 10 <= n % 100 <= 20:
            suffix = 'th'
        else:
            suffix = {1: 'st', 2: 'nd', 3: 'rd'}.get(n % 10, 'th')
        return f"{n}{suffix}"

    def format_datetime(dt):
        if not dt:
            return ""
        day = dt.day
        month = dt.strftime("%B")
        year = dt.year
        return f"{ordinal(day)} {month} {year}"

    def process_image(in_path, out_path):
        try:
            img = Image.open(in_path)
            img = ImageOps.exif_transpose(img)  # <-- Correct orientation
            img = img.convert("RGBA")
        except Exception as e:
            print(f"Error opening image {in_path}: {e}")
            return
        local_exif = exif_data or get_exif_data(img)
        dt_obj = None
        keys = ['SubSecDateTimeOriginal', 'DateTimeOriginal', 'SubSecCreateDate']
        for k in keys:
            if k in local_exif:
                dt_obj = parse_datetime(local_exif[k])
                if dt_obj:
                    break
        if not dt_obj:
            filename_dt = extract_datetime_from_filename(in_path.name)
            if filename_dt:
                dt_obj = filename_dt
            else:
                ctime, mtime = get_file_dates(in_path)
                dt_obj = mtime or ctime
        if custom_date:
            try:
                dt_obj = datetime.strptime(custom_date, "%Y%m%d")
            except Exception:
                pass
        timestamp = format_datetime(dt_obj)
        display_text = f"{timestamp}{f' | {text}' if text else ''}"
        txt_overlay = Image.new("RGBA", img.size, (255, 255, 255, 0))
        draw = ImageDraw.Draw(txt_overlay)
        # Increase font size multiplier from 0.035 to 0.045 for slightly larger text
        font_size = int(min(img.size) * 0.045)
        try:
            font = ImageFont.truetype("arial.ttf", font_size)
        except Exception:
            font = ImageFont.load_default()
        text_bbox = draw.textbbox((0, 0), display_text, font=font)
        pos = (img.width - (text_bbox[2] - text_bbox[0]) - int(min(img.size)*0.01),
               img.height - (text_bbox[3] - text_bbox[1]) - int(min(img.size)*0.01))
        # Draw black outline (1-2 pixels thick)
        outline_range = 1  # 1 pixel thick
        for dx in range(-outline_range, outline_range + 1):
            for dy in range(-outline_range, outline_range + 1):
                if (dx != 0 or dy != 0) and abs(dx) + abs(dy) <= 2:
                    draw.text((pos[0] + dx, pos[1] + dy), display_text, font=font, fill=(0, 0, 0, 255))
        # Draw white text
        draw.text(pos, display_text, font=font, fill=(255, 255, 255, 160))
        combined = Image.alpha_composite(img, txt_overlay).convert("RGB")
        out_file = Path(out_path).with_name(sanitize_filename(Path(out_path).name))
        combined.save(out_file)
        print(f"Burned-in metadata to {out_file}")

    path = Path(image_path)
    if not path.exists():
        print(f"Path not found: {image_path}")
        return
    if path.is_dir():
        output_folder = Path(output_path) if output_path else None
        if output_folder: output_folder.mkdir(parents=True, exist_ok=True)
        files = path.rglob('*') if include_subdirs else path.glob('*')
        images = [p for p in files if p.suffix.lower() in ['.jpg', '.jpeg', '.png']]
        if not images:
            print(f"No images found in {image_path}")
            return
        for img_path in images:
            out_file = (output_folder / img_path.name) if output_folder else img_path
            process_image(img_path, out_file)
    else:
        if not path.suffix.lower() in [".jpg", ".jpeg", ".png"]:
            print(f"File is not a supported image: {image_path}")
            return
        out_file = Path(output_path) if output_path else path
        process_image(path, out_file)


def rename_digital(folder_path, include_subdirs=False, include_raw=False, custom_suffix="", custom_date=None):
    folder = convert_windows_path_to_wsl(folder_path) if (platform.system() == 'Linux' and ':' in folder_path and '\\' in folder_path) else Path(folder_path)
    folder = folder.resolve()
    if not folder.is_dir():
        raise ValueError(f"Not a directory: {folder}")
    files = folder.rglob('*') if include_subdirs else folder.iterdir()
    valid_exts = IMAGE_EXTENSIONS + RAW_EXTENSIONS if include_raw else IMAGE_EXTENSIONS
    custom_suffix = '_'.join(custom_suffix.split()).lower() if custom_suffix else ""
    base_name_to_files = {}
    for file_path in files:
        if not file_path.is_file() or file_path.suffix.lower() not in valid_exts:
            continue
        try:
            exif_data = get_exif_data(Image.open(file_path))
        except Exception:
            exif_data = {}
        new_basename = find_datetime_for_file(file_path, exif_data, custom_date)
        if custom_suffix: new_basename += f"_{custom_suffix}"
        base_name_to_files.setdefault(new_basename, []).append(file_path)
    for base_name, files_list in base_name_to_files.items():
        files_list = sorted(files_list)
        for idx, file_path in enumerate(files_list, start=1):
            suffix = file_path.suffix.lower()
            new_name = f"{base_name}{f'_{idx}' if len(files_list) > 1 else ''}{suffix}"
            new_path = file_path.with_name(new_name)
            try:
                file_path.rename(new_path)
                print(f"Renamed {file_path.name} -> {new_name}")
            except Exception as e:
                print(f"Failed to rename {file_path.name}: {e}")


def rename_film(folder_path, include_subdirs=False, include_raw=False, custom_suffix="", custom_date=None):
    folder = convert_windows_path_to_wsl(folder_path) if (platform.system() == 'Linux' and ':' in folder_path and '\\' in folder_path) else Path(folder_path)
    folder = folder.resolve()
    if not folder.is_dir():
        raise ValueError(f"Not a directory: {folder}")
    if custom_date:
        date_str = custom_date.strip()
    else:
        date_str = input("Enter date for all files (YYYYMMDD, YYYYMM, or YYYY): ").strip()
    # Accept YYYYMMDD, YYYYMM, or YYYY
    matched = False
    if re.fullmatch(r"\d{8}", date_str):
        fmt = "%Y%m%d"
        matched = True
    elif re.fullmatch(r"\d{6}", date_str):
        fmt = "%Y%m"
        matched = True
    elif re.fullmatch(r"\d{4}", date_str):
        fmt = "%Y"
        matched = True
    if not matched:
        raise ValueError("Invalid date format. Use YYYYMMDD, YYYYMM, or YYYY.")
    # Validate the date (pad to YYYYMMDD for validation, but don't use it for naming)
    try:
        padded = date_str
        if fmt == "%Y":
            padded += "0101"
        elif fmt == "%Y%m":
            padded += "01"
        datetime.strptime(padded, "%Y%m%d")
    except Exception:
        raise ValueError("Invalid date value. Use YYYYMMDD, YYYYMM, or YYYY.")
    # Use the original user input for the base name (not the padded one)
    base_name = date_str
    files = folder.rglob('*') if include_subdirs else folder.iterdir()
    valid_exts = IMAGE_EXTENSIONS + RAW_EXTENSIONS if include_raw else IMAGE_EXTENSIONS
    custom_suffix = '_'.join(custom_suffix.split()).lower() if custom_suffix else ""
    if custom_suffix:
        base_name += f"_{custom_suffix}"
    files_list = [f for f in files if f.is_file() and f.suffix.lower() in valid_exts]
    files_list = sorted(files_list)
    for idx, file_path in enumerate(files_list, start=1):
        suffix = file_path.suffix.lower()
        new_name = f"{base_name}_{idx}{suffix}" if len(files_list) > 1 else f"{base_name}{suffix}"
        new_path = file_path.with_name(new_name)
        try:
            file_path.rename(new_path)
            print(f"Renamed {file_path.name} -> {new_name}")
        except Exception as e:
            print(f"Failed to rename {file_path.name}: {e}")
