from . import photos
from . import videos


############# Supporting Functions #############

def handle_rename_photos():
    while True:
        film_or_digital = input("Is this for Film or Digital photographs? (f/d): ").strip().lower()
        if film_or_digital in ('f', 'd'):
            break
        print("Invalid selection. Please choose 'f' for Film or 'd' for Digital.")
    if film_or_digital == 'f':
        photos.rename_film()
    else:
        photos.rename_digital()


################ Menu Functions #############


def main_menu() -> str:
    print("\n" + "═" * 50)
    print("📦  Welcome to the Archivist Utility!  📦".center(50))
    print("═" * 50)
    print(" 1. Photographs")
    print(" 2. Videos")
    print(" 3. Exit (More options coming soon!)")
    print("═" * 50)
    return input(" Select an option (1 - 2): ").strip()


def photos_menu() -> str:
    print("\n" + "═" * 50)
    print("🖼️  Photograph Menu  🖼️".center(50))
    print("═" * 50)
    print(" 1. Rename Photographs to Standard Format")
    print(" 2. Burn-in Information to Photographs")
    print(" 3. Export Image Metadata to a CSV or JSON File")
    print(" 4. Import Image Metadata from a CSV or JSON File")
    print(" 5. Restructure Folder Structure")
    print(" 6. Back to Main Menu")
    print(" 7. Exit the Archivist Utility")
    print("═" * 50)

    while True:
        choice = input(" Select an option (1-7): ").strip()
        if choice in ('1', '2', '3', '4', '5', '6', '7'):
            return choice
        print("❌  Invalid selection. Please choose 1, 2, 3, 4, 5, 6, or 7.")


def videos_menu() -> str:
    print("\n" + "═" * 50)
    print("🎥  Video Menu  🎥".center(50))
    print("═" * 50)
    print(" 1. Burn-in Metadata to Videos")
    print(" 2. Back to Main Menu")
    print(" 3. Exit the Archivist Utility")
    print("═" * 50)
    
    while True:
        choice = input(" Select an option (1-3): ").strip()
        if choice in ('1', '2', '3'):
            return choice
        print("❌  Invalid selection. Please choose 1, 2, or 3.")


################ Main Function ################


def main() -> None:
    while True:
        choice = main_menu()
        if choice == '3':
            print("👋  Exiting the Archivist Utility. Goodbye!")
            exit()
        elif choice == '1':
            while True:
                photos_choice = photos_menu()
                if photos_choice == '1':
                    handle_rename_photos()
                elif photos_choice == '2':
                    photos.burn_in_metadata()
                elif photos_choice == '3':
                    photos.export_metadata()
                elif photos_choice == '4':
                    photos.import_metadata()
                elif photos_choice == '5':
                    photos.restructure_folders()
                elif photos_choice == '6':
                    print("Returning to the Main Menu...")
                    break
                elif photos_choice == '7':
                    print("👋  Exiting the Archivist Utility. Goodbye!")
                    exit()
        elif choice == '2':
            while True:
                videos_choice = videos_menu()
                if videos_choice == '1':
                    videos.burn_in_metadata_video()
                elif videos_choice == '2':
                    print("Returning to the Main Menu...")
                    break
                elif videos_choice == '3':
                    print("👋  Exiting the Archivist Utility. Goodbye!")
                    exit()
        else:
            print("❌  Invalid selection. Please choose 1 or 2.")


if __name__ == '__main__':
    main()
