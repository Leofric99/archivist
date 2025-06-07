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

METADATA_DATE_KEYS = [
        'SubSecDateTimeOriginal',
        'DateTimeOriginal',
        'SubSecCreateDate',
    ]

import re
import platform
from datetime import datetime
from pathlib import Path
from PIL import Image
from PIL.ExifTags import TAGS

# Define these globally or pass them in if needed
IMAGE_EXTENSIONS = ['.jpg', '.jpeg', '.png', '.heic']
RAW_EXTENSIONS = ['.cr2', '.nef', '.arw', '.dng', '.rw2']
DATETIME_KEYS = [
    'SubSecDateTimeOriginal',
    'DateTimeOriginal',
    'SubSecCreateDate',
    'CreateDate',
    'DateTimeDigitized',
    'DateTime',
]

def rename_digital(folder_path, include_subdirs=False, include_raw=False, custom_suffix="", custom_date=None):

    def convert_windows_path_to_wsl(path_str):
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

    def extract_datetime_from_filename(filename):
        m_full = re.search(r'(\d{8})[_\-]?(\d{6})', filename)
        if m_full:
            try:
                return datetime.strptime(m_full.group(1) + m_full.group(2), "%Y%m%d%H%M%S")
            except Exception:
                pass
        m_date = re.search(r'(\d{8})', filename)
        if m_date:
            try:
                return datetime.strptime(m_date.group(1), "%Y%m%d")
            except Exception:
                pass
        return None

    def get_metadata_datetime(exif_data):
        for key in ['SubSecDateTimeOriginal', 'DateTimeOriginal', 'SubSecCreateDate']:
            if key in exif_data:
                dt = parse_exif_datetime(exif_data[key])
                if dt:
                    return dt
        return None

    if platform.system() == 'Linux' and ':' in folder_path and '\\' in folder_path:
        folder = convert_windows_path_to_wsl(folder_path)
    else:
        folder = Path(folder_path)

    folder = folder.resolve()
    if not folder.is_dir():
        raise ValueError(f"The provided path is not a valid directory: {folder}")

    files = folder.rglob('*') if include_subdirs else folder.iterdir()
    valid_extensions = IMAGE_EXTENSIONS + RAW_EXTENSIONS if include_raw else IMAGE_EXTENSIONS
    custom_suffix = '_'.join(custom_suffix.split()).lower() if custom_suffix else ""

    base_name_to_files = {}

    for file_path in files:
        if not file_path.is_file() or file_path.suffix.lower() not in valid_extensions:
            continue

        try:
            img = Image.open(file_path)
            exif_data = get_exif_data(img)
        except Exception:
            exif_data = {}

        metadata_dt = get_metadata_datetime(exif_data)
        metadata_has_priority_keys = metadata_dt is not None

        filename_dt = extract_datetime_from_filename(file_path.name)
        ctime, mtime = get_file_dates(file_path)

        if custom_date:
            try:
                custom_date_obj = datetime.strptime(custom_date, "%Y%m%d")
            except Exception:
                custom_date_obj = None

            time_part = (
                metadata_dt.strftime('%H%M%S') if metadata_dt else
                mtime.strftime('%H%M%S') if mtime else
                ctime.strftime('%H%M%S') if ctime else
                "000000"
            )

            base_name = f"{custom_date_obj.strftime('%Y%m%d') if custom_date_obj else custom_date}_{time_part}"

        else:
            if filename_dt and not metadata_has_priority_keys:
                if filename_dt.hour == 0 and filename_dt.minute == 0 and filename_dt.second == 0:
                    time_part = (
                        metadata_dt.strftime('%H%M%S') if metadata_dt else
                        mtime.strftime('%H%M%S') if mtime else
                        ctime.strftime('%H%M%S') if ctime else
                        "000000"
                    )
                    base_name = f"{filename_dt.strftime('%Y%m%d')}_{time_part}"
                else:
                    base_name = filename_dt.strftime('%Y%m%d_%H%M%S')
            else:
                chosen_dt = metadata_dt or mtime or ctime
                base_name = chosen_dt.strftime('%Y%m%d_%H%M%S') if chosen_dt else "00000000_000000"

        if custom_suffix:
            base_name = f"{base_name}_{custom_suffix}"

        base_name_to_files.setdefault(base_name, []).append(file_path)

    for base_key, file_list in base_name_to_files.items():
        if len(file_list) == 1:
            file_path = file_list[0]
            new_name = f"{base_key}{file_path.suffix.lower()}"
            new_path = file_path.with_name(new_name)

            counter = 1
            while new_path.exists():
                new_name = f"{base_key} ({counter}){file_path.suffix.lower()}"
                new_path = file_path.with_name(new_name)
                counter += 1

            print(f"Renaming '{file_path.name}' to '{new_name}'")
            file_path.rename(new_path)

        else:
            counter = 1
            for file_path in file_list:
                new_name = f"{base_key}_{counter}{file_path.suffix.lower()}"
                new_path = file_path.with_name(new_name)

                while new_path.exists():
                    counter += 1
                    new_name = f"{base_key}_{counter}{file_path.suffix.lower()}"
                    new_path = file_path.with_name(new_name)

                print(f"Renaming '{file_path.name}' to '{new_name}'")
                file_path.rename(new_path)
                counter += 1


