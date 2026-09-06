#!/bin/python3
import os
import sys
import textwrap
import webbrowser

from dotenv import load_dotenv
from librespot.core import Session
from scripts.download import download_url, init_spotify_cred
from scripts.config import AUDIO_FORMAT_MAP, AUDIO_QUALITY_MAP, VERBOSITY_MAP, DuplicateCheckMode, DUPLICATE_CHECK_MAP
from scripts.preference_manager import save_preferences, user_prefs, default_prefs
from scripts.constants import c, SAVED, ERROR, WARN, SUCC, ENV_FILE, CACHE_FILE, CREDENTIALS_FILE
from dataclasses import dataclass
from scripts.credential_manager import save_to_env
from scripts.utils import VALID_FILENAME_KEYWORDS, is_valid_filename_pattern, is_valid_directory_path, \
	is_valid_spotify_hex, is_valid_url, is_valid_spotify_url


if sys.platform == "win32":
	os.system("color")

# TODO ensure all prints end in a `.`
# TODO implement an h option which will print what the setting does
# TODO enforce that all printed lines fit in 50 chars (maybe 80)
# TODO add in user pref, if file exists with different ext, replace, download, or skip (default is to skip)
@dataclass
class DownloadSettings:
	download_dir:         str
	audio_format:         str
	audio_quality:        str
	duplicate_check_mode: DuplicateCheckMode
	generate_m3u:         bool
	filename_format:      str


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

		match choice:
			case "b" | "B" | "" | None:
				return "back"

			case "r" | "R" if is_preference:
				return "reset"

			case _ if choice:
				is_valid, result = is_valid_directory_path(choice)
				if not is_valid:
					print(f"{ERROR} {result}\n")
					continue
				return result

			case _:
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

		match choice:
			case "b" | "B" | "" | None:
				return "back"

			case "r" | "R" if is_preference:
				return "reset"

			case _ if choice in AUDIO_FORMAT_MAP:
				format_enum = AUDIO_FORMAT_MAP[choice]
				if not format_enum.implemented:
					print(f"{ERROR} {format_enum.label} is not supported yet.\n")
					continue
				return format_enum

			case _:
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

		match choice:
			case "b" | "B" | "" | None:
				return "back"

			case "r" | "R" if is_preference:
				return "reset"

			case _ if choice in AUDIO_QUALITY_MAP:
				quality_enum = AUDIO_QUALITY_MAP[choice]
				if not quality_enum.implemented:
					print(f"{ERROR} {quality_enum.label} is not supported yet.\n")
					continue
				return quality_enum

			case _:
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

	duplicate_check_mode = user_prefs["duplicate_check_mode"]
	generate_m3u = user_prefs["generate_m3u"]
	filename_format = user_prefs["filename_format"]

	download_settings = DownloadSettings(download_dir, audio_format, audio_quality, duplicate_check_mode, generate_m3u, filename_format) #TODO look into these yellow lines
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
			case "b" | "B" | "" | None:
				break

			case _ if is_valid_spotify_url(url):
				print(f"{SUCC} Passed URL verification.")
				try:
					download_url(url, settings, user_prefs["verbosity"])
				except Exception as e:
					print(f"{ERROR} Download failed: {e}")

			case _:
				print(f"{ERROR} Failed URL verification. Please enter a well-formed open.spotify.com link.")


