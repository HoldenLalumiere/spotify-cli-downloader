import os
import re
import sys

from scripts.preference_manager import default_prefs

_ILLEGAL_FILENAME_CHARS_WINDOWS = '<>:"/\\|?*'
_ILLEGAL_FILENAME_CHARS_POSIX = '/'

VALID_FILENAME_KEYWORDS = [
    "album",
    "artist",
    "albumartist",
    "title",
    "discnumber",
    "tracknumber",
    "year",
    "id"
]

def _get_illegal_chars():
	"""Returns the set of chars that are illegal in a filename for the current OS."""
	return _ILLEGAL_FILENAME_CHARS_WINDOWS if sys.platform == "win32" else _ILLEGAL_FILENAME_CHARS_POSIX


def sanitize_filename(name):
	"""Removes characters that are illegal on the current OS, trims trailing dots/spaces."""
	illegal_chars = _get_illegal_chars()
	cleaned = "".join(char for char in name if char not in illegal_chars).strip()
	if sys.platform == "win32":
		cleaned = cleaned.rstrip(".")
	return cleaned


def validate_filename_pattern(pattern):
	"""Validates the user entered filename pattern."""
	if not pattern:
		return False, "Pattern cannot be empty" # This will not happen because of the Back functionality

	if re.search(r'(?<!\\)\\(?!\\|\|)', pattern):
		return False, "Invalid escape sequence. Only '\\|' and '\\\\' are supported."

	# Remove all valid uses of \\ and \| so we can check for single |'s
	clean_pattern = pattern.replace(r'\\', '').replace(r'\|', '')
	if clean_pattern.count('|') % 2 != 0:
		return False, "Unbalanced '|' delimiter detected. Ensure all metadata keywords start and end with '|'."

	# Check all keywords
	chunks = clean_pattern.split('|')
	for i in range(1, len(chunks), 2):
		keyword = chunks[i]

		if not keyword:
			return False, "Empty keyword tags (e.g., '||') are not allowed."

		if keyword.lower() not in VALID_FILENAME_KEYWORDS:
			return False, f"Invalid keyword: '|{keyword}|'. Type 'h' for a list of valid keywords."

	return True, ""


def format_custom_filename(pattern, metadata):
	"""
	Parses patterns bounded by `|` and replaces valid keywords with metadata values.
	Supports `\\|` for literal OR operator use and `\\\\` for literal backslash use.
	"""
	if not pattern:
		pattern = default_prefs["filename_format"]

	token_re = re.compile(r'\\(\\|\|)|\|([a-zA-Z]+)\|')

	def replace_token(match_obj):
		escaped_char = match_obj.group(1)
		keyword = match_obj.group(2)

		if escaped_char:
			return escaped_char
		if keyword:
			keyword_lower = keyword.lower()
			if keyword_lower in VALID_FILENAME_KEYWORDS and metadata.get(keyword_lower):
				return str(metadata[keyword_lower])
			return match_obj.group(0)

		return match_obj.group(0)

	result_name = token_re.sub(replace_token, pattern)
	return sanitize_filename(result_name)


def validate_directory_path(path):
	"""Validates the user entered directory path."""
	path = path.strip()
	if not path:
		return False, "Path cannot be empty."

	# Syntax Check: Is it a well-formed path
	try:
		resolved_path = os.path.abspath(path)
	except (ValueError, OSError) as e:
		return False, f"Invalid path: {e}"

	# Windows Checks: Reserved names and illegal characters
	if sys.platform == "win32":
		illegal_chars = '<>"|?*'
		reserved_names = {
			"CON", "PRN", "AUX", "NUL",
			*(f"COM{i}" for i in range(1, 10)),
			*(f"LPT{i}" for i in range(1, 10)),
		}

		for segment in resolved_path.split(os.sep):
			if any(char in segment for char in illegal_chars):
				return False, f"Path contains characters not allowed on Windows: {illegal_chars}"
			if segment.upper() in reserved_names:
				return False, f"'{segment}' is a reserved name on Windows and can't be used as a folder name."

	# Practical Check: If it exists, it must be a directory
	if os.path.exists(resolved_path) and not os.path.isdir(resolved_path):
		return False, f"'{resolved_path}' exists and is not a directory."

	# Practical Check: Is it writable
	nearest_existing = resolved_path
	while not os.path.exists(nearest_existing):
		parent = os.path.dirname(nearest_existing)
		if parent == nearest_existing:
			break # Filesystem root reached
		nearest_existing = parent

	if not os.access(nearest_existing, os.W_OK):
		return False, f"'{nearest_existing}' is not writable."

	return True, resolved_path