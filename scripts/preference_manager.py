import json
import os

from scripts.config import AppAudioFormat, AppAudioQuality, AppVerbosity, DuplicateCheckMode
from scripts.constants import ERROR

### Global Variables ###
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
CONFIG_FILE = os.path.join(_PROJECT_ROOT, "..", "config.json")
user_prefs = {}

# Default preferences
default_prefs = {
    "download_dir":         None,
    "audio_format":         None,
    "audio_quality":        None,
	"bypass_main_menu":     False,
	"verbosity":            AppVerbosity.MEDIUM,
	"duplicate_check_mode": DuplicateCheckMode.WORKING_FOLDER,
	"generate_m3u":         False,
	"filename_format":      "|title|",
}

def load_preferences():
	"""Reads config.json, injects missing settings, and converts stored text strings back into Python Enums."""
	global user_prefs
	# If config.json does not exist, create it
	if not os.path.exists(CONFIG_FILE):
		user_prefs = default_prefs.copy()
		save_preferences()

	try:
		with open(CONFIG_FILE, "r") as f:
			data = json.load(f)
	except json.JSONDecodeError:
		# If the file is corrupted in some way, initialize the defaults
		print(f"{ERROR} {CONFIG_FILE} is empty or corrupted. Initializing defaults...")
		user_prefs = default_prefs.copy()
		save_preferences()
		data = user_prefs.copy()

	# Add missing settings
	has_updates = False
	for key, default_val in default_prefs.items():
		if key not in data:
			data[key] = default_val
			has_updates = True

	# If there are updates, save the current settings
	if has_updates:
		user_prefs = data
		save_preferences()

	if data.get("audio_format") is not None:
		try:
			data["audio_format"] = AppAudioFormat[data["audio_format"]]
		except (KeyError, ValueError):
			# If the JSON file was corrupted, reset it to None
			data["audio_format"] = default_prefs["audio_format"]

	if data.get("audio_quality") is not None:
		try:
			data["audio_quality"] = AppAudioQuality[data["audio_quality"]]
		except (KeyError, ValueError):
			# If the JSON file was corrupted, reset it to None
			data["audio_quality"] = default_prefs["audio_quality"]

	if data.get("verbosity") is not None:
		try:
			if not isinstance(data["verbosity"], AppVerbosity):
				data["verbosity"] = AppVerbosity[data["verbosity"]]
		except (KeyError, ValueError):
			# If the JSON file was corrupted, reset it to the default value
			data["verbosity"] = default_prefs["verbosity"]

	if data.get("duplicate_check_mode") is not None:
		try:
			if not isinstance(data["duplicate_check_mode"], DuplicateCheckMode):
				data["duplicate_check_mode"] = DuplicateCheckMode[data["duplicate_check_mode"]]
		except (KeyError, ValueError):
			data["duplicate_check_mode"] = default_prefs["duplicate_check_mode"]

	user_prefs = data

def save_preferences():
	"""Converts Python Enums to text strings and saves user_prefs to config.json."""
	global user_prefs
	serializable_prefs = user_prefs.copy()

	# Convert Enums to raw string value (e.g., AppAudioFormat.OGG -> "ogg")
	if isinstance(serializable_prefs.get("audio_format"), AppAudioFormat):
		serializable_prefs["audio_format"] = serializable_prefs["audio_format"].name

	if isinstance(serializable_prefs.get("audio_quality"), AppAudioQuality):
		serializable_prefs["audio_quality"] = serializable_prefs["audio_quality"].name

	if isinstance(serializable_prefs.get("verbosity"), AppVerbosity):
		serializable_prefs["verbosity"] = serializable_prefs["verbosity"].name

	if isinstance(serializable_prefs.get("duplicate_check_mode"), DuplicateCheckMode):
		serializable_prefs["duplicate_check_mode"] = serializable_prefs["duplicate_check_mode"].name
	# Note: If it is None, it safely stays None (which JSON turns into null)

	with open(CONFIG_FILE, "w") as f:
		json.dump(serializable_prefs, f, indent=4) # indent 4 makes it readable

# Automatically loads settings into memory when this file is imported
load_preferences()