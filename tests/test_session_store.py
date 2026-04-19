import os
import shutil
import tempfile
import unittest

from github_crawler.session_store import create_session, delete_session, list_sessions, update_session_metadata


class TestSessionStore(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_create_session_persists_metadata_and_directories(self):
        session = create_session(self.test_dir, "Find graph databases", "Look for auth middleware")

        self.assertTrue(os.path.isdir(session.session_dir))
        self.assertTrue(os.path.isdir(session.clone_root))
        self.assertTrue(os.path.isdir(session.artifact_dir))

        sessions = list_sessions(self.test_dir)
        self.assertEqual(len(sessions), 1)
        self.assertEqual(sessions[0]["repository_request"], "Find graph databases")

    def test_delete_session_can_archive_before_removal(self):
        session = create_session(self.test_dir, "Find graph databases", "Look for auth middleware")
        update_session_metadata(session, {"status": "complete", "result_count": 2})

        archive_path = delete_session(self.test_dir, session.session_id, persist_archive=True)

        self.assertTrue(os.path.exists(archive_path))
        self.assertEqual(list_sessions(self.test_dir), [])


if __name__ == "__main__":
    unittest.main()
