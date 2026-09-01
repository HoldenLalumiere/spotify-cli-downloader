import os

from scripts.utils import sanitize_filename, format_custom_filename


def generate_m3u(collection_name, metadata_list, collection_path, file_ext, filename_lookup, path_overrides=None):
	"""Generates a m3u file for the given collection. Can handle files outside of collection_path"""
	path_overrides = path_overrides or {}
	safe_collection_name = sanitize_filename(collection_name)
	m3u_path = os.path.join(collection_path, f"{safe_collection_name}.m3u")

	with open(m3u_path, "w", encoding="utf-8") as f:
		f.write("#EXTM3U\n")
		for track in metadata_list:
			track_id = track["id"]
			if track_id in path_overrides:
				entry = os.path.relpath(path_overrides[track_id], start=collection_path)
			else:
				formatted_filename = filename_lookup[track_id]
				entry = f"{formatted_filename}{file_ext}"

			f.write(f"{entry}\n")

	return m3u_path