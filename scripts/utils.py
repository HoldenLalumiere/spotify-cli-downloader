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
		cleaned.rstrip(".")
	return cleaned

def format_custom_filename(pattern, metadata):
	"""
	Parses patterns bounded by `|` and replaces valid keywords with metadata values.
	Supports `\\|` for literal OR operator use and `\\\\` for literal backslash use.
	"""
	if not pattern:
		pattern = default_prefs["filename_format"]

	token_re = re.compile(r'\\(\\|\\)|\|([a-zA-Z]+)\|')

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
