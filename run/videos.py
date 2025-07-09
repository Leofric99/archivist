from run.config import VIDEO_EXTENSIONS
import platform
import re
from pathlib import Path
from datetime import datetime
import subprocess


########### Supporting Functions ###########


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
    return dt.strftime("%Y-%m-%d %H:%M:%S")


def format_custom_date(date_str) -> str:
    if not date_str: return ""
    if re.fullmatch(r"\d{8}", date_str):
        try:
            dt = datetime.strptime(date_str, "%Y%m%d")
            day = dt.day
            suffix = "th" if 11 <= day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
            return dt.strftime(f"%-d{suffix} %B %Y")
        except:
            return date_str
    if re.fullmatch(r"\d{6}", date_str):
        try: dt = datetime.strptime(date_str, "%Y%m"); return dt.strftime("%B %Y")
        except: return date_str
    if re.fullmatch(r"\d{4}", date_str): return date_str
    return date_str


def get_video_creation_date(video_path: Path) -> datetime:
    try:
        cmd = [
            "ffprobe", "-v", "error", "-select_streams", "v:0",
            "-show_entries", "format_tags=creation_time",
            "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)
        ]
        result = subprocess.run(cmd, capture_output=True, text=True)
        date_str = result.stdout.strip()
        if date_str:
            try:
                return datetime.strptime(date_str[:19], "%Y-%m-%dT%H:%M:%S")
            except Exception:
                pass
    except Exception:
        pass
    m = re.search(r'(\d{8})[_\-]?(\d{6})', video_path.name)
    if m:
        try:
            return datetime.strptime(m.group(1) + m.group(2), "%Y%m%d%H%M%S")
        except Exception:
            pass
    m = re.search(r'(\d{8})', video_path.name)
    if m:
        try:
            return datetime.strptime(m.group(1), "%Y%m%d")
        except Exception:
            pass
    stat = video_path.stat()
    return datetime.fromtimestamp(stat.st_mtime)


############ Main Functions ###########


