import os
import re
import sys
import textwrap
from traceback import print_exc
from urllib.parse import urlparse

from download import download_url
from config import AUDIO_FORMAT_MAP, AUDIO_QUALITY_MAP, VERBOSITY_MAP
from preference_manager import save_preferences, user_prefs
from constants import c, SAVED, ERROR, WARN, SUCC
from dataclasses import dataclass
from credential_manager import save_to_env


if sys.platform == "win32":
    os.system("color")

# TODO ensure all prints end in a `.`
# TODO implement an h option which will print what the setting does
# TODO enforce that all printed lines fit in 50 chars (maybe 80)
@dataclass
class DownloadSettings:
	download_dir: str
	audio_format: str
	audio_quality: str

def print_default_invalid_input():
	print(f"{ERROR} Invalid choice. Please enter a valid option\n")

def print_main_options():
	menu_text = textwrap.dedent(f"""
			=== Spotify Downloader ===
			\t1. Download tracks from Spotify
			\t2. Change/Set Preferences
			\tb. Exit Program""").strip()
	print(menu_text)

def prompt_download_dir(current_value, is_preference=False):
	"""Handles the UI and input collection for a download path."""
	while True:
		title = "Change Download Location Preference" if is_preference else "Select Session Download Location"
		max_display_length = 50 - len("Current Setting: ")
		display_dir = "Not Set" if not current_value else (
				f"...{current_value[-max_display_length+3:]}" if len(current_value) > max_display_length else current_value)

		menu_lines = [
			f"--- {c.blue(title, b=True)} ---",
			*([f"Current Setting: {c.cyan(display_dir)}"] if is_preference else []),
			"Enter your preferred download location (full path) or",
			*(["\tr. Reset Preference"] if is_preference else []),
			"\tb. Back"
		]

		print(textwrap.dedent("\n".join(menu_lines)).strip())
		choice = input("> ").strip()

		if choice.lower() in ('b', '') or choice is None:
			return "back"
		elif choice.lower() == 'r' and is_preference:
			return "reset"
		elif choice:
			return choice
		else:
			print(f"{ERROR} Path cannot be empty.")

def prompt_audio_format(current_value, is_preference=False):
	"""Handles the UI and input collection for choosing an audio format."""
	while True:
		title = "Change Audio Format Preference" if is_preference else "Select Session Audio Format"
		curr_label = current_value.label if current_value else "Not Set"

		menu_lines = [
				f"\n--- {c.blue(title, b=True)} ---",
				f"Current Setting: {c.cyan(curr_label)}"
		]
		for num, format_enum in AUDIO_FORMAT_MAP.items():
			status = "" if format_enum.implemented else f" - {c.red("not implemented")}"
			menu_lines.append(f"\t{num}. {format_enum.label} ({c.cyan(format_enum.ext)}){status}")

		if is_preference:
			menu_lines.append(f"\tr. Reset Preference")
		menu_lines.append("\tb. Back")

		print(textwrap.dedent("\n".join(menu_lines)).strip())
		choice = input("> ").strip()

		if choice in AUDIO_FORMAT_MAP:
			format_enum = AUDIO_FORMAT_MAP[choice]
			if not format_enum.implemented:
				print(f"{ERROR} {format_enum.label} is not supported yet.\n")
				continue
			return format_enum
		elif choice.lower() == "r" and is_preference:
			return "reset"
		elif choice.lower() in ("b", "") or choice is None:
			return "back"
		else:
			print_default_invalid_input()

