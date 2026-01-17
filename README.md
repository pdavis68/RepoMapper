# RepoMap - Command-Line Tool and MCP Server

RepoMap is a powerful tool designed to help, primarily LLMs, understand and navigate complex codebases. It functions both as a command-line application for on-demand analysis and as an MCP (Model Context Protocol) server, providing continuous repository mapping capabilities to other applications. By generating a "map" of the software repository, RepoMap highlights important files, code definitions, and their relationships. It leverages Tree-sitter for accurate code parsing and the PageRank algorithm to rank code elements by importance, ensuring that the most relevant information is always prioritized.

<a href="https://glama.ai/mcp/servers/@pdavis68/RepoMapper">
  <img width="380" height="200" src="https://glama.ai/mcp/servers/@pdavis68/RepoMapper/badge" alt="RepoMap MCP server" />
</a>

## Table of Contents
- [Aider](#aider)
- [Example Output](#example-output)
- [Features](#features)
- [Installation](#installation)
- [Usage](#usage)
  - [Basic Usage](#basic-usage)
  - [Advanced Options](#advanced-options)
- [How It Works](#how-it-works)
- [Output Format](#output-format)
- [Dependencies](#dependencies)
- [Caching](#caching)
- [Supported Languages](#supported-languages)
- [License](#license)
- [Running as an MCP Server](#running-as-an-mcp-server)
  - [Setup](#setup)
  - [Usage](#usage-1)
- [Changelog](#changelog)
----------

## Aider

RepoMap is 100% based on Aider's Repo map functionality, but I don't believe it shares any code with it. Allow me to explain.

My original effort was to take the RepoMap class from Aider, remove all the aider-specific dependencies, and then make it into a command-line tool. Python isn't my native language and I really struggled to get it to work.

So a few hours ago, I had a different idea. I took the RepoMap and some of its related code from aider and I fed it to an LLM (Either Claude or Gemini 2.5 Pro, can't remember) and had it create specifications for this, basically, from aider's implementation. So it generated a very detailed specification for this application (minus the MCP bits) and then I fed that to, well, Aider with Claude 3.7, and it built the command-line version of this.

I then used a combination of Aider w/Claude 3.7, Cline w/Gemini 2.5 Pro Preview & Gemini 2.5 Flash Preview, and Phind.com, and Gemini.com and Claude.com and ChatGPT.com and after a few hours, I finally got the MCP server sorted out. Again, keeping in mind, Python isn't really my native tongue.

----------

## Example Output

```
> uv run repomapper . --chat-files repomap_class.py
Chat files: ['/mnt/programming/RepoMapper/repomap_class.py']
repomap_class.py:
(Rank value: 10.8111)

  36: CACHE_VERSION = 1
  39: TAGS_CACHE_DIR = os.path.join(os.getcwd(), f".repomap.tags.cache.v{CACHE_VERSION}")
  40: SQLITE_ERRORS = (sqlite3.OperationalError, sqlite3.DatabaseError)
  43: Tag = namedtuple("Tag", "rel_fname fname line name kind".split())
  46: class RepoMap:
  49:     def __init__(
  93:     def load_tags_cache(self):
 102:     def save_tags_cache(self):
 459:     def get_ranked_tags_map_uncached(
 483:         def try_tags(num_tags: int) -> Tuple[Optional[str], int]:
 512:     def get_repo_map(

utils.py:
(Rank value: 0.2297)

  18: Tag = namedtuple("Tag", "rel_fname fname line name kind".split())
  21: def count_tokens(text: str, model_name: str = "gpt-4") -> int:
  35: def read_text(filename: str, encoding: str = "utf-8", silent: bool = False) -> Optional[str]:

importance.py:
(Rank value: 0.1149)

   8: IMPORTANT_FILENAMES = {
  27: IMPORTANT_DIR_PATTERNS = {
  34: def is_important(rel_file_path: str) -> bool:
  56: def filter_important_files(file_paths: List[str]) -> List[str]:

    ...
    ...
    ...
```

----------

## Features

-   **Smart Code Analysis**: Uses Tree-sitter to parse source code and extract function/class definitions
-   **Relevance Ranking**: Employs PageRank algorithm to rank code elements by importance
-   **Token-Aware**: Respects token limits to fit within LLM context windows
-   **Caching**: Persistent caching for fast subsequent runs
-   **Multi-Language**: Supports Python, JavaScript, TypeScript, Java, C/C++, Go, Rust, and more
-   **Important File Detection**: Automatically identifies and prioritizes important files (README, requirements.txt, etc.)

----------

## Installation

```bash
# Install with uv (recommended)
uv sync

# Or install as editable package
uv pip install -e .
```

----------

## Usage

### Basic Usage

```bash
# Map current directory
uv run repomapper .

# Map specific directory with custom token limit
uv run repomapper src/ --map-tokens 2048

# Map specific files
uv run repomapper file1.py file2.py

# Specify chat files (higher priority) vs other files
uv run repomapper --chat-files main.py --other-files src/

# Specify mentioned files and identifiers
uv run repomapper --mentioned-files config.py --mentioned-idents "main_function"

# Enable verbose output
uv run repomapper . --verbose

# Force refresh of caches
uv run repomapper . --force-refresh

# Specify model for token counting
uv run repomapper . --model gpt-3.5-turbo

# Set maximum context window
uv run repomapper . --max-context-window 8192

# Exclude files with Page Rank 0
uv run repomapper . --exclude-unranked
```

The tool prioritizes files in the following order:

1.  `--chat-files`: These files are given the highest priority, as they're assumed to be the files you're currently working on.
2.  `--mentioned-files`: These files are given a high priority, as they're explicitly mentioned in the current context.
3.  `--other-files`: These files are given the lowest priority and are used to provide additional context.

### Advanced Options

```bash
# Enable verbose output
uv run repomapper . --verbose

# Force refresh of caches
uv run repomapper . --force-refresh

# Specify model for token counting
uv run repomapper . --model gpt-3.5-turbo

# Set maximum context window
uv run repomapper . --max-context-window 8192

# Exclude files with Page Rank 0
uv run repomapper . --exclude-unranked

# Mention specific files or identifiers for higher priority
uv run repomapper . --mentioned-files config.py --mentioned-idents "main_function"
```

----------

## How It Works

1.  **File Discovery**: Scans the repository for source files
2.  **Code Parsing**: Uses Tree-sitter to parse code and extract definitions/references
3.  **Graph Building**: Creates a graph where files are nodes and symbol references are edges
4.  **Ranking**: Applies PageRank algorithm to rank files and symbols by importance
5.  **Token Optimization**: Uses binary search to fit the most important content within token limits
6.  **Output Generation**: Formats the results as a readable code map

----------

## Output Format

The tool generates a structured view of your codebase showing:

-   File paths and important code sections
-   Function and class definitions
-   Key relationships between code elements
-   Prioritized based on actual usage and references

----------

## Dependencies

-   `tiktoken`: Token counting for various LLM models
-   `networkx`: Graph algorithms (PageRank)
-   `diskcache`: Persistent caching
-   `grep-ast`: Tree-sitter integration for code parsing
-   `tree-sitter`: Code parsing framework
-   `pygments`: Syntax highlighting and lexical analysis

----------

## Caching

The tool uses persistent caching to speed up subsequent runs:

-   Cache directory: `.repomap.tags.cache.v1/`
-   Automatically invalidated when files change
-   Can be cleared with `--force-refresh`

----------

## Supported Languages

Currently supports languages with Tree-sitter grammars:

-   arduino
-   chatito
-   commonlisp
-   cpp
-   csharp
-   c
-   dart
-   d
-   elisp
-   elixir
-   elm
-   gleam
-   go
-   javascript
-   java
-   lua
-   ocaml_interface
-   ocaml
-   pony
-   properties
-   python
-   racket
-   r
-   ruby
-   rust
-   solidity
-   swift
-   udev
-   c_sharp
-   hcl
-   kotlin
-   php
-   ql
-   scala

----------

## License

This implementation is based on the RepoMap design from the Aider project.

----------

## Running as an MCP Server

RepoMap can also be run as an MCP (Model Context Protocol) server, allowing other applications to access its repository mapping capabilities.

### Setup

1. The RepoMap MCP server uses STDIO (standard input/output) for communication. No additional configuration is required for the transport layer.
2. To set up RepoMap as an MCP server with Cline (or similar tools like Roo), add the following configuration to your Cline settings file (e.g., `cline_mcp_settings.json`):

```json
{
  "mcpServers": {
    "RepoMapper": {
      "disabled": false,
      "timeout": 60,
      "type": "stdio",
      "command": "uv",
      "args": [
        "run",
        "--directory",
        "/absolute/path/to/RepoMapper",
        "repomap-mcp"
      ]
    }
  }
}
```

- Replace `"/absolute/path/to/RepoMapper"` with the actual path to your RepoMapper installation directory.

### Usage

1. Run the MCP server:

```bash
uv run repomap-mcp
```

2. The server will start and listen for requests via STDIO.
3. Other applications can then use the `repo_map` tool provided by the server to generate repository maps. They must specify the `project_root` parameter as an absolute path to the project they want to map.


## Changelog

7/13/2025 - Removed the project.json dependency. Fixed the MCP server to be a little easier for the LLM to work with in terms of filenames.