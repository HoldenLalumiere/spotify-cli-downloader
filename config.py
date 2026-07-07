from enum import Enum
from librespot.audio.decoders import AudioQuality as LibrespotAudioQuality


### Audio Formats ###
class AppAudioFormat(Enum):
	# Value format: (extension, UI label, is_implemented)
	MP3  = (".mp3",  "MP3",        False)
	M4A  = (".m4a",  "M4A/AAC",    False)
	FLAC = (".flac", "FLAC",       False)
	OGG  = (".ogg",  "Ogg Vorbis", True)

	def __init__(self, ext, label, implemented):
		self.ext = ext
		self.label = label
		self.implemented = implemented


# Used for the UI only
AUDIO_FORMAT_MAP = {
	"1": AppAudioFormat.MP3,
	"2": AppAudioFormat.M4A,
	"3": AppAudioFormat.FLAC,
	"4": AppAudioFormat.OGG,
}


### Audio Qualities ###
class AppAudioQuality(Enum):
	# Value format: (librespot_enum, UI label, bitrate_display, is_implemented)
	NORMAL    = (LibrespotAudioQuality.NORMAL,    "Normal",    "96kbps",  True)
	HIGH      = (LibrespotAudioQuality.HIGH,      "High",      "160kbps", True)
	VERY_HIGH = (LibrespotAudioQuality.VERY_HIGH, "Very High", "320kbps", True)

	def __init__(self, librespot_quality, label, kbps, implemented):
		self.librespot_quality = librespot_quality
		self.label = label
		self.kbps = kbps
		self.implemented = implemented


# Used for the UI only
AUDIO_QUALITY_MAP = {
	"1": AppAudioQuality.NORMAL,
	"2": AppAudioQuality.HIGH,
	"3": AppAudioQuality.VERY_HIGH,
}


### Verbosity Levels ###
class AppVerbosity(Enum):
	# Value format: (level_value, UI label, description, is_implemented)
	LOW    = ("low",    "Low",    "Errors and progress bar", True)
	MEDIUM = ("medium", "Medium", "Standard logs",           True)
	HIGH   = ("high",   "High",   "Debug/Verbose",           False)

	def __init__(self, level, label, desc, implemented):
		self.level = level
		self.label = label
		self.desc = desc
		self.implemented = implemented

# Used for the UI only
VERBOSITY_MAP = {
    "1": AppVerbosity.LOW,
    "2": AppVerbosity.MEDIUM,
    "3": AppVerbosity.HIGH,
}