import os
import platform
from pathlib import Path
from collections import defaultdict
from datetime import datetime
from PIL.ExifTags import TAGS
from PIL import Image
import warnings
import re

warnings.simplefilter('ignore', Image.DecompressionBombWarning)


IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.tiff', '.heic', '.bmp']
RAW_EXTENSIONS = ['.cr2', '.nef', '.arw', '.rw2', '.dng', '.tif']

# EXIF datetime keys in order of priority
DATETIME_KEYS = [
    'SubSecDateTimeOriginal',
    'DateTimeOriginal',
    'SubSecCreateDate',
    'CreationDate',
    'CreateDate',
    'SubSecMediaCreateDate',
    'MediaCreateDate',
    'DateTimeCreated'
]

def rename(folder_path, include_subdirs=False, include_raw=False, custom_suffix=""):

    def convert_windows_path_to_wsl(path_str):
        # Converts C:\Users\foo to /mnt/c/Users/foo
        match = re.match(r'^([A-Za-z]):\\', path_str)
        if match:
            drive_letter = match.group(1).lower()
            path_str = path_str.replace('\\', '/')
            return Path(f"/mnt/{drive_letter}/{path_str[3:]}")
        return Path(path_str)

    def parse_exif_datetime(value):
        for fmt in ('%Y:%m:%d %H:%M:%S.%f', '%Y:%m:%d %H:%M:%S'):
            try:
                return datetime.strptime(value, fmt)
            except Exception:
                continue
        return None

    def get_exif_data(img):
        exif = {}
        try:
            raw = img._getexif()
            if not raw:
                return exif
            for tag_id, value in raw.items():
                tag = TAGS.get(tag_id, tag_id)
                exif[tag] = value
        except Exception:
            pass
        return exif

    def get_exif_date_taken(path):
        try:
            img = Image.open(path)
            exif_data = get_exif_data(img)
            for key in DATETIME_KEYS:
                if key in exif_data:
                    dt = parse_exif_datetime(exif_data[key])
                    if dt:
                        return dt
        except Exception:
            pass
        return None

    def get_file_dates(path):
        stat = path.stat()
        try:
            ctime = datetime.fromtimestamp(stat.st_ctime)
        except Exception:
            ctime = None
        try:
            mtime = datetime.fromtimestamp(stat.st_mtime)
        except Exception:
            mtime = None
        return ctime, mtime

    # Handle Windows paths if running under WSL or Linux
    if platform.system() in ['Linux'] and ':' in folder_path and '\\' in folder_path:
        folder = convert_windows_path_to_wsl(folder_path)
    else:
        folder = Path(folder_path)

    folder = folder.resolve()

    if not folder.is_dir():
        raise ValueError(f"The provided path is not a valid directory: {folder}")

    files = folder.rglob('*') if include_subdirs else folder.iterdir()

    valid_extensions = IMAGE_EXTENSIONS + RAW_EXTENSIONS if include_raw else IMAGE_EXTENSIONS
    custom_suffix = '_'.join(custom_suffix.split()).lower() if custom_suffix else ""

    for file_path in files:
        if not file_path.is_file() or file_path.suffix.lower() not in valid_extensions:
            continue

        date_taken = get_exif_date_taken(file_path)
        ctime, mtime = get_file_dates(file_path)

        if date_taken:
            chosen_date = date_taken
        elif mtime:
            chosen_date = mtime
        elif ctime:
            chosen_date = ctime
        else:
            base_name = "00000000_000000"

        if date_taken or mtime or ctime:
            base_name = chosen_date.strftime('%Y%m%d_%H%M%S')

        if custom_suffix:
            base_name = f"{base_name}_{custom_suffix}"

        new_name = f"{base_name}{file_path.suffix.lower()}"
        new_path = file_path.with_name(new_name)

        counter = 1
        while new_path.exists():
            new_name = f"{base_name} ({counter}){file_path.suffix.lower()}"
            new_path = file_path.with_name(new_name)
            counter += 1

        print(f"Renaming '{file_path.name}' to '{new_name}'")
        file_path.rename(new_path)