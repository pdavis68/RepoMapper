"""
RepoMap class for generating repository maps.
"""

import os
import shutil
import sqlite3
import sys
from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

import diskcache
import networkx as nx
from grep_ast import TreeContext

from .scm import get_scm_fname
from .utils import Tag, count_tokens, read_text


@dataclass
class FileReport:
    excluded: dict[str, str]  # File -> exclusion reason with status
    definition_matches: int  # Total definition tags
    reference_matches: int  # Total reference tags
    total_files_considered: int  # Total files provided as input


# Constants
CACHE_VERSION = 1

TAGS_CACHE_DIR = os.path.join(os.getcwd(), f".repomap.tags.cache.v{CACHE_VERSION}")
SQLITE_ERRORS = (sqlite3.OperationalError, sqlite3.DatabaseError)


class RepoMap:
    """Main class for generating repository maps."""

    def __init__(
        self,
        map_tokens: int = 1024,
        root: str = None,
        token_counter_func: Callable[[str], int] = count_tokens,
        file_reader_func: Callable[[str], str | None] = read_text,
        output_handler_funcs: dict[str, Callable] = None,
        repo_content_prefix: str | None = None,
        verbose: bool = False,
        max_context_window: int | None = None,
        map_mul_no_files: int = 8,
        refresh: str = "auto",
        exclude_unranked: bool = False,
    ):
        """Initialize RepoMap instance."""
        self.map_tokens = map_tokens
        self.max_map_tokens = map_tokens
        self.root = Path(root or os.getcwd()).resolve()
        self.token_count_func_internal = token_counter_func
        self.read_text_func_internal = file_reader_func
        self.repo_content_prefix = repo_content_prefix
        self.verbose = verbose
        self.max_context_window = max_context_window
        self.map_mul_no_files = map_mul_no_files
        self.refresh = refresh
        self.exclude_unranked = exclude_unranked

        # Set up output handlers
        if output_handler_funcs is None:
            output_handler_funcs = {"info": print, "warning": print, "error": print}
        self.output_handlers = output_handler_funcs

        # Initialize caches
        self.tree_cache = {}
        self.tree_context_cache = {}
        self.map_cache = {}

        # Load persistent tags cache
        self.load_tags_cache()

    def load_tags_cache(self):
        """Load the persistent tags cache."""
        cache_dir = self.root / TAGS_CACHE_DIR
        try:
            self.TAGS_CACHE = diskcache.Cache(str(cache_dir))
        except Exception as e:
            self.output_handlers["warning"](f"Failed to load tags cache: {e}")
            self.TAGS_CACHE = {}

    def save_tags_cache(self):
        """Save the tags cache (no-op as diskcache handles persistence)."""
        pass

    def tags_cache_error(self):
        """Handle tags cache errors."""
        try:
            cache_dir = self.root / TAGS_CACHE_DIR
            if cache_dir.exists():
                shutil.rmtree(cache_dir)
            self.load_tags_cache()
        except Exception:
            self.output_handlers["warning"]("Failed to recreate tags cache, using in-memory cache")
            self.TAGS_CACHE = {}

    def token_count(self, text: str) -> int:
        """Count tokens in text with sampling optimization for long texts."""
        if not text:
            return 0

        len_text = len(text)
        if len_text < 200:
            return self.token_count_func_internal(text)

        # Sample for longer texts
        lines = text.splitlines(keepends=True)
        num_lines = len(lines)

        step = max(1, num_lines // 100)
        sampled_lines = lines[::step]
        sample_text = "".join(sampled_lines)

        if not sample_text:
            return self.token_count_func_internal(text)

        sample_tokens = self.token_count_func_internal(sample_text)

        if len(sample_text) == 0:
            return self.token_count_func_internal(text)

        est_tokens = (sample_tokens / len(sample_text)) * len_text
        return int(est_tokens)

    def get_rel_fname(self, fname: str) -> str:
        """Get relative filename from absolute path."""
        try:
            return str(Path(fname).relative_to(self.root))
        except ValueError:
            return fname

    def get_mtime(self, fname: str) -> float | None:
        """Get file modification time."""
        try:
            return os.path.getmtime(fname)
        except FileNotFoundError:
            self.output_handlers["warning"](f"File not found: {fname}")
            return None

    def get_tags(self, fname: str, rel_fname: str) -> list[Tag]:
        """Get tags for a file, using cache when possible."""
        file_mtime = self.get_mtime(fname)
        if file_mtime is None:
            return []

        try:
            # Handle both diskcache Cache and in-memory dict
            if isinstance(self.TAGS_CACHE, dict):
                cached_entry = self.TAGS_CACHE.get(fname)
            else:
                cached_entry = self.TAGS_CACHE.get(fname)

            if cached_entry and cached_entry.get("mtime") == file_mtime:
                return cached_entry["data"]
        except SQLITE_ERRORS:
            self.tags_cache_error()

        # Cache miss or file changed
        tags = self.get_tags_raw(fname, rel_fname)

        try:
            self.TAGS_CACHE[fname] = {"mtime": file_mtime, "data": tags}
        except SQLITE_ERRORS:
            self.tags_cache_error()

        return tags

    def get_tags_raw(self, fname: str, rel_fname: str) -> list[Tag]:
        """Parse file to extract tags using Tree-sitter."""
        try:
            from grep_ast import filename_to_lang
            from grep_ast.tsl import get_language, get_parser
            from tree_sitter import QueryCursor
        except ImportError:
            print("Error: grep-ast is required. Install with: pip install grep-ast")
            sys.exit(1)

        lang = filename_to_lang(fname)
        if not lang:
            return []

        try:
            language = get_language(lang)
            parser = get_parser(lang)
        except Exception as err:
            self.output_handlers["error"](f"Skipping file {fname}: {err}")
            return []

        scm_fname = get_scm_fname(lang)
        if not scm_fname:
            return []

        code = self.read_text_func_internal(fname)
        if not code:
            return []

        try:
            tree = parser.parse(bytes(code, "utf-8"))

            # Load query from SCM file
            query_text = read_text(scm_fname, silent=True)
            if not query_text:
                return []

            query = language.query(query_text)
            cursor = QueryCursor(query)
            captures = cursor.captures(tree.root_node)

            tags = []
            # Process captures as a dictionary
            for capture_name, nodes in captures.items():
                for node in nodes:
                    if "name.definition" in capture_name:
                        kind = "def"
                    elif "name.reference" in capture_name:
                        kind = "ref"
                    else:
                        # Skip other capture types like 'reference.call' if not needed for tagging
                        continue

                    line_num = node.start_point[0] + 1
                    # Handle potential None value
                    name = node.text.decode("utf-8") if node.text else ""

                    tags.append(
                        Tag(rel_fname=rel_fname, fname=fname, line=line_num, name=name, kind=kind)
                    )

            return tags

        except Exception as e:
            self.output_handlers["error"](f"Error parsing {fname}: {e}")
            return []

    def get_ranked_tags(
        self,
        chat_fnames: list[str],
        other_fnames: list[str],
        mentioned_fnames: set[str] | None = None,
        mentioned_idents: set[str] | None = None,
    ) -> tuple[list[tuple[float, Tag]], FileReport]:
        """Get ranked tags using PageRank algorithm with file report."""
        # Return empty list and empty report if no files
        if not chat_fnames and not other_fnames:
            return [], FileReport([], {}, 0, 0, 0)

        # Initialize file report early
        included: list[str] = []
        excluded: dict[str, str] = {}
        total_definitions = 0
        total_references = 0
        if mentioned_fnames is None:
            mentioned_fnames = set()
        if mentioned_idents is None:
            mentioned_idents = set()

        # Normalize paths to absolute
        def normalize_path(path):
            return str(Path(path).resolve())

        chat_fnames = [normalize_path(f) for f in chat_fnames]
        other_fnames = [normalize_path(f) for f in other_fnames]

        # Initialize file report
        included: list[str] = []
        excluded: dict[str, str] = {}
        total_definitions = 0
        total_references = 0

        # Collect all tags
        defines = defaultdict(set)
        references = defaultdict(set)
        definitions = defaultdict(set)

        personalization = {}
        chat_rel_fnames = set(self.get_rel_fname(f) for f in chat_fnames)

        all_fnames = list(set(chat_fnames + other_fnames))

        for fname in all_fnames:
            rel_fname = self.get_rel_fname(fname)

            if not os.path.exists(fname):
                reason = "File not found"
                excluded[fname] = reason
                self.output_handlers["warning"](f"Repo-map can't include {fname}: {reason}")
                continue

            included.append(fname)

            tags = self.get_tags(fname, rel_fname)

            for tag in tags:
                if tag.kind == "def":
                    defines[tag.name].add(rel_fname)
                    definitions[rel_fname].add(tag.name)
                    total_definitions += 1
                elif tag.kind == "ref":
                    references[tag.name].add(rel_fname)
                    total_references += 1

            # Set personalization for chat files
            if fname in chat_fnames:
                personalization[rel_fname] = 100.0

        # Build graph
        G = nx.MultiDiGraph()

        # Add nodes
        for fname in all_fnames:
            rel_fname = self.get_rel_fname(fname)
            G.add_node(rel_fname)

        # Add edges based on references
        for name, ref_fnames in references.items():
            def_fnames = defines.get(name, set())
            for ref_fname in ref_fnames:
                for def_fname in def_fnames:
                    if ref_fname != def_fname:
                        G.add_edge(ref_fname, def_fname, name=name)

        if not G.nodes():
            return [], FileReport(excluded, 0, 0, len(all_fnames))

        # Run PageRank
        try:
            if personalization:
                ranks = nx.pagerank(G, personalization=personalization, alpha=0.85)
            else:
                ranks = nx.pagerank(G, alpha=0.85)
        except Exception as e:
            print(f"Error during PageRank: {e}")
            try:
                # If personalization caused the crash, try standard PageRank
                ranks = nx.pagerank(G, alpha=0.85)
            except Exception:
                # If both fail, fallback to uniform
                ranks = {node: 1.0 for node in G.nodes()}

        # Update excluded dictionary with status information
        for fname in set(chat_fnames + other_fnames):
            if fname in excluded:
                # Add status prefix to existing exclusion reason
                excluded[fname] = f"[EXCLUDED] {excluded[fname]}"
            elif fname not in included:
                excluded[fname] = "[NOT PROCESSED] File not included in final processing"

        # Create file report
        file_report = FileReport(
            excluded=excluded,
            definition_matches=total_definitions,
            reference_matches=total_references,
            total_files_considered=len(all_fnames),
        )

        # Collect and rank tags
        ranked_tags = []

        for fname in included:
            rel_fname = self.get_rel_fname(fname)
            file_rank = ranks.get(rel_fname, 0.0)

            # Exclude files with low Page Rank if exclude_unranked is True
            if (
                self.exclude_unranked and file_rank <= 0.0001
            ):  # Use a small threshold to exclude near-zero ranks
                continue

            tags = self.get_tags(fname, rel_fname)
            for tag in tags:
                if tag.kind == "def":
                    # Boost for mentioned identifiers
                    boost = 1.0
                    if tag.name in mentioned_idents:
                        boost *= 10.0
                    if rel_fname in mentioned_fnames:
                        boost *= 5.0
                    if rel_fname in chat_rel_fnames:
                        boost *= 20.0

                    final_rank = file_rank * boost
                    ranked_tags.append((final_rank, tag))

        # Sort by rank (descending)
        ranked_tags.sort(key=lambda x: x[0], reverse=True)

        return ranked_tags, file_report

    def render_tree(self, abs_fname: str, rel_fname: str, lois: list[int]) -> str:
        """Render a code snippet with specific lines of interest."""
        code = self.read_text_func_internal(abs_fname)
        if not code:
            return ""

        # Use TreeContext for rendering
        try:
            if rel_fname not in self.tree_context_cache:
                self.tree_context_cache[rel_fname] = TreeContext(rel_fname, code, color=False)

            tree_context = self.tree_context_cache[rel_fname]
            return tree_context.format(lois)
        except Exception:
            # Fallback to simple line extraction
            lines = code.splitlines()
            result_lines = [f"{rel_fname}:"]

            for loi in sorted(set(lois)):
                if 1 <= loi <= len(lines):
                    result_lines.append(f"{loi:4d}: {lines[loi - 1]}")

            return "\n".join(result_lines)

    def to_tree(self, tags: list[tuple[float, Tag]], chat_rel_fnames: set[str]) -> str:
        """Convert ranked tags to formatted tree output."""
        if not tags:
            return ""

        # Group tags by file
        file_tags = defaultdict(list)
        for rank, tag in tags:
            file_tags[tag.rel_fname].append((rank, tag))

        # Sort files by importance (max rank of their tags)
        sorted_files = sorted(
            file_tags.items(), key=lambda x: max(rank for rank, tag in x[1]), reverse=True
        )

        tree_parts = []

        for rel_fname, file_tag_list in sorted_files:
            # Get lines of interest
            lois = [tag.line for rank, tag in file_tag_list]

            # Find absolute filename
            abs_fname = str(self.root / rel_fname)

            # Get the max rank for the file
            max_rank = max(rank for rank, tag in file_tag_list)

            # Render the tree for this file
            rendered = self.render_tree(abs_fname, rel_fname, lois)
            if rendered:
                # Add rank value to the output
                rendered_lines = rendered.splitlines()
                first_line = rendered_lines[0]
                code_lines = rendered_lines[1:]

                tree_parts.append(
                    f"{first_line}\n"
                    f"(Rank value: {max_rank:.4f})\n\n"  # Added an extra newline here
                    + "\n".join(code_lines)
                )

        return "\n\n".join(tree_parts)

    def get_ranked_tags_map(
        self,
        chat_fnames: list[str],
        other_fnames: list[str],
        max_map_tokens: int,
        mentioned_fnames: set[str] | None = None,
        mentioned_idents: set[str] | None = None,
        force_refresh: bool = False,
    ) -> str | None:
        """Get the ranked tags map with caching."""
        cache_key = (
            tuple(sorted(chat_fnames)),
            tuple(sorted(other_fnames)),
            max_map_tokens,
            tuple(sorted(mentioned_fnames or [])),
            tuple(sorted(mentioned_idents or [])),
        )

        if not force_refresh and cache_key in self.map_cache:
            return self.map_cache[cache_key]

        result = self.get_ranked_tags_map_uncached(
            chat_fnames, other_fnames, max_map_tokens, mentioned_fnames, mentioned_idents
        )

        self.map_cache[cache_key] = result
        return result

    def generate_file_overview(
        self, all_files: list[str], files_in_map: set[str], file_report: FileReport
    ) -> str:
        """Generate a summary of files not included in the detailed map.

        Only shows excluded and cutoff files since included files are
        already visible in the detailed code map.
        """
        if not all_files:
            return ""

        # Collect files that aren't in the map
        cutoff_files = []
        excluded_files = []

        sorted_files = sorted(all_files, key=lambda f: self.get_rel_fname(f))

        for fname in sorted_files:
            if fname in files_in_map:
                continue
            rel_fname = self.get_rel_fname(fname)
            if fname in file_report.excluded:
                reason = (
                    file_report.excluded[fname]
                    .replace("[EXCLUDED] ", "")
                    .replace("[NOT PROCESSED] ", "")
                )
                excluded_files.append((rel_fname, reason))
            else:
                cutoff_files.append(rel_fname)

        # If everything is included, no need for an overview section
        if not cutoff_files and not excluded_files:
            return ""

        overview_lines = []

        if cutoff_files:
            overview_lines.append(f"Files not shown (token limit): {len(cutoff_files)}")
            for rel_fname in cutoff_files:
                overview_lines.append(f"  [-] {rel_fname}")
            overview_lines.append("")

        if excluded_files:
            overview_lines.append(f"Files excluded: {len(excluded_files)}")
            for rel_fname, reason in excluded_files:
                overview_lines.append(f"  [x] {rel_fname} ({reason})")
            overview_lines.append("")

        return "\n".join(overview_lines)

    def get_ranked_tags_map_uncached(
        self,
        chat_fnames: list[str],
        other_fnames: list[str],
        max_map_tokens: int,
        mentioned_fnames: set[str] | None = None,
        mentioned_idents: set[str] | None = None,
    ) -> tuple[str | None, FileReport]:
        """Generate the ranked tags map without caching."""
        ranked_tags, file_report = self.get_ranked_tags(
            chat_fnames, other_fnames, mentioned_fnames, mentioned_idents
        )

        if not ranked_tags:
            return None, file_report

        # Binary search to find the right number of tags
        chat_rel_fnames = set(self.get_rel_fname(f) for f in chat_fnames)

        def try_tags(num_tags: int) -> tuple[str | None, int, set[str]]:
            if num_tags <= 0:
                return None, 0, set()

            selected_tags = ranked_tags[:num_tags]
            tree_output = self.to_tree(selected_tags, chat_rel_fnames)

            if not tree_output:
                return None, 0, set()

            # Extract files that are in this output
            files_in_output = set(tag.fname for rank, tag in selected_tags)

            tokens = self.token_count(tree_output)
            return tree_output, tokens, files_in_output

        # Binary search for optimal number of tags
        left, right = 0, len(ranked_tags)
        best_tree = None
        best_files = set()

        while left <= right:
            mid = (left + right) // 2
            tree_output, tokens, files_in_output = try_tags(mid)

            if tree_output and tokens <= max_map_tokens:
                best_tree = tree_output
                best_files = files_in_output
                left = mid + 1
            else:
                right = mid - 1

        # Generate file overview if we have a tree (only when verbose)
        if best_tree:
            if self.verbose:
                all_files = list(set(chat_fnames + other_fnames))
                overview = self.generate_file_overview(all_files, best_files, file_report)
                if overview:
                    best_tree = best_tree + "\n\n" + overview

        return best_tree, file_report

    def get_repo_map(
        self,
        chat_files: list[str] = None,
        other_files: list[str] = None,
        mentioned_fnames: set[str] | None = None,
        mentioned_idents: set[str] | None = None,
        force_refresh: bool = False,
    ) -> tuple[str | None, FileReport]:
        """Generate the repository map with file report."""
        if chat_files is None:
            chat_files = []
        if other_files is None:
            other_files = []

        # Create empty report for error cases
        empty_report = FileReport({}, 0, 0, 0)

        if self.max_map_tokens <= 0 or not other_files:
            return None, empty_report

        # Adjust max_map_tokens if no chat files
        max_map_tokens = self.max_map_tokens
        if not chat_files and self.max_context_window:
            padding = 1024
            available = self.max_context_window - padding
            max_map_tokens = min(max_map_tokens * self.map_mul_no_files, available)

        try:
            # get_ranked_tags_map returns (map_string, file_report)
            map_string, file_report = self.get_ranked_tags_map(
                chat_files,
                other_files,
                max_map_tokens,
                mentioned_fnames,
                mentioned_idents,
                force_refresh,
            )
        except RecursionError:
            self.output_handlers["error"]("Disabling repo map, git repo too large?")
            self.max_map_tokens = 0
            return None, FileReport({}, 0, 0, 0)  # Ensure consistent return type

        if map_string is None:
            print("map_string is None")
            return None, file_report

        if self.verbose:
            tokens = self.token_count(map_string)
            self.output_handlers["info"](f"Repo-map: {tokens / 1024:.1f} k-tokens")

        # Format final output
        other = "other " if chat_files else ""

        if self.repo_content_prefix:
            repo_content = self.repo_content_prefix.format(other=other)
        else:
            repo_content = ""

        repo_content += map_string

        return repo_content, file_report
