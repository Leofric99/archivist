# archivist

This script will fulfill all your archiving needs. From renaming and dating photographs to... be determined. More tools to follow.

## Installation

Clone the repository and install the required dependencies:

```bash
git clone https://github.com/Leofric99/archivist.git
cd archivist
pip install -r requirements.txt
```

### System Requirements

In addition to the Python dependencies, you must install some system libraries for full metadata and video support:

#### macOS

```sh
brew install inih exiv2 ffmpeg
```

#### Linux

```sh
sudo apt-get update
sudo apt-get install libexiv2-dev libinih-dev ffmpeg
```

#### Windows

While running on Windows should be possible, I recommend using WSL.

> If you encounter issues with importing photo metadata, ensure both `exiv2` and `inih` libraries are installed and available on your system.
>  
> For video features, you must also have `ffmpeg` installed and accessible from your system path.

## Running the Script

To run the script, and view the main menu, use:

```bash
python3 -m run
```

Make sure you have all required dependencies installed before running the script.

## Functions

### Photographs

- **Renaming:**  
  Standardizes photo filenames using the date from metadata or user input. Formats as `YYYYMMDD_HHMMSS[_suffix][_{n}].ext`. Supports digital and film scans, subfolders, RAW files, and custom suffixes.

- **Burning In Metadata:**  
  Adds a visible date and optional text to the bottom-right corner of photos. Works for single images or folders.

- **Exporting Metadata:**  
  Exports image metadata (EXIF, etc.) to CSV or JSON for archival or analysis.

- **Importing Metadata:**  
  Rewrites image metadata from a previously exported CSV or JSON file.

- **Restructuring Folders:**  
  Organizes photos and videos into a hierarchy by decade, year, and event (based on filename: `YYYYMMDD_HHMMSS_suffix.ext`). Copies files into a new structure.

### Videos

- **Renaming:**  
  Standardizes video filenames using detected or custom date. Format: `YYYYMMDD_HHMMSS[_suffix][_{n}].ext`.

- **Burning In Metadata:**  
  Adds a visible date and optional text overlay to videos (bottom-right corner). Requires `ffmpeg` to be installed and available in your system path.

