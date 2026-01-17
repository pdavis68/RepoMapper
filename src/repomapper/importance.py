"""
Important file filtering for RepoMap.
"""

import os

IMPORTANT_FILENAMES = {
    "README.md",
    "README.txt",
    "readme.md",
    "README.rst",
    "README",
    "requirements.txt",
    "Pipfile",
    "pyproject.toml",
    "setup.py",
    "setup.cfg",
    "package.json",
    "yarn.lock",
    "package-lock.json",
    "npm-shrinkwrap.json",
    "Dockerfile",
    "docker-compose.yml",
    "docker-compose.yaml",
    ".gitignore",
    ".gitattributes",
    ".dockerignore",
    "Makefile",
    "makefile",
    "CMakeLists.txt",
    "LICENSE",
    "LICENSE.txt",
    "LICENSE.md",
    "COPYING",
    "CHANGELOG.md",
    "CHANGELOG.txt",
    "HISTORY.md",
    "CONTRIBUTING.md",
    "CODE_OF_CONDUCT.md",
    ".env",
    ".env.example",
    ".env.local",
    "tox.ini",
    "pytest.ini",
    ".pytest.ini",
    ".flake8",
    ".pylintrc",
    "mypy.ini",
    "go.mod",
    "go.sum",
    "Cargo.toml",
    "Cargo.lock",
    "pom.xml",
    "build.gradle",
    "build.gradle.kts",
    "composer.json",
    "composer.lock",
    "Gemfile",
    "Gemfile.lock",
}

IMPORTANT_DIR_PATTERNS = {
    os.path.normpath(".github/workflows"): lambda fname: fname.endswith((".yml", ".yaml")),
    os.path.normpath(".github"): lambda fname: fname.endswith((".md", ".yml", ".yaml")),
    os.path.normpath("docs"): lambda fname: fname.endswith((".md", ".rst", ".txt")),
}


def is_important(rel_file_path: str) -> bool:
    """Check if a file is considered important."""
    normalized_path = os.path.normpath(rel_file_path)
    file_name = os.path.basename(normalized_path)
    dir_name = os.path.dirname(normalized_path)

    # Check specific directory patterns
    for important_dir, checker_func in IMPORTANT_DIR_PATTERNS.items():
        if dir_name == important_dir and checker_func(file_name):
            return True

    # Check if the full normalized path is important
    if normalized_path in IMPORTANT_FILENAMES:
        return True

    # Check if just the basename is important
    if file_name in IMPORTANT_FILENAMES:
        return True

    return False


def filter_important_files(file_paths: list[str]) -> list[str]:
    """Filter list to only include important files."""
    return [path for path in file_paths if is_important(path)]
