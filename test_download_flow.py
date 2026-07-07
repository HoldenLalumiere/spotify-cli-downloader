import threading
import time
import unittest
from unittest.mock import patch, MagicMock, mock_open
import os

from download import DownloadProcessor
from preference_manager import AppVerbosity
from config import AppAudioFormat, AppAudioQuality

_real_sleep = time.sleep

# Mock the DownloadSettings dataclass structure locally for the test runner
class MockDownloadSettings:
	def __init__(self):
		self.download_dir = "/fake/download/path"
		# Create mock audio options mirroring your configuration maps
		self.audio_format = MagicMock()
		self.audio_format.ext = ".ogg"
		self.audio_quality = MagicMock()
		self.audio_quality.librespot_quality = "VERY_HIGH"


class TestDownloadProcessorSimulation(unittest.TestCase):

	@patch('download.OggVorbis')
	@patch('download.os.remove')
	@patch('download.os.rename')
	@patch('download.os.chdir')
	@patch('download.os.makedirs')
	@patch('download.os.path.exists')
	@patch('download._safe_api_call')
	@patch('download._get_stream_session')
	@patch('download.init_spotify_cred')
	def test_low_verbosity_progress_bar_flow(self, mock_init_cred, mock_get_session,
	                                         mock_safe_call, mock_exists,
	                                         mock_makedirs, mock_chdir,
	                                         mock_rename, mock_remove, mock_oggvorbis):
		"""Simulates a multi-track download to visually check the LOW verbosity progress bar."""

		# 1. Set up a fake playlist payload containing 3 tracks
		fake_tags_list = [
			{"id": f"id{i}", "title": f"Song {i}", "artist": f"Artist {chr(65 + (i % 26))}", "image_url": None}
			for i in range(1, 51)
		]

		# 2. Force our file-checker mock to report that NONE of these files exist locally yet
		mock_exists.return_value = False

		interrupt_event = threading.Event()

		# 3. Prevent real file writing operations by patching built-in open() out of existence
		with patch("builtins.open", mock_open()):
			# Also patch out time.sleep so our test suite runs instantly without waiting 7 seconds per track!
			with patch("download.time.sleep") as mock_sleep:
				mock_sleep.side_effect = lambda seconds: interrupt_event.wait(1)
				# 4. Instantiate the processor with LOW verbosity
				settings = MockDownloadSettings()
				processor = DownloadProcessor(
					url="https://open.spotify.com/playlist/fakeID123",
					download_settings=settings,
					verbosity=AppVerbosity.LOW
				)

				# 5. Run the inner engine loop manually by directly feeding our fake tags
				processor._download_collection(
					collection_name="Test Playlist",
					tags_list=fake_tags_list,
					download_dir=settings.download_dir,
					original_dir="/fake/program/root"
				)

				# 6. Verify our logic ran correctly under the hood
				self.assertEqual(mock_sleep.call_count, 51)
				print("\n[!] Simulation complete. Verify that the progress bar rendered accurately above.")


if __name__ == '__main__':
	unittest.main()