import os
import sys
import time
import base64
import random
import spotipy
import tempfile
import requests
import subprocess
import imageio_ffmpeg

from dotenv import load_dotenv
from scripts.config import AppAudioFormat, DuplicateCheckMode
from scripts.m3u_generator import generate_m3u
from scripts.utils import sanitize_filename, format_custom_filename, _get_url_id
from spotipy.oauth2 import SpotifyOAuth
from librespot.core import Session
from librespot.metadata import TrackId, EpisodeId
from librespot.audio.decoders import VorbisOnlyAudioQuality
from mutagen.flac import FLAC, Picture
from mutagen.oggvorbis import OggVorbis
from mutagen.mp4 import MP4, MP4Cover
from mutagen.easyid3 import EasyID3
from mutagen.id3 import ID3NoHeaderError, ID3, APIC
from mutagen.mp3 import MP3
from scripts.constants import c, SAVED, ERROR, WARN, SUCC, WAIT, CACHE_FILE, ENV_FILE, CREDENTIALS_FILE
from scripts.preference_manager import AppVerbosity

# TODO add in extra prints if high verbosity
# TODO add lyric download and metadata addition
# TODO manually generate an M3U for masayoshi and DKC
# TODO Generate playlist file based on folder
# TODO Look at duplicate checking to see if there is a more concrete way to check if they are the same audio
# TODO See if tracks have an associated album
def init_spotify_cred():
	"""Initializes Spotipy with user authentication credentials."""
	return spotipy.Spotify(auth_manager=SpotifyOAuth(
			client_id=os.getenv("SPOTIPY_CLIENT_ID"),
			client_secret=os.getenv("SPOTIPY_CLIENT_SECRET"),
			redirect_uri=os.getenv("SPOTIPY_REDIRECT_URI"),
			scope="playlist-read-private",
			cache_path=CACHE_FILE
	))


def _verify_ffmpeg_available():
	"""Checks if the bundled ffmpeg binary is usable"""
	try:
		ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
		if not os.path.exists(ffmpeg_path):
			raise FileNotFoundError(ffmpeg_path)
		return ffmpeg_path
	except Exception as e:
		print(f"{ERROR} ffmpeg binary unavailable {e}. Only {AppAudioFormat.OGG.ext} downloads will work right now.")
		return None


### Global variables ###
# Load vars from .env system memory
load_dotenv(dotenv_path=ENV_FILE)
# Set up Spotify API listening credentials
SPOTIFY_STREAM_SESSION = None
SC = None
# FFmpeg
_FFMPEG_PATH = _verify_ffmpeg_available()
# librespot
_SESSION_CONF = Session.Configuration.Builder() \
	.set_store_credentials(True) \
	.set_stored_credential_file(CREDENTIALS_FILE) \
	.build()

#TODO add blue to main menu
#TODO if someone Ctrl+C's or exits the program in some way, exit gracefully instead of displaying a code crash
def _get_stream_session(verbosity):
	"""Returns the current stream session, or builds a fresh one if dropped/idle."""
	global SPOTIFY_STREAM_SESSION
	if SPOTIFY_STREAM_SESSION is None or not SPOTIFY_STREAM_SESSION.is_valid():
		if verbosity != AppVerbosity.LOW:
			print(f"{WAIT} Establishing active Spotify streaming connection...")

		SPOTIFY_STREAM_SESSION = Session.Builder(_SESSION_CONF).stored_file().create()

		if verbosity != AppVerbosity.LOW:
			print(f"{SUCC} Connection established.")
	return SPOTIFY_STREAM_SESSION


def _get_auth_token(): #TODO is this needed? currently unused.
	try:
		token_info = SC.auth_manager.get_access_token(as_dict=False)
		if isinstance(token_info, dict):
			return token_info.get("access_token")
		return token_info
	except Exception:
		return None