def prompt_audio_quality(current_value, is_preference=False):
	"""Handles the UI and input collection for choosing audio quality."""
	while True:
		title = "Change Audio Quality Preference" if is_preference else "Select Audio Quality for this session"
		curr_label = current_value.label if current_value else "Not Set"

		menu_lines = [
			f"--- {c.blue(title, b=True)} ---",
			f"Current Setting: {c.cyan(curr_label)}"
		]
		for num, quality_enum in AUDIO_QUALITY_MAP.items():
			status = "" if quality_enum.implemented else f" - {c.red('not implemented')}"
			menu_lines.append(f"\t{num}. {quality_enum.label} ({c.cyan(quality_enum.kbps)}){status}")

		if is_preference:
			menu_lines.append("\tr. Reset Preference")
		menu_lines.append("\tb. Back")

		print(textwrap.dedent("\n".join(menu_lines)).strip())
		choice = input("> ").strip()

		if choice in AUDIO_QUALITY_MAP:
			quality_enum = AUDIO_QUALITY_MAP[choice]
			if not quality_enum.implemented:
				print(f"{ERROR} {quality_enum.label} is not supported yet.\n")
				continue
			return quality_enum
		elif choice.lower() == 'r' and is_preference:
			return "reset"
		elif choice.lower() in ('b', '') or choice is None:
			return "back"
		else:
			print_default_invalid_input()

def handle_pre_download_menu():
	download_dir = user_prefs["download_dir"]
	if download_dir is None:
		result = prompt_download_dir(current_value=None, is_preference=False)
		if result == "back": return
		download_dir = result

	audio_format = user_prefs["audio_format"]
	if audio_format is None:
		result = prompt_audio_format(current_value=None, is_preference=False)
		if result == "back": return
		audio_format = result

	audio_quality = user_prefs["audio_quality"]
	if audio_quality is None:
		result = prompt_audio_quality(current_value=None, is_preference=False)
		if result == "back": return
		audio_quality = result

	download_settings = DownloadSettings(download_dir, audio_format, audio_quality) #TODO look into these yellow lines
	handle_download_menu(download_settings)

def print_download_menu(settings):
	# Shorten the save path if it's too long for the UI header
	max_display_length = 50 - len(" > Directory: ")
	save_path = f"...{settings.download_dir[-max_display_length+3:]}" if len(settings.download_dir) > max_display_length else settings.download_dir
	settings_header = textwrap.dedent(f"""
			--- {c.blue("Download", b=True)} ---
			==================================================
			Current Settings:
			 > Format:    {c.cyan(settings.audio_format.label)}
			 > Quality:   {c.cyan(settings.audio_quality.name)}
			 > Directory: {c.cyan(save_path)}
			==================================================""").strip()

	menu_lines = textwrap.dedent("""
			Enter a track, album, or playlist url or
			b. Back""").strip()
	print(f"\n{settings_header}\n{menu_lines}")

def handle_download_menu(settings):
	while True:
		print_download_menu(settings)
		url = input("> ").strip()
		match url:
			case "b" | "B" | '' | None:
				break

			case _ if is_valid_spotify_url(url):
				print(f"{SUCC} Passed URL verification.")
				download_url(url, settings, user_prefs["verbosity"])

			case _:
				print(f"{ERROR} Failed URL verification. Please enter a well-formed open.spotify.com link.")


def print_preferences_menu():
	#TODO add in the current preferences printed on the side in cyan
	menu_text = textwrap.dedent(f"""
			--- {c.blue("Change/Set Preferences", b=True)} ---
			If a preference is set here, when downloading, the preference will be used
			as the default value and you will not be asked for it as input
			\t1. Download Location
			\t2. Audio Format
			\t3. Audio Quality
			\t4. Toggle Main Menu Bypass (Start in Download Menu)
			\t5. Verbosity
			\t6. Spotify API Credentials (.env)
			\t7. {c.red("Spotify session stuff (might happen naturally)")}
			\tr. {c.red("TODO add reset all functionality")}
			\tb. Back""").strip()
	print(menu_text)

def handle_preferences_menu():
	while True:
		print_preferences_menu()
		choice = input("> ").strip()
		match choice:
			case "1":
				handle_download_dir_menu()
			case "2":
				handle_audio_format_menu()
			case "3":
				handle_audio_quality_menu()
			case "4":
				handle_bypass_menu()
			case "5":
				handle_verbosity_menu()
			case "6":
				handle_credentials_menu()
			case "r" | "R":
				pass #TODO
			case "b" | "B" | '' | None:
				break
			case _:
				print_default_invalid_input()


