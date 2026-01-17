import asyncio
import logging
import os
from pathlib import Path
from typing import Any

from fastmcp import FastMCP, settings

from .repomap_class import RepoMap
from .utils import count_tokens, read_text


# Helper function from your CLI, useful to have here
def find_src_files(directory: str) -> list[str]:
    if not os.path.isdir(directory):
        return [directory] if os.path.isfile(directory) else []
    src_files = []
    for r, d, f_list in os.walk(directory):
        d[:] = [
            d_name
            for d_name in d
            if not d_name.startswith(".")
            and d_name not in {"node_modules", "__pycache__", "venv", "env"}
        ]
        for f in f_list:
            if not f.startswith("."):
                src_files.append(os.path.join(r, f))
    return src_files


# Configure logging - only show errors
root_logger = logging.getLogger()
root_logger.setLevel(logging.ERROR)

# Create console handler for errors only
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.ERROR)
console_formatter = logging.Formatter(
    "%(levelname)-5s %(asctime)-15s %(name)s:%(funcName)s:%(lineno)d - %(message)s"
)
console_handler.setFormatter(console_formatter)
root_logger.addHandler(console_handler)

# Suppress FastMCP logs
fastmcp_logger = logging.getLogger("fastmcp")
fastmcp_logger.setLevel(logging.ERROR)
# Suppress server startup message
server_logger = logging.getLogger("fastmcp.server")
server_logger.setLevel(logging.ERROR)

log = logging.getLogger(__name__)

# Set global stateless_http setting
settings.stateless_http = True

# Create MCP server
mcp = FastMCP("RepoMapServer")


@mcp.tool()
async def repo_map(
    project_root: str,
    chat_files: list[str] | None = None,
    other_files: list[str] | None = None,
    token_limit: Any = 8192,  # Accept any type to handle empty strings
    exclude_unranked: bool = False,
    force_refresh: bool = False,
    mentioned_files: list[str] | None = None,
    mentioned_idents: list[str] | None = None,
    verbose: bool = False,
    max_context_window: int | None = None,
) -> dict[str, Any]:
    """Generate a repository map for the specified files, providing a list of function prototypes and variables for files as well as relevant related
    files. Provide filenames relative to the project_root. In addition to the files provided, relevant related files will also be included with a
    very small ranking boost.

    :param project_root: Root directory of the project to search.  (must be an absolute path!)
    :param chat_files: A list of file paths that are currently in the chat context. These files will receive the highest ranking.
    :param other_files: A list of other relevant file paths in the repository to consider for the map. They receive a lower ranking boost than mentioned_files and chat_files.
    :param token_limit: The maximum number of tokens the generated repository map should occupy. Defaults to 8192.
    :param exclude_unranked: If True, files with a PageRank of 0.0 will be excluded from the map. Defaults to False.
    :param force_refresh: If True, forces a refresh of the repository map cache. Defaults to False.
    :param mentioned_files: Optional list of file paths explicitly mentioned in the conversation and receive a mid-level ranking boost.
    :param mentioned_idents: Optional list of identifiers explicitly mentioned in the conversation, to boost their ranking.
    :param verbose: If True, enables verbose logging for the RepoMap generation process. Defaults to False.
    :param max_context_window: Optional maximum context window size for token calculation, used to adjust map token limit when no chat files are provided.
    :returns: A dictionary containing:
        - 'map': the generated repository map string
        - 'report': a dictionary with file processing details including:
            - 'included': list of processed files
            - 'excluded': dictionary of excluded files with reasons
            - 'definition_matches': count of matched definitions
            - 'reference_matches': count of matched references
            - 'total_files_considered': total files processed
        Or an 'error' key if an error occurred.
    """
    if not os.path.isdir(project_root):
        return {"error": f"Project root directory not found: {project_root}"}

    # 1. Handle and validate parameters
    # Convert token_limit to integer with fallback
    try:
        token_limit = int(token_limit) if token_limit else 8192
    except (TypeError, ValueError):
        token_limit = 8192

    # Ensure token_limit is positive
    if token_limit <= 0:
        token_limit = 8192

    chat_files_list = chat_files or []
    mentioned_fnames_set = set(mentioned_files) if mentioned_files else None
    mentioned_idents_set = set(mentioned_idents) if mentioned_idents else None

    # 2. If a specific list of other_files isn't provided, scan the whole root directory.
    # This should happen regardless of whether chat_files are present.
    effective_other_files = []
    if other_files:
        effective_other_files = other_files
    else:
        log.info("No other_files provided, scanning root directory for context...")
        effective_other_files = find_src_files(project_root)

    # Add a print statement for debugging so you can see what the tool is working with.
    log.debug(f"Chat files: {chat_files_list}")
    log.debug(f"Effective other_files count: {len(effective_other_files)}")

    # If after all that we have no files, we can exit early.
    if not chat_files_list and not effective_other_files:
        log.info("No files to process.")
        return {"map": "No files found to generate a map."}

    # 3. Resolve paths relative to project root
    root_path = Path(project_root).resolve()
    abs_chat_files = [str(root_path / f) for f in chat_files_list]
    abs_other_files = [str(root_path / f) for f in effective_other_files]

    # Remove any chat files from the other_files list to avoid duplication
    abs_chat_files_set = set(abs_chat_files)
    abs_other_files = [f for f in abs_other_files if f not in abs_chat_files_set]

    # 4. Instantiate and run RepoMap
    try:
        repo_mapper = RepoMap(
            map_tokens=token_limit,
            root=str(root_path),
            token_counter_func=lambda text: count_tokens(text, "gpt-4"),
            file_reader_func=read_text,
            output_handler_funcs={"info": log.info, "warning": log.warning, "error": log.error},
            verbose=verbose,
            exclude_unranked=exclude_unranked,
            max_context_window=max_context_window,
        )
    except Exception as e:
        log.exception(f"Failed to initialize RepoMap for project '{project_root}': {e}")
        return {"error": f"Failed to initialize RepoMap: {str(e)}"}

    try:
        map_content, file_report = await asyncio.to_thread(
            repo_mapper.get_repo_map,
            chat_files=abs_chat_files,
            other_files=abs_other_files,
            mentioned_fnames=mentioned_fnames_set,
            mentioned_idents=mentioned_idents_set,
            force_refresh=force_refresh,
        )

        # Convert FileReport to dictionary for JSON serialization
        report_dict = {
            "excluded": file_report.excluded,
            "definition_matches": file_report.definition_matches,
            "reference_matches": file_report.reference_matches,
            "total_files_considered": file_report.total_files_considered,
        }

        return {
            "map": map_content or "No repository map could be generated.",
            "report": report_dict,
        }
    except Exception as e:
        log.exception(f"Error generating repository map for project '{project_root}': {e}")
        return {"error": f"Error generating repository map: {str(e)}"}