class DownloadProcessor:
	"""Handles the lifecycle of a download request."""

	def __init__(self, url, download_settings, verbosity):
		self.url = url
		# Save the dataclass instance containing user choices
		self.settings = download_settings
		self.verbosity = verbosity

	def start(self):
		url_type = self.url.split("/")[-2]
		download_dir = self.settings.download_dir
		original_dir = os.getcwd()

		global SC
		match url_type:
			case "playlist" | "album":
				SC = init_spotify_cred()
				metadata_list, collection_name = _get_collection_metadata(self.url, url_type)
				self._download_collection(collection_name, metadata_list, download_dir, original_dir)

			# TODO episode downloading does not work currently
			# TODO catch/supress this message somehow: Failed reading packet! Failed to receive packet
			case "track" | "episode":
				SC = init_spotify_cred()
				os.chdir(download_dir)
				try:
					metadata = _get_item_metadata(self.url, url_type)
					match url_type:
						case "track":
							super_title = metadata["album"]
						case "episode":
							super_title = metadata["artist"]
						case _:
							raise Exception("Unknown URL type") # This should never happen

					self.file_ext = self.settings.audio_format.ext.lower().strip()
					self.filename_lookup = {metadata["id"]: format_custom_filename(self.settings.filename_format, metadata)}
					self.collection_path = download_dir

					_get_stream_session(self.verbosity)
					print(f"Downloading: {super_title} - {metadata["title"]}")
					self.download_item(metadata, url_type)
				finally:
					os.chdir(original_dir)

			case _:
				raise Exception("Unknown URL type") # This should never happen

		print(f"{SUCC} Download sequence completed.")

	def _download_collection(self, collection_name, metadata_list, download_dir, original_dir):
		total_tracks = len(metadata_list)
		width = len(str(total_tracks))
		safe_collection_name = sanitize_filename(collection_name)

		# Change directory to that collection in their preferred download directory
		self.collection_path = os.path.join(download_dir, safe_collection_name)
		folder_exists = os.path.exists(self.collection_path)
		os.makedirs(self.collection_path, exist_ok=True)
		os.chdir(self.collection_path)
		if not folder_exists:
			print(f"{SUCC} Created folder: {os.getcwd()}")

		self.file_ext = self.settings.audio_format.ext.lower().strip()

		match self.settings.duplicate_check_mode:
			case DuplicateCheckMode.ALL_FOLDERS:
				existing_file_index = _build_file_index(download_dir)
			case DuplicateCheckMode.WORKING_FOLDER:
				existing_file_index = _build_file_index(self.collection_path)
			case DuplicateCheckMode.DO_NOT_CHECK:
				existing_file_index = {}

		_get_stream_session(self.verbosity)

		# Download the items in a randomized order to avoid a predictable sequential request pattern.
		# Need to keep metadata_list in order though for M3U generation and the progress bar
		download_order = list(enumerate(metadata_list, start=1))
		random.shuffle(download_order)

		download_count = 0
		processed_count = 0
		self.filename_lookup = {}
		self.m3u_path_overrides = {}
		try:
			for index, metadata in download_order:
				processed_count += 1
				formatted_filename = format_custom_filename(self.settings.filename_format, metadata)
				self.filename_lookup[metadata["id"]] = formatted_filename

				# Check if the file is already downloaded
				dupe_key = (metadata["artist"], metadata["title"])
				already_downloaded = dupe_key in existing_file_index

				if already_downloaded:
					if self.settings.generate_m3u:
						existing_path = existing_file_index[dupe_key]
						if os.path.dirname(existing_path) != self.collection_path:
							self.m3u_path_overrides[metadata["id"]] = existing_path

					if self.verbosity != AppVerbosity.LOW:
						print(f"{c.magenta(f"[{processed_count:>{width}}/{total_tracks}]")} Skipping: {metadata['artist']} - {metadata['title']}")
					else:
						self.update_download_progress(index, total_tracks, metadata)
					continue

				if self.verbosity != AppVerbosity.LOW:
					print(f"{c.cyan(f"[{processed_count:>{width}}/{total_tracks}]")} Downloading: {metadata["artist"]} - {metadata["title"]}")
				else:
					self.update_download_progress(index, total_tracks, metadata)

				# The file is not downloaded, download it
				success = self.download_item(metadata, "track") #TODO unhard code this when adding entire podcasts
				if not success:
					continue
				download_count += 1

				if download_count < total_tracks:
					# Short delay between each track
					sleep_time = random.uniform(2.5, 5.0)
					if self.verbosity == AppVerbosity.HIGH:
						print(f"\t{WAIT} {sleep_time:.2f} seconds to protect rate limits...")
					time.sleep(sleep_time)

					# Take a long break every 20 downloads
					if download_count % 20 == 0:
						long_break = random.randint(120, 300)  # 2 to 5 minutes
						if self.verbosity == AppVerbosity.HIGH:
							print(f"\t{WAIT} {long_break // 60} minutes, downloaded {download_count} tracks...")
						time.sleep(long_break)

			if self.settings.generate_m3u:
				generate_m3u(collection_name, metadata_list, self.collection_path, self.file_ext, self.filename_lookup, self.m3u_path_overrides)
				if self.verbosity != AppVerbosity.LOW:
					print(f"{SUCC} M3U playlist created.")
		finally:
			os.chdir(original_dir) # cd back to the program directory

	def download_item(self, metadata, url_type):
		match url_type:
			case "track":
				item_id = TrackId.from_base62(metadata["id"])
			case "episode":
				item_id = EpisodeId.from_base62(metadata["id"])
			case _:
				raise Exception("Unknown URL type") # This should never happen

		# Fetch the raw decrypted music byte stream from the Content Delivery Network (CDN)
		session = _get_stream_session(self.verbosity)

		stream = None
		audio_key_retries = 3
		audio_key_delay = 2
		for attempt in range(audio_key_retries):
			try:
				stream = _safe_api_call(
					session.content_feeder().load,
					item_id,
					VorbisOnlyAudioQuality(self.settings.audio_quality.librespot_quality),
					False,
					None
				)
				break
			except RuntimeError as e:
				if attempt < audio_key_retries - 1:
					print(f"\t{WARN} Audio key fetch failed for '{metadata['title']}' (attempt [{attempt + 1}/{audio_key_retries}]). Retrying in {audio_key_delay}s...")
					time.sleep(audio_key_delay)
					audio_key_delay *= 2
				else:
					print(f"\t{ERROR} Skipping '{metadata['title']}': unable to fetch audio key after {audio_key_retries} attempts ({e}).")
					return False

		formatted_filename = self.filename_lookup[metadata["id"]]

		# Create a temp file in the working directory
		temp_fd, temp_ogg_filename = tempfile.mkstemp(suffix=AppAudioFormat.OGG.ext, dir=self.collection_path)
		os.close(temp_fd)

		final_filename = f"{formatted_filename}{self.file_ext}"

		with open(temp_ogg_filename, "wb") as f:
			f.write(stream.input_stream.stream().read())

		if self.file_ext == AppAudioFormat.OGG.ext or not _FFMPEG_PATH:
			if self.file_ext != AppAudioFormat.OGG.ext:
				print(f"{WARN} ffmpeg unavailable. Defaulting to {AppAudioFormat.OGG.ext} instead of {self.file_ext}.")
				final_filename = f"{formatted_filename}{AppAudioFormat.OGG.ext}"
			os.replace(temp_ogg_filename, final_filename)
		else:
			try:
				result = subprocess.run([_FFMPEG_PATH, "-y", "-i", temp_ogg_filename, final_filename], capture_output=True)
				if result.returncode != 0:
					raise Exception(f"{WARN} FFmpeg failed with code {result.returncode}")
			except Exception as e:
				print(f"{ERROR} Transcoding failed: {e}. Defaulting to original OGG container.")
				final_filename = f"{formatted_filename}{AppAudioFormat.OGG.ext}"
				os.replace(temp_ogg_filename, final_filename)
			finally:
				if os.path.exists(temp_ogg_filename):
					os.remove(temp_ogg_filename)

		if self.verbosity == AppVerbosity.HIGH:
			print(f"\t{SUCC} Downloaded {final_filename}")
		self.add_file_metadata(final_filename, metadata)
		return True

	def add_file_metadata(self, filename, metadata):
		"""Add metadata to the audio file."""
		ext = os.path.splitext(filename)[1].lower()
		match ext:
			case AppAudioFormat.OGG.ext:
				audio = OggVorbis(filename)
			case AppAudioFormat.FLAC.ext:
				audio = FLAC(filename)
			case AppAudioFormat.MP3.ext:
				try:
					audio = EasyID3(filename)
				except ID3NoHeaderError:
					# Freshly transcoded MP3s have no ID3 metadata yet: create one
					audio = EasyID3()
					audio.save(filename)
					audio = EasyID3(filename)
			case AppAudioFormat.M4A.ext:
				audio = MP4(filename)
			case _:
				print(f"{WARN} {ext} metadata not implemented yet, skipping.")
				return

		if ext == AppAudioFormat.MP3.ext:
			# Map program metadata names to mp3 ID3 metadata names
			id3_metadata_map = {
				"album": "album",
				"artist": "artist",
				"albumartist": "albumartist",
				"title": "title",
				"discnumber": "discnumber",
				"tracknumber": "tracknumber",
				"year": "date",
			}
			for meta_key, id3_key in id3_metadata_map.items():
				if metadata.get(meta_key):
					audio[id3_key] = str(metadata[meta_key])

			# ID3 combines track number and total tracks into track number / total tracks
			if metadata.get("tracknumber"):
				if metadata.get("totaltracks"):
					audio["tracknumber"] = f"{metadata['tracknumber']}/{metadata['totaltracks']}"
				else:
					audio["tracknumber"] = metadata["tracknumber"]
		elif ext == AppAudioFormat.M4A.ext:
			# Map program metadata names to MP4 atom keys
			mp4_metadata_map = {
				"©alb": "album",
				"©ART": "artist",
				"aART": "albumartist",
				"©nam": "title",
				"©day": "year",
			}
			for atom_key, meta_key in mp4_metadata_map.items():
				if metadata.get(meta_key):
					audio[atom_key] = [str(metadata[meta_key])]

			# TODO Disc total is unknown, so we default to 0. see if this is possible to calculate
			if metadata.get("tracknumber"):
				try:
					total_tracks = int(metadata["totaltracks"]) if metadata.get("totaltracks") else 0
					audio["trkn"] = [(int(metadata["tracknumber"]), total_tracks)]
				except ValueError:
					pass
			if metadata.get("discnumber"):
				try:
					audio["disk"] = [(int(metadata["discnumber"]), 0)]
				except ValueError:
					pass
		else:
			audio.update({k: v for k, v in metadata.items() if k not in ["id", "image_url"]})
			if metadata.get("totaltracks"):
				audio["tracktotal"] = metadata["totaltracks"]

		audio.save()

		image_url = metadata["image_url"]
		if image_url:
			try:
				response = requests.get(image_url, timeout=10)
				if response.status_code == 200:
					if ext == AppAudioFormat.MP3.ext:
						id3 = ID3(filename)
						id3.delall("APIC")
						id3.add(APIC(
							encoding=3,
							mime="image/jpeg",
							type=3,
							desc="Cover",
							data=response.content
						))
						id3.save()
					elif ext == AppAudioFormat.M4A.ext:
						audio["covr"] = [MP4Cover(response.content, imageformat=MP4Cover.FORMAT_JPEG)]
						audio.save()
					else:
						# Build a Vorbis-compliant picture block metadata frame
						picture = Picture()
						picture.data = response.content
						picture.type = 3  # Type 3 is the industry standard for 'Front Cover'
						picture.mime = "image/jpeg"  # Spotify artwork links are always JPEG files
						picture.description = "Cover"

						if ext == AppAudioFormat.OGG.ext:
							# Ogg Vorbis needs metadata as a base64 encoded string
							picture_bytes = picture.write()
							encoded_picture = base64.b64encode(picture_bytes).decode("ascii")
							audio["metadata_block_picture"] = [encoded_picture]
							audio.save()
						elif ext == AppAudioFormat.FLAC.ext:
							audio.clear_pictures()
							audio.add_picture(picture)
							audio.save()

				else:
					print(f"\t{WARN} Artwork server returned status code {response.status_code}")

			except Exception as e:
				print(f"\t{WARN} Failed to embed album art due to network or format error: {e}")

	def update_download_progress(self, current, total, metadata):
		"""Update the progress bar print with the current information"""
		if self.verbosity != AppVerbosity.LOW:
			return

		percentage = float(current) / total
		bar_length = 25  # Slightly shorter for cleaner geometry

		# Calculate how many full blocks to draw
		filled_length = int(round(bar_length * percentage))

		# Determine if a section will be updated next call
		next_current = min(current + 1, total)
		next_percentage = float(next_current) / total
		next_filled_length = int(round(bar_length * next_percentage))
		will_fill = next_filled_length > filled_length and filled_length < bar_length

		filled_segment = c.cyan("█" * filled_length)

		if will_fill:
			next_highlight_segment = c.cyan("░")
			to_fill_segment = c.gray("░" * (bar_length - filled_length - 1))
			colored_bar = filled_segment + next_highlight_segment + to_fill_segment
		else:
			to_fill_segment = c.gray("░" * (bar_length - filled_length))
			colored_bar = filled_segment + to_fill_segment

		# Smooth formatting for numbers and truncation logic for tracks
		percentage_text = f"{int(percentage * 100):>3}%"
		count_text = c.gray(f"{current}/{total}")


		# Overwrite the current terminal line dynamically
		sys.stdout.write(f"\rDownloading {colored_bar} {percentage_text} {count_text} | {metadata["title"]} - {metadata["artist"]}")
		sys.stdout.flush()

		if current == total:
			print(f"\n{SUCC} All tracks downloaded.")


