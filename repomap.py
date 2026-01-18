#!/usr/bin/env python3
"""
Standalone RepoMap Tool

A command-line tool that generates a "map" of a software repository,
highlighting important files and definitions based on their relevance.
Uses Tree-sitter for parsing and PageRank for ranking importance.
"""

import argparse
import os
import sys
from pathlib import Path
from typing import List

from utils import count_tokens, read_text, Tag
from scm import get_scm_fname
from importance import is_important, filter_important_files
from repomap_class import RepoMap


def find_src_files(directory: str) -> List[str]:
    """Find source files in a directory."""
    if not os.path.isdir(directory):
        return [directory] if os.path.isfile(directory) else []

    src_files = []
    for root, dirs, files in os.walk(directory):
        # Skip hidden directories and common non-source directories
        dirs[:] = [
            d
            for d in dirs
            if not d.startswith(".")
            and d not in {"node_modules", "__pycache__", "venv", "env"}
        ]

        for file in files:
            if not file.startswith("."):
                full_path = os.path.join(root, file)
                src_files.append(full_path)

    return src_files


def tool_output(*messages):
    """Print informational messages."""
    print(*messages, file=sys.stdout)


def tool_warning(message):
    """Print warning messages."""
    print(f"Warning: {message}", file=sys.stderr)


def tool_error(message):
    """Print error messages."""
    print(f"Error: {message}", file=sys.stderr)


def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Generate a repository map showing important code structures.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s .                    # Map current directory
  %(prog)s src/ --map-tokens 2048  # Map src/ with 2048 token limit
  %(prog)s file1.py file2.py    # Map specific files
  %(prog)s --chat-files main.py --other-files src/  # Specify chat vs other files
        """,
    )

    parser.add_argument(
        "paths", nargs="*", help="Files or directories to include in the map"
    )

    parser.add_argument(
        "--root",
        default=".",
        help="Repository root directory (default: current directory)",
    )

    parser.add_argument(
        "--map-tokens",
        type=int,
        default=8192,
        help="Maximum tokens for the generated map (default: 8192)",
    )

    parser.add_argument(
        "--chat-files",
        nargs="*",
        help="Files currently being edited (given higher priority)",
    )

    parser.add_argument(
        "--other-files", nargs="*", help="Other files to consider for the map"
    )

    parser.add_argument(
        "--mentioned-files",
        nargs="*",
        help="Files explicitly mentioned (given higher priority)",
    )

    parser.add_argument(
        "--mentioned-idents",
        nargs="*",
        help="Identifiers explicitly mentioned (given higher priority)",
    )

    parser.add_argument("--verbose", action="store_true", help="Enable verbose output")

    parser.add_argument(
        "--model",
        default="gpt-4",
        help="Model name for token counting (default: gpt-4)",
    )

    parser.add_argument(
        "--max-context-window", type=int, help="Maximum context window size"
    )

    parser.add_argument(
        "--force-refresh", action="store_true", help="Force refresh of caches"
    )

    parser.add_argument(
        "--exclude-unranked",
        action="store_true",
        help="Exclude files with Page Rank 0 from the map",
    )

    args = parser.parse_args()

    # Set up token counter with specified model
    def token_counter(text: str) -> int:
        return count_tokens(text, args.model)

    # Set up output handlers
    output_handlers = {
        "info": tool_output,
        "warning": tool_warning,
        "error": tool_error,
    }

    # Process file arguments
    chat_files_from_args = (
        args.chat_files or []
    )  # These are the paths as strings from the CLI

    # Determine the list of unresolved path specifications that will form the 'other_files'
    # These can be files or directories. find_src_files will expand them.
    unresolved_paths_for_other_files_specs = []
    if args.other_files:  # If --other-files is explicitly provided, it's the source
        unresolved_paths_for_other_files_specs.extend(args.other_files)
    elif args.paths:  # Else, if positional paths are given, they are the source
        unresolved_paths_for_other_files_specs.extend(args.paths)
    # If neither, unresolved_paths_for_other_files_specs remains empty.

    # Now, expand all directory paths in unresolved_paths_for_other_files_specs into actual file lists
    # and collect all file paths. find_src_files handles both files and directories.
    effective_other_files_unresolved = []
    for path_spec_str in unresolved_paths_for_other_files_specs:
        effective_other_files_unresolved.extend(find_src_files(path_spec_str))

    # Convert to absolute paths
    root_path = Path(args.root).resolve()
    # chat_files for RepoMap are from --chat-files argument, resolved.
    chat_files = [str(Path(f).resolve()) for f in chat_files_from_args]
    # other_files for RepoMap are the effective_other_files, resolved after expansion.
    other_files = [str(Path(f).resolve()) for f in effective_other_files_unresolved]

    print(f"Chat files: {chat_files}")

    # Convert mentioned files to sets
    mentioned_fnames = set(args.mentioned_files) if args.mentioned_files else None
    mentioned_idents = set(args.mentioned_idents) if args.mentioned_idents else None

    # Create RepoMap instance
    repo_map = RepoMap(
        map_tokens=args.map_tokens,
        root=str(root_path),
        token_counter_func=token_counter,
        file_reader_func=read_text,
        output_handler_funcs=output_handlers,
        verbose=args.verbose,
        max_context_window=args.max_context_window,
        exclude_unranked=args.exclude_unranked,
    )

    # Generate the map
    try:
        map_content, _file_report = repo_map.get_repo_map(
            chat_files=chat_files,
            other_files=other_files,
            mentioned_fnames=mentioned_fnames,
            mentioned_idents=mentioned_idents,
            force_refresh=args.force_refresh,
        )

        if map_content:
            if args.verbose:
                tokens = repo_map.token_count(map_content)
                tool_output(
                    f"Generated map: {len(map_content)} chars, ~{tokens} tokens"
                )

            print(map_content)
        else:
            tool_output("No repository map generated.")

    except KeyboardInterrupt:
        tool_error("Interrupted by user")
        sys.exit(1)
    except Exception as e:
        tool_error(f"Error generating repository map: {e}")
        if args.verbose:
            import traceback

            traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