def print_download_dir_menu():
	download_dir = user_prefs["download_dir"]
	if download_dir is None:
		download_dir = "Not Set"
	elif len(download_dir) > 40:
		download_dir = f"...{download_dir[-37:]}"

	menu_lines = textwrap.dedent(f"""
			--- {c.blue("Change Download Location Preference", b=True)} ---
			Current Preference: {c.cyan(download_dir)}
			Enter your preferred download location (full path) or
			r. Reset Preference
			b. Back""").strip()
	print(menu_lines)

def handle_download_dir_menu():
	result = prompt_download_dir(user_prefs["download_dir"], is_preference=True)

	match result:
		case "back":
			pass

		case "reset":
			user_prefs["download_dir"] = None
			save_preferences()
			print(f"{SAVED} Preference cleared.\n")

		case _:  # Returned a valid string path
			user_prefs["download_dir"] = result
			save_preferences()
			print(f"{SAVED} Download location updated to {result}.\n")

def print_audio_format_menu():
	curr_enum = user_prefs["audio_format"]
	curr_label = curr_enum.label if curr_enum else "Not Set"
	menu_lines = [
		f"--- {c.blue("Change Audio Format Preference", b=True)} ---",
		f"Current Preference: {c.cyan(curr_label)}"
	]
	for num, format_enum in AUDIO_FORMAT_MAP.items():
		status = "" if format_enum.implemented else f" - {c.red("not implemented")}"
		menu_lines.append(f"\t{num}. {format_enum.label} ({c.cyan(format_enum.ext)}){status}")
	menu_lines.append("\tr. Reset Preference")
	menu_lines.append("\tb. Back")

	print(textwrap.dedent("\n".join(menu_lines)).strip())

def handle_audio_format_menu():
	result = prompt_audio_format(user_prefs["audio_format"], is_preference=True)

	match result:
		case "back":
			pass

		case "reset":
			user_prefs["audio_format"] = None
			save_preferences()
			print(f"{SAVED} Preference cleared.\n")

		case _:  # Returned a valid format enum
			user_prefs["audio_format"] = result
			save_preferences()
			print(f"{SAVED} Audio format updated to {result.label}.\n")

def print_audio_quality_menu():
	curr_enum = user_prefs["audio_quality"]
	curr_label = curr_enum.label if curr_enum else "Not Set"
	menu_lines = [
		f"--- {c.blue("Change Audio Quality Preference", b=True)} ---",
		f"Current Preference: {c.cyan(curr_label)}"
	]
	for num, quality_enum in AUDIO_QUALITY_MAP.items():
		status = "" if quality_enum.implemented else f" - {c.red("not implemented")}"
		menu_lines.append(f"\t{num}. {quality_enum.label} ({c.cyan(quality_enum.kbps)}){status}")
	menu_lines.append("\tr. Reset Preference")
	menu_lines.append("\tb. Back")

	print(textwrap.dedent("\n".join(menu_lines)).strip())

def handle_audio_quality_menu():
	result = prompt_audio_quality(user_prefs["audio_quality"], is_preference=True)

	match result:
		case "back":
			pass

		case "reset":
			user_prefs["audio_quality"] = None
			save_preferences()
			print(f"{SAVED} Preference cleared.\n")

		case _:  # Returned a valid quality enum
			user_prefs["audio_quality"] = result
			save_preferences()
			print(f"{SAVED} Audio quality updated to {result.label}.\n")

def print_bypass_menu():
	curr_label = "Bypass on" if user_prefs["bypass_main_menu"] else "Bypass off"
	menu_text = textwrap.dedent(f"""
			--- {c.blue("Change Bypass Preference", b=True)} ---
			Current Preference: {c.cyan(curr_label)}
			If bypass is on, you will start in the download menu
			and skip the main menu
			\t1. Bypass On
			\t2. Bypass Off
			\tr. Reset Preference
			\tb. Back""").strip()
	print(menu_text)

def handle_bypass_menu():
	while True:
		print_bypass_menu()
		choice = input("> ").strip()

		match choice:
			case "1":
				user_prefs["bypass_main_menu"] = True
				save_preferences()
				print(f"{SAVED} Bypass updated to On.\n")
				break
			case "2":
				user_prefs["bypass_main_menu"] = False
				save_preferences()
				print(f"{SAVED} Bypass updated to Off.\n")
				break
			case "r" | "R":
				user_prefs["bypass_main_menu"] = False
				save_preferences()
				print(f"{SAVED} Preference cleared (Bypass set to Off).\n")
				break
			case "b" | "B" | '' | None:
				break
			case _:
				print_default_invalid_input()

