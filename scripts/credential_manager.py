import os
from scripts.constants import AUTH_DIR, ENV_FILE


def save_to_env(key, value):
	"""
	Reads or creates a .env file, drops any old entry matching the key,
	and appends the updated key-value pair to the end of the file.
	"""
	os.makedirs(AUTH_DIR, exist_ok=True)

	# Read existing lines if the file exists, otherwise start clean
	lines = []
	if os.path.exists(ENV_FILE):
		with open(ENV_FILE, "r", encoding="utf-8") as f:
			lines = f.readlines()

	# Filter out any old entry that matches our key (keeps everything else)
	cleaned_lines = [line for line in lines if not line.strip().startswith(f"{key}=")]

	# Append our updated key-value assignment to the list
	cleaned_lines.append(f"{key}={value}\n")

	# Save/Create the file with the fresh configuration matrix back to disk
	with open(ENV_FILE, "w", encoding="utf-8") as f:
		f.writelines(cleaned_lines)