import math
import os
import sys
import time
import json
import base64
import random
import spotipy
import logging
import requests
import threading

# from pydub import AudioSegment #TODO uncomment this once I figure out a good solution to the ffmpeg requirement
from dotenv import load_dotenv
from email.mime.image import MIMEImage
from spotipy.exceptions import SpotifyException
from spotipy.oauth2 import SpotifyOAuth
from librespot.core import Session
from librespot.metadata import TrackId
from librespot.audio.decoders import VorbisOnlyAudioQuality
from mutagen.flac import Picture
from mutagen.oggvorbis import OggVorbis
from constants import c, SAVED, ERROR, WARN, SUCC, WAIT
from preference_manager import AppVerbosity


# TODO implement switching between different audio formats
# TODO when getting the 403 error for someone elses playlist, print a message that the playlist must be made by you
# TODO add in extra prints if high verbosity
def init_spotify_cred():
	"""Initializes Spotipy with user authentication credentials."""
	project_root = os.path.dirname(os.path.abspath(__file__))
	cache_path = os.path.join(project_root, ".cache")

	return spotipy.Spotify(auth_manager=SpotifyOAuth(
			client_id=os.getenv("SPOTIPY_CLIENT_ID"),
			client_secret=os.getenv("SPOTIPY_CLIENT_SECRET"),
			redirect_uri=os.getenv("SPOTIPY_REDIRECT_URI"),
			scope="playlist-read-private",
			cache_path=cache_path
	))


### Global variables ###
# Load vars from .env system memory
load_dotenv()
# Set up Spotify API listening credentials
SPOTIFY_STREAM_SESSION = None
SC = None

def _get_stream_session(verbosity):
	"""Returns the current stream session, or builds a fresh one if dropped/idle."""
	global SPOTIFY_STREAM_SESSION
	if SPOTIFY_STREAM_SESSION is None or not SPOTIFY_STREAM_SESSION.is_valid():
		if verbosity != AppVerbosity.LOW:
			print("\tEstablishing active Spotify streaming connection...")
		auth_token = _get_auth_token()
		if auth_token:
			# Pass the Spotipy token into the librespot session builder
			SPOTIFY_STREAM_SESSION = Session.Builder().oauth(auth_token).create()
		else:
			# Fallback as unauthenticated if no token is passed
			SPOTIFY_STREAM_SESSION = Session.Builder().oauth(None).create()
	return SPOTIFY_STREAM_SESSION


def _get_auth_token():
	try:
		token_info = SC.auth_manager.get_access_token(as_dict=True)
		return token_info["access_token"] if token_info else None
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
				tags_list, collection_name = _get_collection_tags(self.url, url_type)
				self._download_collection(collection_name, tags_list, download_dir, original_dir)

			case "track":
				SC = init_spotify_cred()
				os.chdir(download_dir)
				try:
					tags = _get_track_tags(self.url)
					print(f"Downloading: {tags['artist']} - {tags['title']}")
					self.download_track(tags)
				finally:
					os.chdir(original_dir)

			case _:
				raise Exception("Unknown URL type")

		print(f"{SUCC} Download sequence completed.")

	def _download_collection(self, collection_name, tags_list, download_dir, original_dir):
		total_tracks = len(tags_list)
		width = len(str(total_tracks))
		safe_collection_name = "".join(
				[char for char in collection_name if char.isalpha() or char.isdigit() or char in " ',-_"]).strip()

		# Change directory to that collection in their preferred download directory
		collection_path = os.path.join(download_dir, safe_collection_name)
		folder_exists = os.path.exists(collection_path)
		os.makedirs(collection_path, exist_ok=True)
		os.chdir(collection_path)
		if not folder_exists:
			print(f"{SUCC} Created folder: {os.getcwd()}")

		file_ext = self.settings.audio_format.ext.lower().strip()

		download_count = 0
		try:
			for index, tags in enumerate(tags_list, start=1):
				final_filename = f"{tags["title"]}{file_ext}"

				# Check if the file is already downloaded
				if _verify_file_integrity(final_filename):
					if self.verbosity != AppVerbosity.LOW:
						print(f"{c.magenta(f"[{index:>{width}}/{total_tracks}]")} Skipping: {tags['artist']} - {tags['title']}")
					else:
						self.update_download_progress(index, total_tracks, tags)
					continue

				if self.verbosity != AppVerbosity.LOW:
					print(f"{c.cyan(f"[{index:>{width}}/{total_tracks}]")} Downloading: {tags["artist"]} - {tags["title"]}")
				else:
					self.update_download_progress(index, total_tracks, tags)

				# The file is not downloaded, download it
				self.download_track(tags)
				download_count += 1

				if index < total_tracks:
					# Short delay between each track
					sleep_time = random.uniform(3.0, 7.0)
					if self.verbosity == AppVerbosity.HIGH:
						print(f"\t{WAIT} {sleep_time:.2f} seconds to protect rate limits...")
					time.sleep(sleep_time)

					# Take a long break every 20 downloads
					if download_count % 20 == 0 and download_count != total_tracks:
						long_break = random.randint(120, 300)  # 2 to 5 minutes
						if self.verbosity == AppVerbosity.HIGH:
							print(f"\t{WAIT} {long_break // 60} minutes, downloaded {download_count} tracks...")
						time.sleep(long_break)
		finally:
			os.chdir(original_dir) # cd back to the program directory

	def download_track(self, tags):
		track_id = TrackId.from_base62(tags["id"])

		# Fetch the raw decrypted music byte stream from the Content Delivery Network (CDN)
		session = _get_stream_session(self.verbosity)
		stream = _safe_api_call(
			session.content_feeder().load,
			track_id,
			VorbisOnlyAudioQuality(self.settings.audio_quality.librespot_quality),
			False,
			None
		)

		file_ext = self.settings.audio_format.ext.lower().strip()
		temp_ogg_filename = f"{tags['title']}_temp.ogg" #TODO save as .file so the user does not see it?
		final_filename = f"{tags['title']}{file_ext}"

		with open(temp_ogg_filename, "wb") as f:
			f.write(stream.input_stream.stream().read())

		if file_ext == ".ogg":
			os.rename(temp_ogg_filename, final_filename)
		else:
			pass #TODO uncomment this once I figure out a good solution to the ffmpeg requirement
			# try:
			# 	audio_segment = AudioSegment.from_ogg(temp_ogg_filename)
			#
			# 	# pydub expects format strings without periods (e.g., "mp3", "flac")
			# 	audio_segment.export(final_filename, format=file_ext.replace(".", ""))
			# except Exception as e:
			# 	print(f"{ERROR} Transcoding failed: {e}. Defaulting to original OGG container.")
			# 	final_filename = f"{tags['title']}.ogg"
			# 	os.rename(temp_ogg_filename, final_filename)
			# finally:
			# 	if os.path.exists(temp_ogg_filename):
			# 		os.remove(temp_ogg_filename)

		if self.verbosity == AppVerbosity.HIGH:
			print(f"\t{SUCC} Downloaded {final_filename}")
		self.tag_file(final_filename, tags)

	def tag_file(self, filename, tags):
		"""Add tags to the audio file."""
		audio = OggVorbis(filename)
		audio.update({k: v for k, v in tags.items() if k not in ["id", "image_url"]})

		image_url = tags["image_url"]
		if image_url:
			try:
				response = requests.get(image_url, timeout=10)
				if response.status_code == 200:
					# Build a Vorbis-compliant picture block metadata frame
					picture = Picture()
					picture.data = response.content
					picture.type = 3  # Type 3 is the industry standard for 'Front Cover'
					picture.mime = "image/jpeg"  # Spotify artwork links are always JPEG files
					picture.description = "Cover"

					# Ogg Vorbis needs metadata as a base64 encoded string
					picture_bytes = picture.write()
					encoded_picture = base64.b64encode(picture_bytes).decode("ascii")

					audio["metadata_block_picture"] = [encoded_picture]
				else:
					print(f"\t{WARN} Artwork server returned status code {response.status_code}")

			except Exception as e:
				print(f"\t{WARN} Failed to embed album art due to network or format error: {e}")

		audio.save()

	def update_download_progress(self, current, total, tags):
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

		# next_highlight_segment = c.cyan("░") #TODO see which Jacob likes
		# to_fill_segment = c.gray("░" * (bar_length - filled_length))
		# colored_bar = filled_segment + next_highlight_segment + to_fill_segment

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
		sys.stdout.write(f"\rDownloading {colored_bar} {percentage_text} {count_text} | {tags["title"]} - {tags["artist"]}")
		sys.stdout.flush()

		if current == total:
			print(f"\n{SUCC} All tracks downloaded.")