def print_verbosity_menu():
	curr_enum = user_prefs["verbosity"]
	curr_label = curr_enum.label if curr_enum else "Not Set"

	menu_lines = [
		f"--- {c.blue("Change Verbosity Preference", b=True)} ---",
		f"Current Setting: {c.cyan(curr_label)}"
	]

	for num, verb_enum in VERBOSITY_MAP.items():
		status = "" if verb_enum.implemented else f" - {c.red('not implemented')}"
		menu_lines.append(f"\t{num}. {verb_enum.label} ({c.cyan(verb_enum.desc)}){status}")

	menu_lines.append("\tr. Reset Preference")
	menu_lines.append("\tb. Back")

	print(textwrap.dedent("\n".join(menu_lines)).strip())

def handle_verbosity_menu():
	while True:
		print_verbosity_menu()
		choice = input("> ").strip()

		match choice:
			case c if c in VERBOSITY_MAP: #TODO change use of c
				verb_enum = VERBOSITY_MAP[c]

				if not verb_enum.implemented:
					print(f"{ERROR} {verb_enum.label} is not supported yet.\n")
					continue

				user_prefs["verbosity"] = verb_enum
				save_preferences()
				print(f"{SAVED} Verbosity updated to {verb_enum.label}.\n")
				break

			case "r" | "R":
				user_prefs["verbosity"] = VERBOSITY_MAP["2"] # Default to Medium
				save_preferences()
				print(f"{SAVED} Preference reset to default (Medium).\n")
				break

			case "b" | "B" | '' | None:
				break

			case _:
				print_default_invalid_input()

def print_id_credentials_menu():
	menu_lines = textwrap.dedent(f"""
			--- {c.blue("Set/Change Spotify Credentials", b=True)} ---
			Go to `https://developer.spotify.com/documentation/web-api`
			Once your API App is set up enter the following information:
			Client ID:
			h. Help
			b. Back""").strip()
	print(menu_lines)

def print_secret_credentials_menu():
	menu_lines = textwrap.dedent(f"""
			Client Secret:
			h. Help
			b. Back""").strip()
	print(menu_lines)

def print_redirect_credentials_menu():
	menu_lines = textwrap.dedent(f"""
			Redirect URI:
			b. Back""").strip()
	print(menu_lines)

def print_id_credentials_help(): #TODO figure out why this only uses 1 tab, for a-e, and none for 1-9
	print(textwrap.dedent(f"""
			\t1. Click `Log in`
			\t2. Log in with your Premium Spotify Account
			\t3. Click your username
			\t4. Click `Dashboard`
			\t5. Click `Create app`
			\t6. Under `App name` enter one of the following:
			\t\ta. {c.cyan("`Audio Archive Analytics`")}
			\t\tb. {c.magenta("`Playlist Meta Organizer`")}
			\t\tc. {c.green("`Track Data Visualizer`")}
			\t\td. {c.yellow("`Media Controller Hub`")}
			\t\te. {c.red("`My Python API Project`")}
			\t7. Under `App description` enter the matching description from step 6:
			\t\ta. {c.cyan("`A personal developer tool built to fetch, parse, and organize track metadata and playlist metrics for library optimization.`")}
			\t\tb. {c.magenta("`A personal data analysis utility designed to read streaming history statistics and generate listening data summaries.`")}
			\t\tc. {c.green("`An audio visualization project used to extract track attributes, beats-per-minute, and acoustic features for personal research.`")}
			\t\td. {c.yellow("`A lightweight integration hub to interface local media playback commands with a personal desktop environment.`")}
			\t\te. {c.red("`A private programming sandbox application used for learning REST API integration, authentication flows, and JSON parsing.`")}
			\t8. Under `Redirect URIs` enter `http://127.0.0.1:8080`
			\t9. Click `Save`
			""").strip())