def burn_in_metadata_video() -> None:
    print("\n" + "═" * 50)
    print("🎥  Burn-in Metadata to Videos  🎥".center(50))
    print("═" * 50)
    video_path = input(" Enter path to the video or folder: ").strip()
    output_path = input(" Enter output path (leave blank to overwrite original): ").strip()
    per_video_suffix = input(" Add suffix to each video individually? (y/n): ").strip().lower() == 'y'
    custom_text = None if per_video_suffix else input(" Enter custom text to burn in to all videos: ").strip()
    use_custom_date = input(" Use custom date? (y/n): ").strip().lower() == 'y'
    custom_date = input(" Enter date (YYYYMMDD, YYYYMM, or YYYY): ").strip() if use_custom_date else None

    # Convert Windows paths to WSL format if running on Linux
    if platform.system() == 'Linux' and ':' in video_path and '\\' in video_path:
        video_path = convert_windows_path_to_wsl(video_path)
    if output_path and platform.system() == 'Linux' and ':' in output_path and '\\' in output_path:
        output_path = convert_windows_path_to_wsl(output_path)

    path = Path(video_path)
    if path.is_dir():
        include_subdirs = input(" Include subdirectories? (y/n): ").strip().lower() == 'y'
    else:
        include_subdirs = False

    def format_date_with_suffix(dt: datetime) -> str:
        if not dt:
            return ""
        day = dt.day
        suffix = "th" if 11 <= day <= 13 else {1: "st", 2: "nd", 3: "rd"}.get(day % 10, "th")
        return dt.strftime(f"%-d{suffix} %B %Y")

    def format_custom_date_str(date_str) -> str:
        if not date_str:
            return ""
        if re.fullmatch(r"\d{8}", date_str):
            try:
                dt = datetime.strptime(date_str, "%Y%m%d")
                return format_date_with_suffix(dt)
            except:
                return date_str
        if re.fullmatch(r"\d{6}", date_str):
            try:
                dt = datetime.strptime(date_str, "%Y%m")
                return dt.strftime("%B %Y")
            except:
                return date_str
        if re.fullmatch(r"\d{4}", date_str):
            return date_str
        return date_str

    def detect_gpu_codec() -> tuple:
        # Returns (video_codec, hwaccel_args) or (None, [])
        # Try NVIDIA (h264_nvenc), then Intel (h264_qsv), then AMD (h264_amf)
        # Returns codec and any extra args needed
        try:
            result = subprocess.run(
                ["ffmpeg", "-hide_banner", "-encoders"],
                capture_output=True, text=True, check=True
            )
            encoders = result.stdout
            if "h264_nvenc" in encoders:
                return ("h264_nvenc", [])
            elif "h264_qsv" in encoders:
                return ("h264_qsv", [])
            elif "h264_amf" in encoders:
                return ("h264_amf", [])
        except Exception:
            pass
        return (None, [])

    def process_video(in_path, out_path, custom_text=None) -> None:
        dt_obj = get_video_creation_date(in_path)
        if custom_date:
            timestamp = format_custom_date_str(custom_date)
        else:
            timestamp = format_date_with_suffix(dt_obj)
        display_text = f"{timestamp}{f' | {custom_text}' if custom_text else ''}"

        fontfile = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        # Escape text for ffmpeg drawtext - only escape characters that need it
        # Use double quotes for text and escape double quotes in the display_text
        safe_text = display_text.replace("\\", "\\\\").replace('"', '\\"').replace(":", "\\:")
        drawtext = (
            f'drawtext=fontfile=\'{fontfile}\':'
            f'text="{safe_text}":'
            "fontcolor=white:fontsize=24:borderw=2:bordercolor=black@0.7:"
            "box=1:boxcolor=black@0.4:boxborderw=5:"
            "x=w-tw-20:y=h-th-20"
        )

        # Handle output file path - create temp file if overwriting original
        if str(in_path) == str(out_path):
            # Create temporary file in same directory as original
            temp_suffix = f"_temp_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
            out_file = in_path.with_stem(in_path.stem + temp_suffix)
            is_temp_file = True
        else:
            out_file = Path(out_path).with_name(re.sub(r'[ \(\)]', '_', Path(out_path).name))
            is_temp_file = False
        
        out_file.parent.mkdir(parents=True, exist_ok=True)

        # Detect GPU codec
        video_codec, hwaccel_args = detect_gpu_codec()
        if video_codec:
            print(f"Using GPU acceleration: {video_codec}")
            codec_args = ["-c:v", video_codec]
        else:
            codec_args = ["-c:v", "libx264"]

        cmd = [
            "ffmpeg", "-y", "-i", str(in_path),
            "-vf", drawtext,
            *codec_args,
            "-codec:a", "copy",
            str(out_file)
        ]
        try:
            subprocess.run(cmd, check=True)
            
            # If we created a temp file, replace the original
            if is_temp_file:
                in_path.unlink()  # Remove original
                out_file.rename(in_path)  # Rename temp to original
                print(f"Burned-in metadata to {in_path} (overwritten)")
            else:
                print(f"Burned-in metadata to {out_file}")
        except subprocess.CalledProcessError as e:
            # Clean up temp file if it exists and there was an error
            if is_temp_file and out_file.exists():
                out_file.unlink()
            print(f"Error processing video {in_path}: {e}")

    if not path.exists():
        print(f"Path not found: {video_path}")
        return
    video_exts = [ext.lower() for ext in VIDEO_EXTENSIONS]
    if path.is_dir():
        output_folder = Path(output_path) if output_path else None
        if output_folder:
            output_folder.mkdir(parents=True, exist_ok=True)
        files = path.rglob('*') if include_subdirs else path.glob('*')
        videos = [p for p in files if p.suffix.lower() in video_exts]
        if not videos:
            print(f"No videos found in {video_path}")
            return
        for vid_path in videos:
            out_file = (output_folder / vid_path.name) if output_folder else vid_path
            if per_video_suffix:
                try:
                    custom_text = input(f"Enter custom suffix for '{vid_path.name}' (leave blank for none): ").strip()
                except EOFError:
                    custom_text = ""
                process_video(vid_path, out_file, custom_text if custom_text else None)
            else:
                process_video(vid_path, out_file, custom_text)
    else:
        if not path.suffix.lower() in video_exts:
            print(f"File is not a supported video: {video_path}")
            return
        out_file = Path(output_path) if output_path else path
        if per_video_suffix:
            try:
                custom_text = input(f"Enter custom suffix for '{path.name}' (leave blank for none): ").strip()
            except EOFError:
                custom_text = ""
            process_video(path, out_file, custom_text if custom_text else None)
        else:
            process_video(path, out_file, custom_text)


def rename_videos() -> None:
    print("\n" + "═" * 50)
    print("🎬  Rename Videos  🎬".center(50))
    print("═" * 50)
    folder_path = input(" Enter folder path: ").strip()
    include_subdirs = input(" Include subdirectories? (y/n): ").strip().lower() == 'y'
    custom_suffix = input(" Custom suffix (leave blank for none): ").strip()
    use_custom_date = input(" Use custom date? (y/n): ").strip().lower() == 'y'
    custom_date = input(" Enter date (YYYYMMDD): ").strip() if use_custom_date else None

    # Convert Windows paths to WSL format if running on Linux
    folder = convert_windows_path_to_wsl(folder_path) if (platform.system() == 'Linux' and ':' in folder_path and '\\' in folder_path) else folder_path
    folder = Path(folder).resolve()
    if not folder.is_dir():
        raise ValueError(f"Not a directory: {folder}")
    files = folder.rglob('*') if include_subdirs else folder.iterdir()
    valid_exts = [ext.lower() for ext in VIDEO_EXTENSIONS]
    custom_suffix = '_'.join(custom_suffix.split()).lower() if custom_suffix else ""
    base_name_to_files = {}
    for file_path in files:
        if not file_path.is_file() or file_path.suffix.lower() not in valid_exts:
            continue
        # --- Get video creation or fallback date ---
        dt = get_video_creation_date(file_path)
        if custom_date:
            try:
                custom_date_obj = datetime.strptime(custom_date, "%Y%m%d")
            except:
                custom_date_obj = None
            time_part = dt.strftime('%H%M%S') if dt else "000000"
            base = f"{custom_date_obj.strftime('%Y%m%d') if custom_date_obj else custom_date}_{time_part}"
        elif dt:
            base = dt.strftime('%Y%m%d_%H%M%S')
        else:
            base = "00000000_000000"
        if custom_suffix:
            base += f"_{custom_suffix}"
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
