_ILLEGAL_FILENAME_CHARS = '<>:"/\\|?*'

def sanitize_filename(name):
	"""Removes characters that are illegal in Windows filenames, trims trailing dots/spaces."""
	cleaned = "".join(char for char in name if char not in _ILLEGAL_FILENAME_CHARS)
	return cleaned.strip().rstrip(".")