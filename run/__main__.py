from . import photos
import platform
from pathlib import Path

def main_menu():
    # Main loop for the photo utility menu
    while True:
        # Display menu options to the user
        print("\nArchivist Utility Menu:\n")
        print("1. Rename Photographs to Standard Format")
        print("2. Burn-in Information to Photographs")
        print("3. Exit (More to follow...)")

        # Get user input for menu selection
        choice = input("\nSelect an option (1-3): ").strip()

        return choice


def main():

    # Call the main menu function to start the utility
    main_choice = main_menu()

    # If the user selects option 1 for renaming photographs
    if main_choice == '1':

        # Determine if the user is working with Film or Digital photographs
        while True:
            film_or_digital = input("Is this for Film or Digital photographs? (f/d): ").strip().lower()
            if film_or_digital not in ('f', 'd'):
                print("Invalid selection. Please choose 'f' for Film or 'd' for Digital.")
                continue
            break
        
        # If the user is working with Film photographs
        if film_or_digital == 'f':
            
            # Collect user inputs for film renaming
            folder_path = input("Enter folder path: ").strip()
            include_subdirs = input("Include subdirectories? (y/n): ").strip().lower() == 'y'
            include_raw = input("Include RAW files? (y/n): ").strip().lower() == 'y'
            custom_suffix = input("Custom suffix (leave blank for none): ").strip()
            
            # For rename_film, custom_date is mandatory; prompt until valid
            while True:
                custom_date = input("Enter date (YYYY or YYYYMM or YYYYMMDD): ").strip()
                if custom_date and len(custom_date) in [4, 6, 8] and custom_date.isdigit():
                    break
                else:
                    print("Invalid date format. Please enter date as YYYY or YYYYMM or YYYYMMDD.")
            
            # Call rename_film with user inputs
            photos.rename_film(
                folder_path=folder_path,
                include_subdirs=include_subdirs,
                include_raw=include_raw,
                custom_suffix=custom_suffix if custom_suffix else None,
                custom_date=custom_date
            )

        # If the user is working with Digital photographs
        elif film_or_digital == 'd':

            # Collect user inputs for digital renaming
            folder_path = input("Enter folder path: ").strip()
            include_subdirs = input("Include subdirectories? (y/n): ").strip().lower() == 'y'
            include_raw = input("Include RAW files? (y/n): ").strip().lower() == 'y'
            custom_suffix = input("Custom suffix (leave blank for none): ").strip()
            use_custom_date = input("Use custom date? (y/n): ").strip().lower() == 'y'
            if use_custom_date:
                custom_date = input("Enter date (YYYYMMDD): ").strip()
            else:
                custom_date = None
            include_video = input("Include videos? (y/n): ").strip().lower() == 'y'
            if include_video == 'n':
                include_video = False
            elif include_video == 'y':
                include_video = True

            # Call the rename function from the photos module with user parameters
            photos.rename_digital(
            folder_path=folder_path,
            include_subdirs=include_subdirs,
            include_raw=include_raw,
            custom_suffix=custom_suffix,
            custom_date=custom_date,
            include_videos=include_video
            )

    # If the user selects option 2 for burning in metadata
    elif main_choice == '2':

        # Collect user inputs for burning in metadata
        image_path = input("Enter path to the image or folder: ").strip()
        output_path = input("Enter output path (leave blank to overwrite original): ").strip()
        per_photo_suffix = input("Add suffix to each photo individually? (y/n): ").strip().lower() == 'y'
        if per_photo_suffix == 'y':
            per_photo_suffix = True
        elif per_photo_suffix == 'n':
            per_photo_suffix = False
            custom_text = input("Enter custom text to burn in to all photos: ").strip()
        use_custom_date = input("Use custom date? (y/n): ").strip().lower() == 'y'
        if use_custom_date:
            custom_date = input("Enter date (YYYYMMDD): ").strip()
        else:
            custom_date = None

        # Convert Windows path to WSL path if necessary
        if platform.system() == 'Linux' and ':' in image_path and '\\' in image_path:
            image_path = photos.convert_windows_path_to_wsl(image_path)

        if output_path and platform.system() == 'Linux' and ':' in output_path and '\\' in output_path:
            output_path = photos.convert_windows_path_to_wsl(output_path)

        # Ask if folder and include_subdirs
        include_subdirs = False
        if Path(image_path).is_dir():
            include_subdirs = input("Include subdirectories? (y/n): ").strip().lower() == 'y'

        # Call the burn_in_metadata function from the photos module with user parameters
        photos.burn_in_metadata(
            image_path=image_path,
            output_path=output_path if output_path else None,
            text=custom_text if 'custom_text' in locals() and custom_text else None,
            custom_date=custom_date,
            include_subdirs=include_subdirs,
            per_photo_suffix=per_photo_suffix
        )

    # If the user selects option 3 to...
    elif main_choice == '3':
        # Option 3: Exit the menu loop
        print("Exiting. More features coming soon...")
        return

    # If the user selects an invalid option
    else:
        # Handle invalid menu selections
        print("Invalid selection. Please choose 1, 2, or 3.")


if __name__ == '__main__':
    main()
