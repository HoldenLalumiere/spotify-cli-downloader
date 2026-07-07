import unittest
import itertools

from main import is_valid_spotify_url

class TestSpotifyUrlValidation(unittest.TestCase):
	def test_valid_spotify_links(self):
		"""Ensure all generated Spotify links pass validation."""
		protocols = ["http", "https"]
		subdomains = ["open", "www", "play"]
		media_types = ["track", "album", "playlist", "artist", "show", "episode"]
		test_id = "3aUNhIz0jPQIB9zlGKouWg"  # Valid 22-character alphanumeric ID

		tracking_suffixes = [
			"",                        # No tracking data
			"?si=abcde12345fghij678",  # Standard query parameter tracking
			"?si=123&utm_source=copy", # Multiple query parameters
			"/",                       # Trailing slash
		]

		valid_urls = []

		# Add all URLs
		for proto, sub, media, suffix in itertools.product(protocols, subdomains, media_types, tracking_suffixes):
			base_url = f"{proto}://{sub}.spotify.com/{media}/{test_id}"
			valid_urls.append(f"{base_url}{suffix}")

		# Add all URIs
		for media in media_types:
			valid_urls.append(f"spotify:{media}:{test_id}")

		for url in valid_urls:
			with self.subTest(url=url):
				self.assertTrue(is_valid_spotify_url(url), f"Failed to validate real URL: {url}")

	def test_invalid_spotify_links(self):
		"""Ensure malformed strings, wrong IDs, or foreign domains fail validation."""
		# Invalid elements
		bad_protocols = ["ftp", "ws"]
		bad_subdomains = ["music", "api", "embed"]
		bad_media_types = ["usercollection", "playlisttrack", "song", "artist profile"]

		bad_ids = [
			"3aUNhIz0jPQIB9zlGKouW",     # 21 chars (too short)
			"3aUNhIz0jPQIB9zlGKouWgaa",  # 24 chars (too long)
			"",                          # 0  chars (empty)
			"3aUNhIz0jPQIB9zlGKouW!",    # 22 chars but contains invalid character '!'
		]

		# Valid baseline elements
		good_protocols = ["http", "https"]
		good_subdomains = ["open", "www", "play"]
		good_media_types = ["track", "album"]
		good_id = "3aUNhIz0jPQIB9zlGKouWg"

		invalid_urls = [
			# Hardcoded foreign domains or text
			"https://youtube.com/watch?v=1lVPn0cpvnM",
			"https://apple.co/music-track-sample",
			"just_text_not_a_url",
			"spotify:track",  # Missing trailing colons/ID
		]

		# Bad IDs
		for proto, sub, media, bad_id in itertools.product(good_protocols, good_subdomains, good_media_types, bad_ids):
			invalid_urls.append(f"{proto}://{sub}.spotify.com/{media}/{bad_id}")

		# Bad Media Types
		for proto, sub, bad_media in itertools.product(good_protocols, good_subdomains, bad_media_types):
			invalid_urls.append(f"{proto}://{sub}.spotify.com/{bad_media}/{good_id}")

		# Bad Subdomains
		for proto, bad_sub, media in itertools.product(good_protocols, bad_subdomains, good_media_types):
			invalid_urls.append(f"{proto}://{bad_sub}.spotify.com/{media}/{good_id}")

		# Bad Protocols
		for bad_proto, sub, media in itertools.product(bad_protocols, good_subdomains, good_media_types):
			invalid_urls.append(f"{bad_proto}://{sub}.spotify.com/{media}/{good_id}")

		# Bad URIs
		for bad_media in bad_media_types:
			invalid_urls.append(f"spotify:{bad_media}:{good_id}")
		for bad_id in bad_ids:
			invalid_urls.append(f"spotify:track:{bad_id}")

		for url in invalid_urls:
			with self.subTest(url=url):
				self.assertFalse(is_valid_spotify_url(url), f"Incorrectly validated fake URL: {url}")


if __name__ == "__main__":
	unittest.main()
