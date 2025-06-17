from . import photos


def main_menu() -> str:
    while True:
        print("\nArchivist Utility Menu:\n")
        print("1. Rename Photographs to Standard Format")
        print("2. Burn-in Information to Photographs")
        print("3. Exit (More to follow...)")
        choice = input("\nSelect an option (1-3): ").strip()
        return choice


def main() -> None:
    main_choice = main_menu()
    if main_choice == '1':
        while True:
            film_or_digital = input("Is this for Film or Digital photographs? (f/d): ").strip().lower()
            if film_or_digital not in ('f', 'd'):
                print("Invalid selection. Please choose 'f' for Film or 'd' for Digital.")
                continue
            break
        if film_or_digital == 'f':
            photos.rename_film()
        elif film_or_digital == 'd':
            photos.rename_digital()
    elif main_choice == '2':
        photos.burn_in_metadata()
    elif main_choice == '3':
        print("Exiting. More features coming soon...")
        return
    else:
        print("Invalid selection. Please choose 1, 2, or 3.")


if __name__ == '__main__':
    main()