### Helper Functions ###
def _is_valid_audio(filepath):
	"""Validates a given file's audio, meaning it can be parsed by Mutagen"""
	if not os.path.exists(filepath):
		return False
	ext = os.path.splitext(filepath)[1].lower()
	try:
		match ext:
			case AppAudioFormat.OGG.ext:
				OggVorbis(filepath)
			case AppAudioFormat.FLAC.ext:
				FLAC(filepath)
			case AppAudioFormat.MP3.ext:
				MP3(filepath)
			case AppAudioFormat.M4A.ext:
				MP4(filepath)
			case _:
				return False
		return True
	except Exception:
		return False


def _verify_file_integrity(filepath):
	"""Checks if a file exists and can be successfully read/parsed by Mutagen. Deletes if corrupted."""
	if not os.path.exists(filepath):
		return False
	if _is_valid_audio(filepath):
		return True
	print(f"\t{WARN} Existing '{os.path.basename(filepath)}' is corrupted. Overwriting...")
	try:
		os.remove(filepath)
	except OSError:
		pass
	return False


def _build_file_index(download_dir):
	"""Walks all folders under download_dir and returns a dict mapping (artist, title)
	to the full filepath of the already-downloaded file, based on file metadata."""
	existing_items = {}
	for root, _dirs, files in os.walk(download_dir):
		for filename in files:
			filepath = os.path.join(root, filename)
			if not _is_valid_audio(filepath):
				continue
			item_metadata = _read_track_metadata(filepath)
			if item_metadata:
				existing_items[item_metadata] = filepath
	return existing_items