@mcp.tool()
async def search_identifiers(
    project_root: str,
    query: str,
    max_results: int = 50,
    context_lines: int = 2,
    include_definitions: bool = True,
    include_references: bool = True,
) -> dict[str, Any]:
    """Search for identifiers in code files. Get back a list of matching identifiers with their file, line number, and context.
       When searching, just use the identifier name without any special characters, prefixes or suffixes. The search is
       case-insensitive.

    Args:
        project_root: Root directory of the project to search.  (must be an absolute path!)
        query: Search query (identifier name)
        max_results: Maximum number of results to return
        context_lines: Number of lines of context to show
        include_definitions: Whether to include definition occurrences
        include_references: Whether to include reference occurrences

    Returns:
        Dictionary containing search results or error message
    """
    if not os.path.isdir(project_root):
        return {"error": f"Project root directory not found: {project_root}"}

    try:
        # Initialize RepoMap with search-specific settings
        repo_map = RepoMap(
            root=project_root,
            token_counter_func=lambda text: count_tokens(text, "gpt-4"),
            file_reader_func=read_text,
            output_handler_funcs={"info": log.info, "warning": log.warning, "error": log.error},
            verbose=False,
            exclude_unranked=True,
        )

        # Find all source files in the project
        all_files = find_src_files(project_root)

        # Get all tags (definitions and references) for all files
        all_tags = []
        for file_path in all_files:
            rel_path = str(Path(file_path).relative_to(project_root))
            tags = repo_map.get_tags(file_path, rel_path)
            all_tags.extend(tags)

        # Filter tags based on search query and options
        matching_tags = []
        query_lower = query.lower()

        for tag in all_tags:
            if query_lower in tag.name.lower():
                if (tag.kind == "def" and include_definitions) or (
                    tag.kind == "ref" and include_references
                ):
                    matching_tags.append(tag)

        # Sort by relevance (definitions first, then references)
        matching_tags.sort(key=lambda x: (x.kind != "def", x.name.lower().find(query_lower)))

        # Limit results
        matching_tags = matching_tags[:max_results]

        # Format results with context
        results = []
        for tag in matching_tags:
            file_path = str(Path(project_root) / tag.rel_fname)

            # Calculate context range based on context_lines parameter
            start_line = max(1, tag.line - context_lines)
            end_line = tag.line + context_lines
            context_range = list(range(start_line, end_line + 1))

            context = repo_map.render_tree(file_path, tag.rel_fname, context_range)

            if context:
                results.append(
                    {
                        "file": tag.rel_fname,
                        "line": tag.line,
                        "name": tag.name,
                        "kind": tag.kind,
                        "context": context,
                    }
                )

        return {"results": results}

    except Exception as e:
        log.exception(f"Error searching identifiers in project '{project_root}': {e}")
        return {"error": f"Error searching identifiers: {str(e)}"}


# --- Main Entry Point ---
def main():
    # Run the MCP server
    log.debug("Starting FastMCP server...")
    mcp.run()


if __name__ == "__main__":
    main()