### Helper Functions ###
def _get_url_id(url):
	return url.split("/")[-1].split("?")[0]


def _verify_file_integrity(filepath):
	"""Checks if a file exists and can be successfully read/parsed by Mutagen."""
	if not os.path.exists(filepath):
		return False
	try:
		OggVorbis(filepath)
		return True
	except Exception as e:
		print(f"\t{WARN} Existing'{os.path.basename(filepath)}' is corrupted/incomplete. Overwriting...")
		try:
			os.remove(filepath)
		except OSError:
			pass
		return False


def _build_track_tags(track_data, album_name, release_date, image_url):
	"""Formats raw track data into a standardized tags dictionary."""
	return {
		"album": album_name,
		"artist": "/".join([artist["name"] for artist in track_data["artists"]]),
		"title": track_data["name"],
		"discnumber": str(track_data["disc_number"]),
		"tracknumber": str(track_data["track_number"]),
		"year": release_date.split("-")[0],
		"id": track_data["id"],
		"image_url": image_url
	}


def _get_track_tags(track_url):
	"""Fetches and processes a single tracks tags."""
	track_id = _get_url_id(track_url)
	track_data = _safe_api_call(SC.track, track_id)
	images = track_data["album"].get("images", [])
	image_url = images[0]["url"] if images else None
	return _build_track_tags(track_data, track_data["album"]["name"], track_data["album"]["release_date"], image_url)


def _get_collection_tags(url, url_type):
	"""Fetches and processes all track tags within a collection."""
	collection_id = _get_url_id(url)

	match url_type:
		case "album":
			collection_data = _safe_api_call(SC.album, collection_id)
			# Pre-populate album wide metadata
			album_name = collection_name = collection_data["name"]
			release_date = collection_data["release_date"]
			images = collection_data.get("images", [])
			image_url = images[0]["url"] if images else None

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

	tags_list = []
	for item in tracks:
		match url_type:
			case "album":
				track_data = item

			case "playlist":
				if not item.get("item"):
					continue # This will filter out podcasts, local files, and blocked content
				track_data = item["item"]

				track_album = track_data.get("album", {})
				album_name = track_album.get("name", "Unknown Album")
				release_date = track_album.get("release_date", "Unknown Date")
				images = track_album.get("images", [])
				image_url = images[0]["url"] if images else None

		track_tags = _build_track_tags(track_data, album_name, release_date, image_url)
		tags_list.append(track_tags)

	return tags_list, collection_name


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