def _build_item_metadata(track_data, collection_name, release_date, image_url, total_tracks):
	"""Formats track or episode data into a standardized metadata dictionary."""
	match track_data.get("type"):
		case "track":
			artists = track_data.get("artists", [])
			artist_string = "/".join([artist["name"] for artist in artists]) if artists else "Unknown Artist"

			album_artists = track_data.get("album", {}).get("artists", [])
			if not album_artists:
				album_artists = artists
			album_artist = album_artists[0]["name"] if album_artists else "Unknown Artist"
		case "episode":
			show_data = track_data.get("show", {})
			artist_string = show_data.get("publisher") or show_data.get("name") or "Podcast"
			album_artist = artist_string
		case _:
			raise Exception("Unknown URL type") # This should never happen

	return {
		"album": collection_name,
		"artist": artist_string,
		"albumartist": album_artist,
		"title": track_data["name"],
		"discnumber": str(track_data.get("disc_number", "")),
		"tracknumber": str(track_data.get("track_number", "")),
		"totaltracks": str(total_tracks) if total_tracks else "",
		"year": release_date.split("-")[0] if release_date and "-" in release_date else "Unknown",
		"id": track_data["id"],
		"image_url": image_url
	}


def _get_item_metadata(url, url_type):
	"""Fetches and processes metadata for a single track or podcast episode."""
	item_id = _get_url_id(url)

	match url_type:
		case "track":
			data = _safe_api_call(SC.track, item_id)
			album_data = data.get("album", {})

			collection_name = album_data.get("name", "Unknown Album")
			release_date = album_data.get("release_date", "Unknown Date")
			images = album_data.get("images", [])
			total_tracks = album_data.get("total_tracks", 0)

		case "episode":
			data = _safe_api_call(SC.episode, item_id)
			show_data = data.get("show", {})

			collection_name = show_data.get("name", "Unknown Podcast")
			release_date = data.get("release_date", "Unknown Date")
			images = data.get("images", [])
			total_tracks = 0
		case _:
			raise Exception("Unknown URL type") # This should never happen

	image_url = images[0]["url"] if images else None
	return _build_item_metadata(data, collection_name, release_date, image_url, total_tracks)


