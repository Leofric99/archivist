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

    def process_video(in_path, out_path, custom_text=None) -> None:
        dt_obj = get_video_creation_date(in_path)
        if custom_date:
            timestamp = format_custom_date_str(custom_date)
        else:
            timestamp = format_date_with_suffix(dt_obj)
        display_text = f"{timestamp}{f' | {custom_text}' if custom_text else ''}"

        fontfile = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
        # Escape single quotes and colons for ffmpeg drawtext
        safe_text = display_text.replace(":", r'\:').replace("'", r"\'")
        drawtext = (
            f"drawtext=fontfile='{fontfile}':"
            f"text='{safe_text}':"
            "fontcolor=white:fontsize=24:borderw=2:bordercolor=black@0.7:"
            "box=1:boxcolor=black@0.4:boxborderw=5:"
            "x=w-tw-20:y=h-th-20"
        )

        out_file = Path(out_path).with_name(re.sub(r'[ \(\)]', '_', Path(out_path).name))
        out_file.parent.mkdir(parents=True, exist_ok=True)
        cmd = [
            "ffmpeg", "-y", "-i", str(in_path),
            "-vf", drawtext,
            "-codec:a", "copy",
            str(out_file)
        ]
        try:
            subprocess.run(cmd, check=True)
            print(f"Burned-in metadata to {out_file}")
        except subprocess.CalledProcessError as e:
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
