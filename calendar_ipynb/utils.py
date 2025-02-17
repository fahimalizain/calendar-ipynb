import os

PACKAGE_ROOT = os.path.abspath(
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
)


def get_temp_path(filename: str):
    return os.path.join(PACKAGE_ROOT, "temp", filename)