def _get_collection_metadata(url, url_type):
	"""Fetches and processes all track metadata within a collection."""
	collection_id = _get_url_id(url)

	match url_type:
		case "album":
			collection_data = _safe_api_call(SC.album, collection_id)
			# Pre-populate album wide metadata
			album_name = collection_name = collection_data["name"]
			release_date = collection_data["release_date"]
			images = collection_data.get("images", [])
			image_url = images[0]["url"] if images else None
			total_tracks = collection_data.get("total_tracks", 0)

			tracks_payload = collection_data.get("tracks", {})

		case "playlist":
			collection_data = _safe_api_call(SC.playlist, collection_id)
			collection_name = collection_data["name"]

			tracks_payload = _safe_api_call(SC.playlist_items, collection_id)

		case _: # This should never be hit
			raise ValueError(f"{ERROR} Unsupported url type: {url_type}")

	# If a collection is over 50 items long it will use multiple pages, go through each page
	tracks = tracks_payload.get("items", [])
	while tracks_payload.get("next"):
		tracks_payload = _safe_api_call(SC.next, tracks_payload)
		if tracks_payload:
			tracks.extend(tracks_payload.get("items", []))
		else:
			break

	metadata_list = []
	for item in tracks:
		match url_type:
			case "album":
				track_data = item
				track_total_tracks = total_tracks

			case "playlist":
				if not item.get("item"):
					continue # This will filter out podcasts, local files, and blocked content
				track_data = item["item"]

				track_album = track_data.get("album", {})
				album_name = track_album.get("name", "Unknown Album")
				release_date = track_album.get("release_date", "Unknown Date")
				images = track_album.get("images", [])
				image_url = images[0]["url"] if images else None
				track_total_tracks = track_album.get("total_tracks", 0)

		track_metadata = _build_item_metadata(track_data, album_name, release_date, image_url, track_total_tracks)
		metadata_list.append(track_metadata)

	return metadata_list, collection_name


