import os


def save_to_env(key, value):
	"""
	Reads or creates a .env file, drops any old entry matching the key,
	and appends the updated key-value pair to the end of the file.
	"""
	env_file = "../.env"

	# Read existing lines if the file exists, otherwise start clean
	lines = []
	if os.path.exists(env_file):
		with open(env_file, "r", encoding="utf-8") as f:
			lines = f.readlines()

	# Filter out any old entry that matches our key (keeps everything else)
	cleaned_lines = [line for line in lines if not line.strip().startswith(f"{key}=")]

	# Append our updated key-value assignment to the list
	cleaned_lines.append(f"{key}={value}\n")

	# Save/Create the file with the fresh configuration matrix back to disk
	with open(env_file, "w", encoding="utf-8") as f:
		f.writelines(cleaned_lines)