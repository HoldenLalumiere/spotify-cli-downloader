import os
import json
from scripts.download import init_spotify_cred, _get_url_id, _safe_api_call


def save_spotify_json_fixture(url, output_dir="tests/"):
	"""
	Fetches the raw JSON payload for a track, album, or playlist
	from Spotify and saves it locally as a test fixture.
	"""
	# 1. Initialize credentials and parse out URL components
	sc_client = init_spotify_cred()
	url_id = _get_url_id(url)

	try:
		url_type = url.split("/")[-2]
	except IndexError:
		print(f"[-] Invalid URL structure: {url}")
		return False

	print(f"[*] Contacting Spotify API for {url_type} ID: {url_id}...")

	data = _safe_api_call(sc_client.episode, url_id)
	# match url_type:
	# 	case "track":
	# 		data = _safe_api_call(sc_client.track, url_id)
	# 	case "album":
	# 		data = _safe_api_call(sc_client.album, url_id)
	# 	case "playlist":
	# 		data = _safe_api_call(sc_client.playlist, url_id)
	# 		# If the playlist is paginated, follow the 'next' iteration cursors
	# 		tracks_payload = data.get("tracks", {})
	# 		while tracks_payload.get("next"):
	# 			tracks_payload = _safe_api_call(sc_client.next, tracks_payload)
	# 			if tracks_payload:
	# 				data["tracks"]["items"].extend(tracks_payload.get("items", []))
	# 			else:
	# 				break
	# 	case _:
	# 		print(f"[-] Unsupported media type '{url_type}' for snapshot capture.")
	# 		return False

	# 3. Securely write the payload file out to disk
	os.makedirs(output_dir, exist_ok=True)
	filename = f"{url_type}_{url_id}.json"
	file_path = os.path.join(output_dir, filename)

	with open(file_path, "w", encoding="utf-8") as f:
		json.dump(data, f, indent=4, ensure_ascii=False)

	print(f"[+] Successfully saved mock data fixture to: {file_path}")
	return True

save_spotify_json_fixture("https://open.spotify.com/episode/5CMr3RyhOwfLixP2m7lBC6?si=8ef92acdc6164b1d")
