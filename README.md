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

In addition to the Python dependencies, you must install some system libraries for full metadata support:

#### macOS

```sh
brew install inih exiv2
```

#### Linux

```sh
sudo apt-get update
sudo apt-get install libexiv2-dev libinih-dev
```

> If you encounter issues with `pyexiv2`, ensure both `exiv2` and `inih` libraries are installed and available on your system.

## Running the Script

To run the script, and view the main menu, use:

```bash
python3 -m run
```

Make sure you have all required dependencies installed before running the script.

## Functions

### Photographs

#### Renaming

You can rename your photo files for better organization, using either the date from the photo's metadata (for digital photos) or a date you provide (for scanned film photos):

- **Digital photos:**  
  Choose "Rename Photographs to Standard Format" from the menu, select "Digital", and follow the prompts. The script will automatically extract the date from EXIF metadata, filenames, or file timestamps.

- **Film scans:**  
  Choose "Rename Photographs to Standard Format", select "Film", and enter the date when prompted (since film scans usually lack metadata). The script will use this date for renaming.

Both options let you include subfolders, RAW files, and add a custom suffix to filenames. Duplicate filenames are avoided by adding counters.

> **Note:** Supported file extensions and EXIF tag mappings are managed in `run/config.py`.

#### Burning In Metadata

To add a visible date and optional text onto your photos:

- Choose "Burn-in Information to Photographs" from the menu.
- Enter the image or folder path, output location (or leave blank to overwrite), and any custom text.
- You can use the detected date or provide your own.
- The date and text will appear in the bottom-right corner of each photo.

This works for single images or entire folders, and supports processing subfolders if you choose.

#### Exporting Image Metadata

You can export metadata from your images to a CSV or JSON file for archival or analysis:

- Choose "Export Image Metadata to a CSV or JSON File" from the menu.
- Enter the folder path containing your images.
- Choose whether to include subdirectories.
- Specify the output directory and the desired export format (`csv`, `json`, or `both`).
- The script will extract file information and EXIF metadata and save it to the specified location.

#### Importing (Rewriting) Metadata

You can rewrite image metadata from a previously exported CSV or JSON file:

- Choose "Import Image Metadata from a CSV or JSON File" from the menu.
- Enter the path to your metadata file (CSV or JSON).
- Confirm the file and specify the folder containing the images to update.
- The script will attempt to update EXIF, IPTC, and XMP metadata for matching files.

> **Note:** For full metadata support, ensure all system dependencies are installed as described above.  
> The mapping of EXIF tags to their internal names is handled in `run/config.py` and does not require alteration.

