import os

from scripts.utils import sanitize_filename


def generate_m3u(collection_name, metadata_list, collection_path, file_ext  ):
	""""""
	safe_collection_name = sanitize_filename(collection_name)
	m3u_path = os.path.join(collection_path, f"{safe_collection_name}.m3u")

	with open(m3u_path, "w", encoding="utf-8") as f:
		f.write("#EXTM3U\n")
		for track in metadata_list:
			filename = f"{track['title']}{file_ext}"
			f.write(f"{filename}\n")

	return m3u_path