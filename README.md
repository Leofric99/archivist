# archivist

This script will fulfill all your archiving needs. From renaming and dating photographs to... de determined.

## Functions

### Photographs

#### Renaming

##### `rename_digital(folder_path, include_subdirs=False, include_raw=False, custom_suffix="", custom_date=None)`

Renames digital photos by date/time from EXIF data, filenames, or file timestamps.

- **Use:** Organize photos by date with optional suffix and subfolder support.
- **Params:**
  - `folder_path`: Folder with images.
  - `include_subdirs`: Include subfolders (default `False`).
  - `include_raw`: Include raw image files (default `False`).
  - `custom_suffix`: Add a suffix to filenames.
  - `custom_date`: Override date with this `YYYYMMDD`.

##### `rename_film(folder_path, include_subdirs=False, include_raw=False, custom_suffix="", custom_date=None)`

Renames scanned film photos using a fixed date you provide.

- **Use:** Rename film scans with your chosen date (year, year+month, or full date).
- **Params:**
  - `folder_path`: Folder with images.
  - `include_subdirs`: Include subfolders (default `False`).
  - `include_raw`: Include raw image files (default `False`).
  - `custom_suffix`: Add a suffix to filenames.
  - `custom_date`: **Required** date string (`YYYY`, `YYYYMM`, or `YYYYMMDD`).

Both functions rename files to avoid overwriting by adding counters when needed.
