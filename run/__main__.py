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
            # Option 1: Rename photographs
            folder_path = input("Enter folder path: ").strip()
            include_subdirs = input("Include subdirectories? (y/n): ").strip().lower() == 'y'
            include_raw = input("Include RAW files? (y/n): ").strip().lower() == 'y'
            custom_suffix = input("Custom suffix (leave blank for none): ").strip()
            # Call the rename function from the photos module with user parameters
            photos.rename(
                folder_path=folder_path,
                include_subdirs=include_subdirs,
                include_raw=include_raw,
                custom_suffix=custom_suffix
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
