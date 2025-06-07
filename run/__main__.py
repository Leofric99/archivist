from . import photos

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

        if choice == '1':

            film_or_digital = input("Is this for Film or Digital photographs? (f/d): ").strip().lower()
            if film_or_digital not in ('f', 'd'):
                print("Invalid selection. Please choose 'f' for Film or 'd' for Digital.")
                continue
            
            if film_or_digital == 'f':
                
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
                    custom_suffix=custom_suffix,
                    custom_date=custom_date
                )

            elif film_or_digital == 'd':

                # Option 1: Rename photographs
                folder_path = input("Enter folder path: ").strip()
                include_subdirs = input("Include subdirectories? (y/n): ").strip().lower() == 'y'
                include_raw = input("Include RAW files? (y/n): ").strip().lower() == 'y'
                custom_suffix = input("Custom suffix (leave blank for none): ").strip()
                use_custom_date = input("Use custom date? (y/n): ").strip().lower() == 'y'
                if use_custom_date:
                    custom_date = input("Enter date (YYYYMMDD): ").strip()
                else:
                    custom_date = None
                # Call the rename function from the photos module with user parameters
                photos.rename_digital(
                folder_path=folder_path,
                include_subdirs=include_subdirs,
                include_raw=include_raw,
                custom_suffix=custom_suffix,
                custom_date=custom_date
                )

        elif choice == '2':
            # Option 2: Burn-in information (not yet implemented)
            print("Feature not yet implemented: Burn-in Information to Photographs.")
            # Placeholder for future implementation

        elif choice == '3':
            # Option 3: Exit the menu loop
            print("Exiting. More features coming soon...")
            break

        else:
            # Handle invalid menu selections
            print("Invalid selection. Please choose 1, 2, or 3.")


if __name__ == '__main__':
    main_menu()