def print_preferences_menu():
	download_dir = user_prefs["download_dir"] or "Not Set"
	if len(download_dir) > 30:
		download_dir = f"...{download_dir[-27:]}"

	audio_format_label = user_prefs["audio_format"].label if user_prefs["audio_format"] else "Not Set"
	audio_quality_label = user_prefs["audio_quality"].label if user_prefs["audio_quality"] else "Not Set"
	verbosity_label = user_prefs["verbosity"].label if user_prefs["verbosity"] else "Not Set"
	bypass_label = "On" if user_prefs["bypass_main_menu"] else "Off"
	duplicate_check_label = user_prefs["duplicate_check_mode"].label
	m3u_label = "On" if user_prefs["generate_m3u"] else "Off"
	filename_format_label = user_prefs["filename_format"]

	options = [
		("1. Download Location", download_dir),
		("2. Audio Format", audio_format_label),
		("3. Audio Quality", audio_quality_label),
		("4. Toggle Main Menu Bypass", bypass_label),
		("5. Verbosity", verbosity_label),
		("6. Duplicate Checking", duplicate_check_label),
		("7. Toggle Generate M3U Playlist", m3u_label),
		("8. Change Filename Format", filename_format_label),
	]
	widest_option = max(len(label) for label, _ in options)

	menu_lines = [
		f"--- {c.blue("Change/Set Preferences", b=True)} ---",
		"If a preference is set here, when downloading, the preference will be used",
		"as the default value and you will not be asked for it as input",
	]
	for label, value in options:
		menu_lines.append(f"\t{label:<{widest_option}}  {c.cyan(value)}")

	menu_lines.append(f"\t9. Spotify API Credentials (.env)")
	menu_lines.append(f"\t0. {c.red("Spotify session stuff (might happen naturally)")}")
	menu_lines.append(f"\tr. {c.red("TODO add reset all functionality")}")
	menu_lines.append("\tb. Back")

	print(textwrap.dedent("\n".join(menu_lines)).strip())

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
				handle_duplicate_check_menu()
			case "7":
				handle_generate_m3u_menu()
			case "8":
				handle_filename_menu()
			case "9":
				handle_credentials_menu()
			case "r" | "R":
				pass #TODO
			case "b" | "B" | "" | None:
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
		case "reset":
			user_prefs["download_dir"] = default_prefs["download_dir"]
			save_preferences()
			print(f"{SAVED} Preference cleared.\n")

		case "back":
			pass

		case _:
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
		case "reset":
			user_prefs["audio_format"] = default_prefs["audio_format"]
			save_preferences()
			print(f"{SAVED} Preference cleared.\n")

		case "back":
			pass

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
		case "reset":
			user_prefs["audio_quality"] = default_prefs["audio_quality"]
			save_preferences()
			print(f"{SAVED} Preference cleared.\n")

		case "back":
			pass

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
				user_prefs["bypass_main_menu"] = default_prefs["bypass_main_menu"]
				save_preferences()
				print(f"{SAVED} Preference cleared (Bypass set to Off).\n") #TODO make this print dynamic based on default_prefs
				break

			case "b" | "B" | "" | None:
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
				user_prefs["verbosity"] = default_prefs["verbosity"]
				save_preferences()
				print(f"{SAVED} Preference reset to default (Medium).\n") #TODO make this print dynamic based on default_prefs
				break

			case "b" | "B" | "" | None:
				break

			case _:
				print_default_invalid_input()

def print_duplicate_check_menu():
	curr_label = user_prefs["duplicate_check_mode"].label
	menu_lines = [
		f"--- {c.blue("Change Duplicate Checking Preference", b=True)} ---",
		f"Current Preference: {c.cyan(curr_label)}"
	]
	for num, mode_enum in DUPLICATE_CHECK_MAP.items():
		menu_lines.append(f"\t{num}. {mode_enum.label} - {mode_enum.description}")
	menu_lines.append("\tr. Reset Preference")
	menu_lines.append("\tb. Back")

	print(textwrap.dedent("\n".join(menu_lines)).strip())

def handle_duplicate_check_menu():
	while True:
		print_duplicate_check_menu()
		choice = input("> ").strip()

		match choice:
			case _ if choice in DUPLICATE_CHECK_MAP:
				user_prefs["duplicate_check_mode"] = DUPLICATE_CHECK_MAP[choice]
				save_preferences()
				print(f"{SAVED} Duplicate checking updated to {DUPLICATE_CHECK_MAP[choice].label}.\n")
				break

			case "r" | "R":
				user_prefs["duplicate_check_mode"] = default_prefs["duplicate_check_mode"]
				save_preferences()
				print(f"{SAVED} Preference cleared (set to {default_prefs['duplicate_check_mode'].label}).\n")
				break

			case "b" | "B" | "" | None:
				break
			case _:
				print_default_invalid_input()

