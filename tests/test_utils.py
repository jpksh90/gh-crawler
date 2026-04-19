
import os
import shutil
import tempfile
import unittest
from github_crawler.github_utils import count_lines_of_code, get_repo_tree

class TestCrawlerUtils(unittest.TestCase):
    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        
        # Create some files and directories
        os.makedirs(os.path.join(self.test_dir, "src"))
        os.makedirs(os.path.join(self.test_dir, ".git")) # Hidden dir
        
        with open(os.path.join(self.test_dir, "root_file.txt"), "w") as f:
            f.write("Line 1\nLine 2\n")
            
        with open(os.path.join(self.test_dir, "src", "main.py"), "w") as f:
            f.write("import os\n\ndef main():\n    pass\n")
            
        with open(os.path.join(self.test_dir, ".git", "config"), "w") as f:
            f.write("hidden config\n")
            
        with open(os.path.join(self.test_dir, ".hidden_file"), "w") as f:
            f.write("hidden file\n")

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_count_lines_of_code(self):
        # 2 lines in root_file.txt + 4 lines in src/main.py = 6 lines
        # .git/ and .hidden_file should be ignored.
        total_lines = count_lines_of_code(self.test_dir)
        self.assertEqual(total_lines, 6)

    def test_get_repo_tree(self):
        tree = get_repo_tree(self.test_dir)
        
        # Check if expected structure is there
        self.assertIn("root_file.txt", tree)
        self.assertIn("src", tree)
        self.assertIn("main.py", tree["src"])
        
        # Check if hidden files/dirs are excluded
        self.assertNotIn(".git", tree)
        self.assertNotIn(".hidden_file", tree)

if __name__ == "__main__":
    unittest.main()