def _read_track_metadata(filepath): #TODO might need a rename once episodes/podcasts are done
	"""Reads (artist, title) from a file's metadata. Returns None if metadata was missing."""
	ext = os.path.splitext(filepath)[1].lower()
	try:
		match ext:
			case AppAudioFormat.OGG.ext:
				audio = OggVorbis(filepath)
				artist = audio.get("artist", [""])[0]
				title = audio.get("title", [""])[0]
			case AppAudioFormat.FLAC.ext:
				audio = FLAC(filepath)
				artist = audio.get("artist", [""])[0]
				title = audio.get("title", [""])[0]
			case AppAudioFormat.MP3.ext:
				audio = EasyID3(filepath)
				artist = audio.get("artist", [""])[0]
				title = audio.get("title", [""])[0]
			case AppAudioFormat.M4A.ext:
				audio = MP4(filepath)
				artist = audio.get("©ART", [""])[0]
				title = audio.get("©nam", [""])[0]
			case _:
				return None

		if not artist or not title:
			return None
		return artist, title

	except Exception:
		return None


def _safe_api_call(api_func, *args, **kwargs):
	"""Wraps network calls to handle Spotify rate limits (429) and access denial (403)."""
	retries = 5
	delay = 2
	for i in range(retries):
		try:
			return api_func(*args, **kwargs)
		except spotipy.exceptions.SpotifyException as e:
			# Handle Rate Limit (429)
			if e.http_status == 429:
				headers = getattr(e, 'headers', {})
				wait_time = int(headers.get('Retry-After', delay))
				print(f"{WARN} 429 Rate limited. Cooling down for {wait_time} seconds...")
				time.sleep(wait_time)
				delay *= 2
				continue
			elif e.http_status == 403:
				print(f"{ERROR} 403 Forbidden when calling '{api_func.__name__}'.")
				print(f"{ERROR} This usually means the playlist isn't yours. Spotify only allows full access to playlists you created or can edit.")
				print(f"Details: {e.msg}")
				raise e
			else:
				raise e
		except Exception as e:
			# Catch general connection/network issues
			raise e
	raise Exception("Max retries exceeded due to rate limiting.")


### Main Interface Function ###
def download_url(url, download_settings, verbosity):
	"""Entry point function used by the UI"""
	processor = DownloadProcessor(url, download_settings, verbosity)
	processor.start()
