import os
import subprocess

from pygount import SourceAnalysis

def count_lines_of_code(repo_path: str):
    """
    Counts total lines in the repository using pygount, excluding hidden files and directories.
    """
    total_lines = 0
    for root, dirs, files in os.walk(repo_path):
        # Exclude hidden directories
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        for file in files:
            # Exclude hidden files
            if file.startswith('.'):
                continue
            file_path = os.path.join(root, file)
            try:
                analysis = SourceAnalysis.from_file(file_path, group=repo_path)
                total_lines += analysis.line_count
            except Exception:
                # Skip files that cannot be analyzed
                continue
    return total_lines

def get_repo_tree(repo_path: str):
    """
    Captures the file tree structure of the repository.
    """
    tree_data = {}
    for root, dirs, files in os.walk(repo_path):
        # Exclude hidden directories
        dirs[:] = [d for d in dirs if not d.startswith('.')]
        
        rel_path = os.path.relpath(root, repo_path)
        if rel_path == ".":
            current = tree_data
        else:
            parts = rel_path.split(os.sep)
            current = tree_data
            for part in parts:
                if part not in current:
                    current[part] = {}
                current = current[part]
        
        for file in files:
            if not file.startswith('.'):
                current[file] = None # Mark as file
    return tree_data

def clone_repo(clone_url: str, temp_dir: str):
    """
    Clones a repository using git.
    """
    subprocess.run(["git", "clone", "--depth", "1", clone_url, temp_dir], check=True, capture_output=True)