def print_generate_m3u_menu():
	curr_label = "Generates M3U playlists" if user_prefs["generate_m3u"] else "Not generating M3U playlists"
	menu_text = textwrap.dedent(f"""
			--- {c.blue("Change Generate M3U Preference", b=True)} ---
			Current Preference: {c.cyan(curr_label)}
			If on, an M3U playlist file listing tracks in album/playlist
			order will be created alongside each download
			\t1. Generate M3U On
			\t2. Generate M3U Off
			\tr. Reset Preference
			\tb. Back""").strip()
	print(menu_text)

def handle_generate_m3u_menu():
	while True:
		print_generate_m3u_menu()
		choice = input("> ").strip()

		match choice:
			case "1":
				user_prefs["generate_m3u"] = True
				save_preferences()
				print(f"{SAVED} Generate M3U updated to On.\n")
				break

			case "2":
				user_prefs["generate_m3u"] = False
				save_preferences()
				print(f"{SAVED} Generate M3U updated to Off.\n")
				break

			case "r" | "R":
				user_prefs["generate_m3u"] = default_prefs["generate_m3u"]
				save_preferences()
				print(f"{SAVED} Preference cleared (set to Off).\n")
				break

			case "b" | "B" | "" | None:
				break

			case _:
				print_default_invalid_input()

def print_filename_menu():
	curr_pattern = user_prefs["filename_format"]
	menu_text = textwrap.dedent(f"""
			--- {c.blue("Change Filename Format Preference", b=True)} ---
			Current Setting: {c.cyan(curr_pattern)}
			Wrap metadata tags in bars, e.g., |artist| - |title|
			Use \\| to write a literal bar '|' or \\\\ for a literal '\\\\'
			\th. Help
			\tr. Reset Preference
			\tb. Back""").strip() #TODO add a line that states that help will show all keywords

	print(menu_text)

def handle_filename_menu():
	while True:
		print_filename_menu()
		choice = input("> ").strip()

		match choice.lower():
			case "h" | "H":
				print_filename_help()
				continue

			case "r" | "R":
				user_prefs["filename_format"] = default_prefs["filename_format"]
				save_preferences()
				print(f"{SAVED} Preference reset to default (|title|).\n")  #TODO make this print dynamic based on default_prefs
				break

			case "b" | "B" | "" | None:
				break

			case _:
				is_valid, error_msg = is_valid_filename_pattern(choice)
				if not is_valid:
					print(f"{ERROR} {error_msg}\n")
					continue

				user_prefs["filename_format"] = choice
				save_preferences()
				print(f"{SAVED} Filename Format updated to {choice}.\n")
				break

def print_filename_help():
	menu_lines = [
		"Use pattern syntax to define how downloaded files are named.",
		f"Wrap metadata tag names in bar symbols: {c.cyan('|keyword|')}\n",
		f"{c.blue('Valid Keywords:', b=True)}"
	]

	for keyword in VALID_FILENAME_KEYWORDS:
		menu_lines.append(f"  • {c.cyan('|' + keyword + '|'):<18}")

	menu_lines.extend([
		f"\n{c.blue('Escape Characters:', b=True)}",
		f"  Use backslash {c.cyan('\\')} to escape standard special tokens:",
		"    \\| -> literal '|'",
		"    \\\\ -> literal '\\'\n",
		f"{c.blue('Example:', b=True)}",
		"  Pattern: {|artist|} --- |year| = |title|",
		"  Result:  {Theo Katzman} --- 2017 = Hard Work"
	])

	print(textwrap.dedent("\n".join(menu_lines)).strip())

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

