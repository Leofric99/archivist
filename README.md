# Archivist

[![Source Code](https://img.shields.io/badge/source-GitHub-181717?logo=github)](https://github.com/Leofric99/archivist)

<p align="center">
  <img src="images/archivist.png" alt="Archivist logo" width="500">
</p>

<p align="center">
  <a href="#what-is-archivist">About</a> &nbsp;|&nbsp;
  <a href="#features">Features</a> &nbsp;|&nbsp;
  <a href="#installation">Installation</a> &nbsp;|&nbsp;
  <a href="#running-archivist">Run Archivist</a>
</p>

<h3 align="center">A collection of tools for organizing and preserving photo and video archives.</h3>

## What Is Archivist?

Archivist is a command-line utility for managing photographs and videos. It can standardize filenames using dates, work with image metadata, add visible information to media, and organize files into a consistent folder structure.

## Features

### Photographs

- **Rename photographs:** Standardizes filenames using the date from metadata or user input. Formats filenames as `YYYYMMDD_HHMMSS[_suffix][_{n}].ext` and supports digital and film scans, subfolders, RAW files, and custom suffixes.
- **Burn in information:** Adds a visible date and optional text to photographs, with basic and verbose modes.
- **Manage metadata:** Clone metadata from another photograph, export image metadata to CSV or JSON, and import metadata from a previously exported file.
- **Restructure folders:** Copies photographs and videos into a hierarchy by decade, year, and event, based on filenames in the standard date format.

### Videos

- **Rename videos:** Standardizes video filenames using a detected or custom date, in the format `YYYYMMDD_HHMMSS[_suffix][_{n}].ext`.
- **Burn in metadata:** Adds a visible date and optional text overlay to videos. Requires `ffmpeg` to be installed and available on your system path.

## Installation

Clone the repository and install the Python dependencies:

```bash
git clone https://github.com/Leofric99/archivist.git
cd archivist
pip install -r requirements.txt
```

### System requirements

Install the following system libraries for full metadata and video support:

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

While running on Windows should be possible, using WSL is recommended.

> If you encounter issues importing photo metadata, ensure both `exiv2` and `inih` are installed and available on your system. Video features also require `ffmpeg` on your system path.

## Running Archivist

Start the interactive menu from the repository directory:

```bash
python3 -m run
```

Choose Photographs or Videos from the main menu to access the available tools. Make sure all required Python dependencies and system libraries are installed before running Archivist.
