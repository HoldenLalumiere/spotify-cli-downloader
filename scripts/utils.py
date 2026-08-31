import sys


_ILLEGAL_FILENAME_CHARS_WINDOWS = '<>:"/\\|?*'
_ILLEGAL_FILENAME_CHARS_POSIX = '/'


def _get_illegal_chars():
	"""Returns the set of chars that are illegal in a filename for the current OS."""
	return _ILLEGAL_FILENAME_CHARS_WINDOWS if sys.platform == "win32" else _ILLEGAL_FILENAME_CHARS_POSIX


def sanitize_filename(name):
	"""Removes characters that are illegal on the current OS, trims trailing dots/spaces."""
	illegal_chars = _get_illegal_chars()
	cleaned = "".join(char for char in name if char not in illegal_chars).strip()
	if sys.platform == "win32":
		cleaned.rstrip(".")
	return cleaned