def print_secret_credentials_help():
	print("Click `View client secret`")

#TODO add a print out that the user must click a link after starting for first time (if .cache does not exitst)
#TODO update env vars after creating the env file
#TODO modify this menu so that the user selects each thing to set if not the first time?
def handle_credentials_menu():
	result = handle_id_credentials_menu()
	if result == "back": return

	result = handle_secret_credentials_menu()
	if result == "back": return

	result = handle_redirect_credentials_menu()
	if result == "back": return

	print(f"{SAVED} All API Credentials saved") #TODO remove?

def handle_id_credentials_menu():
	while True:
		print_id_credentials_menu()
		choice = input("> ").strip()

		match choice:
			case "b" | "B" | '' | None:
				return "back"
			case "h" | "H":
				print_id_credentials_help()
			case _ if is_valid_spotify_hex(choice):
				save_to_env("SPOTIPY_CLIENT_ID", choice)
				print(f"{SAVED} Client ID")
				break
			case _:
				print(f"{ERROR} Invalid Client ID format. It must be a 32-character hex string.")

def handle_secret_credentials_menu():
	while True:
		print_secret_credentials_menu()
		choice = input("> ").strip() #TODO replace with password safe input box

		match choice:
			case "b" | "B" | '' | None:
				return "back"
			case "h" | "H":
				print_secret_credentials_help()
			case _ if is_valid_spotify_hex(choice):
				save_to_env("SPOTIPY_CLIENT_SECRET", choice)
				print(f"{SAVED} Client Secret")
				break
			case _:
				print(f"{ERROR} Invalid Client Secret format. It must be a 32-character hex string.")

def handle_redirect_credentials_menu():
	while True:
		print_redirect_credentials_menu()
		choice = input("> ").strip()

		match choice:
			case "b" | "B" | '' | None:
				return "back"
			case _ if is_valid_url(choice):
				save_to_env("SPOTIPY_REDIRECT_URI", choice)
				print(f"{SAVED} Redirect URI")
				break
			case _:
				print(f"{ERROR} Invalid Redirect URI. Please enter a valid URL (e.g., http://localhost:8080).")

def is_valid_spotify_url(url):
	# Not valid if blank/None
	if not url or not isinstance(url, str):
		return False

	# Regex:
	# 1. Matches either a web URL with subdomains (open, www, play) OR the native spotify: protocol
	# 2. Ensures a valid media type path (track, album, playlist, artist, show, episode)
	# 3. Validates the 22-character alphanumeric Spotify ID
	pattern = r"^(?:(https?://(?:open|www|play)\.spotify\.com/(track|album|playlist|episode)/[a-zA-Z0-9]{22}(?:/|\?.*)?)|(spotify:(track|album|playlist|artist|show|episode):[a-zA-Z0-9]{22}))$"
	# pattern = r"^(?:(https?://(?:open|www|play)\.spotify\.com/(track|album|playlist|artist|show|episode)/[a-zA-Z0-9]{22}(?:/|\?.*)?)|(spotify:(track|album|playlist|artist|show|episode):[a-zA-Z0-9]{22}))$"
	return bool(re.match(pattern, url.strip()))

def is_valid_spotify_hex(token):
	"""Spotify Client IDs and Secrets are 32-character lowercase Hexadecimal strings."""
	# Matches exactly 32 alphanumeric hex characters (0-9, a-f)
	return bool(re.match(r"^[0-9a-f]{32}$", token.strip()))

def is_valid_url(url):
	"""Verifies the redirect URI is a syntactically valid web link."""
	try:
		parsed = urlparse(url.strip())
		return all([parsed.scheme, parsed.netloc])
	except Exception:
		return False

#TODO add option to reset credential
#TODO implement artist support ???
def get_input():
	if user_prefs["bypass_main_menu"]:
		handle_pre_download_menu()
	while True:
		print_main_options()
		choice = input("> ").strip()

		match choice:
			case "1":
				handle_pre_download_menu()
			case "2":
				handle_preferences_menu()
			case "b":
				print("Exiting...")
				break
			case _:
					print_default_invalid_input()


if __name__ == '__main__':
	get_input()