#TODO update env vars after creating the env file (Is this done, or did I mean a way to update these later)
#TODO modify this menu so that the user selects each thing to set if not the first time?
def handle_credentials_menu():
	""""""
	result = handle_id_credentials_menu()
	if result == "back": return

	result = handle_secret_credentials_menu()
	if result == "back": return

	result = handle_redirect_credentials_menu()
	if result == "back": return

	if os.path.exists(ENV_FILE):
		return True
	else:
		print(f"{ERROR} Setup incomplete: credentials were not saved. Exiting.")
		return False

def handle_id_credentials_menu():
	while True:
		print_id_credentials_menu()
		choice = input("> ").strip()

		match choice:
			case "h" | "H":
				print_id_credentials_help()

			case "b" | "B" | "" | None:
				return "back"

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
			case "h" | "H":
				print_secret_credentials_help()

			case "b" | "B" | "" | None:
				return "back"

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
			case "b" | "B" | "" | None:
				return "back"

			case _ if is_valid_url(choice):
				save_to_env("SPOTIPY_REDIRECT_URI", choice)
				print(f"{SAVED} Redirect URI")
				break

			case _:
				print(f"{ERROR} Invalid Redirect URI. Please enter a valid URL (e.g., http://localhost:8080).")

def handle_spotify_login_menu():
	"""If .cache does not exist, attempt to create it via the user logging into a web browser."""
	load_dotenv(dotenv_path=ENV_FILE, override=True)
	try:
		SC = init_spotify_cred()
		SC.auth_manager.get_access_token(as_dict=False)
	except Exception as e:
		print(f"{ERROR} Spotify login failed: {e}")
		return False
	return True

def handle_streaming_login_menu():
	"""If credentials.json does not exist, run librespot's OAuth flow to create it."""
	def oauth_url_callback(url):
		print("Open this URL in your browser to log in for streaming:")
		print(url)
		webbrowser.open(url)

	conf = Session.Configuration.Builder() \
		.set_store_credentials(True) \
		.set_stored_credential_file(CREDENTIALS_FILE) \
		.build()

	try:
		Session.Builder(conf).oauth(oauth_url_callback).create()
	except Exception as e:
		print(f"{ERROR} Streaming login failed: {e}")
		return False
	return True

def is_first_time_setup():
	"""Checks if all required auth files have been created."""
	return not (os.path.exists(ENV_FILE) and os.path.exists(CACHE_FILE) and os.path.exists(CREDENTIALS_FILE))

def run_first_time_setup():
	""""""
	print(f"--- {c.blue('First-Time Setup', b=True)} ---")

	if not os.path.exists(ENV_FILE):
		print("Step 1: Spotify API Credential")
		handle_credentials_menu()
		if os.path.exists(ENV_FILE):
			print(f"{SAVED} Credentials.")
		else:
			print(f"{ERROR} Setup incomplete: credentials were not saved. Exiting.")
			return False

	if not os.path.exists(CACHE_FILE):
		print("Step 2: Log into Spotify")
		handle_spotify_login_menu()
		if os.path.exists(CACHE_FILE):
			print(f"{SUCC} Spotify login successful.")
		else:
			print(f"{ERROR} Setup incomplete: Spotify login did not complete. Exiting.")
			return False

	if not os.path.exists(CREDENTIALS_FILE):
		print("Step 3: ")
		if not handle_streaming_login_menu():
			return False
		if os.path.exists(CREDENTIALS_FILE):
			print(f"{SUCC} Streaming login successful.")
		else:
			print(f"{ERROR} Setup incomplete: streaming login did not complete. Exiting.")
			return False

	print(f"{SAVED} Setup complete.\n")
	return True


#TODO add option to reset credential
#TODO implement artist support ???
def get_input():
	try:
		if is_first_time_setup():
			if not run_first_time_setup():
				return # Exit program if not fully set up
				#TODO might want to make this open partially functional program if i implement playlist file creation,
				# then the user can do playlist creation still w/o full set up.

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
	except (KeyboardInterrupt, EOFError):
		print(f"\nExiting...")
	except Exception as e:
		print(f"You broke me :(\n{e}")

if __name__ == '__main__':
	get_input()
