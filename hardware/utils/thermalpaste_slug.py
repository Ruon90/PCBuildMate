import re

import pandas as pd


def slugify(text: str) -> str:
    """Lowercase and replace non-alphanumeric characters with dashes.

    Also strip leading and trailing dashes.
    """
    return re.sub(r"[^a-z0-9]+", "-", str(text).lower()).strip("-")


def add_slugs_to_thermal_paste(input_file, output_file):
    df = pd.read_csv(input_file)

    # Generate slug from name
    df["slug"] = df["name"].apply(slugify)

    df.to_csv(output_file, index=False)
    print(f"Thermal paste file with slugs written to {output_file}")


if __name__ == "__main__":
    add_slugs_to_thermal_paste(
        "data/cooler/thermal-paste.csv", "data/cooler/thermal-paste_slugs.csv"
    )
