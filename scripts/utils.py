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