def rename_film(folder_path, include_subdirs=False, include_raw=False, custom_suffix="", custom_date=None):
    def convert_windows_path_to_wsl(path_str):
        match = re.match(r'^([A-Za-z]):\\', path_str)
        if match:
            drive_letter = match.group(1).lower()
            path_str = path_str.replace('\\', '/')
            return Path(f"/mnt/{drive_letter}/{path_str[3:]}")
        return Path(path_str)

    if not custom_date:
        raise ValueError("You must supply a custom_date in the format YYYY or YYYYMM or YYYYMMDD.")

    # Validate custom_date format: must be 4, 6 or 8 digits, and a valid date for each
    valid_lengths = [4, 6, 8]
    if len(custom_date) not in valid_lengths or not custom_date.isdigit():
        raise ValueError("custom_date must be numeric and in the format YYYY or YYYYMM or YYYYMMDD.")

    # Validate the date parts depending on length
    try:
        if len(custom_date) == 4:
            # Only year, check if valid year
            year = int(custom_date)
            if year < 1 or year > 9999:
                raise ValueError
        elif len(custom_date) == 6:
            # Year and month
            datetime.strptime(custom_date, "%Y%m")
        elif len(custom_date) == 8:
            # Full date
            datetime.strptime(custom_date, "%Y%m%d")
    except Exception:
        raise ValueError("custom_date must be a valid date in the format YYYY or YYYYMM or YYYYMMDD.")

    # Convert Windows paths if necessary
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

    files_to_rename = [
        f for f in files
        if f.is_file() and f.suffix.lower() in valid_extensions
    ]

    name_map = defaultdict(list)

    # First pass: group by target base name
    for file_path in files_to_rename:
        ext = file_path.suffix.lower()
        parts = [custom_date]
        if custom_suffix:
            parts.append(custom_suffix)
        base = "_".join(parts)
        name_map[(base, ext)].append(file_path)

    # Second pass: rename files
    for (base, ext), paths in name_map.items():
        if len(paths) == 1:
            # No duplicates – use base name as-is
            new_name = f"{base}{ext}"
            new_path = paths[0].with_name(new_name)

            if new_path.exists():
                # Very unlikely, fallback to numbered
                new_name = f"{base}_1{ext}"
                new_path = paths[0].with_name(new_name)

            print(f"Renaming '{paths[0].name}' to '{new_name}'")
            paths[0].rename(new_path)
        else:
            # Duplicates – number all
            for idx, path in enumerate(sorted(paths), start=1):
                numbered_base = f"{base}_{idx}"
                new_name = f"{numbered_base}{ext}"
                new_path = path.with_name(new_name)

                # In rare case of conflict, keep incrementing
                counter = idx
                while new_path.exists():
                    counter += 1
                    numbered_base = f"{base}_{counter}"
                    new_name = f"{numbered_base}{ext}"
                    new_path = path.with_name(new_name)

                print(f"Renaming '{path.name}' to '{new_name}'")
                path.rename(new_path)
