"""
SCM file handling for RepoMap.
"""

from pathlib import Path


def get_scm_fname(lang: str) -> str | None:
    """Get the SCM query file for a language."""
    scm_files = {
        "arduino": "arduino-tags.scm",
        "chatito": "chatito-tags.scm",
        "commonlisp": "commonlisp-tags.scm",
        "cpp": "cpp-tags.scm",
        "csharp": "csharp-tags.scm",
        "c": "c-tags.scm",
        "dart": "dart-tags.scm",
        "d": "d-tags.scm",
        "elisp": "elisp-tags.scm",
        "elixir": "elixir-tags.scm",
        "elm": "elm-tags.scm",
        "gleam": "gleam-tags.scm",
        "go": "go-tags.scm",
        "javascript": "javascript-tags.scm",
        "java": "java-tags.scm",
        "lua": "lua-tags.scm",
        "ocaml_interface": "ocaml_interface-tags.scm",
        "ocaml": "ocaml-tags.scm",
        "pony": "pony-tags.scm",
        "properties": "properties-tags.scm",
        "python": "python-tags.scm",
        "racket": "racket-tags.scm",
        "r": "r-tags.scm",
        "ruby": "ruby-tags.scm",
        "rust": "rust-tags.scm",
        "solidity": "solidity-tags.scm",
        "swift": "swift-tags.scm",
        "udev": "udev-tags.scm",
        "c_sharp": "c_sharp-tags.scm",
        "hcl": "hcl-tags.scm",
        "kotlin": "kotlin-tags.scm",
        "php": "php-tags.scm",
        "ql": "ql-tags.scm",
        "scala": "scala-tags.scm",
        "typescript": "typescript-tags.scm",
    }

    if lang in scm_files:
        scm_filename = scm_files[lang]
        # Search in tree-sitter-language-pack
        scm_path = Path(__file__).parent / "queries" / "tree-sitter-language-pack" / scm_filename
        if scm_path.exists():
            return str(scm_path)
        # Search in tree-sitter-languages
        scm_path = Path(__file__).parent / "queries" / "tree-sitter-languages" / scm_filename
        if scm_path.exists():
            return str(scm_path)

    return None
