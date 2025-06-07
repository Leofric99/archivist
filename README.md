# archivist

This script will fulfill all your archiving needs. From renaming and dating photographs to... de determined.

## Installation

Clone the repository and install the required dependencies:

```bash
git clone https://github.com/yourusername/archivist.git
cd archivist
pip install -r requirements.txt
```

## Running the Script

This script performs the main execution logic for the project.

To run the script, use:

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

#### Burning In Metadata

To add a visible date and optional text onto your photos:

- Choose "Burn-in Information to Photographs" from the menu.
- Enter the image or folder path, output location (or leave blank to overwrite), and any custom text.
- You can use the detected date or provide your own.
- The date and text will appear in the bottom-right corner of each photo.

This works for single images or entire folders, and supports processing subfolders if you choose.

