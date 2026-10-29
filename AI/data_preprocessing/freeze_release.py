"""The original baseline is frozen. Validate the current published release."""
from manage import selected_release

def freeze():
    release, metadata = selected_release()
    raise FileExistsError(f"Release {metadata['version']} is immutable at {release}; publish a distinct release instead")

if __name__ == '__main__': freeze()
