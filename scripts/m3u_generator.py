import os

from scripts.utils import sanitize_filename, format_custom_filename


def generate_m3u(collection_name, metadata_list, collection_path, file_ext, filename_lookup):
	"""Generates a m3u file for the given collection"""
	safe_collection_name = sanitize_filename(collection_name)
	m3u_path = os.path.join(collection_path, f"{safe_collection_name}.m3u")

	with open(m3u_path, "w", encoding="utf-8") as f:
		f.write("#EXTM3U\n")
		for track in metadata_list:
			formatted_filename = filename_lookup[track["id"]]
			filename = f"{formatted_filename}{file_ext}"
			f.write(f"{filename}\n")

	return m3u_path