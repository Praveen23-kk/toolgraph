"""The agent's own built-in tools (Claude Code), so hooks and skills that name them resolve."""

BUILTIN_SERVER = "builtin"


def _t(name: str, description: str, props: dict[str, str], required: list[str]) -> dict:
    return {"name": name, "description": description,
            "inputSchema": {"type": "object", "required": required,
                            "properties": {k: {"type": "string", "description": v} for k, v in props.items()}}}


BUILTIN_TOOLS = [
    _t("Bash", "Run a shell command and return its output", {"command": "The command to run"}, ["command"]),
    _t("Read", "Read a file from the local filesystem. Returns the file contents as text", {"file_path": "Absolute path"}, ["file_path"]),
    _t("Write", "Write a file to the local filesystem. Returns the file path", {"file_path": "Absolute path", "content": "File content"}, ["file_path", "content"]),
    _t("Edit", "Perform exact string replacement in a file. Returns the file path", {"file_path": "Absolute path", "old_string": "Text to replace", "new_string": "Replacement"}, ["file_path", "old_string", "new_string"]),
    _t("Glob", "Find files by glob pattern. Returns file paths", {"pattern": "Glob pattern", "path": "Directory"}, ["pattern"]),
    _t("Grep", "Search file contents with a regular expression. Returns file paths", {"pattern": "Regex", "path": "Directory"}, ["pattern"]),
    _t("WebFetch", "Fetch a URL and return its content as markdown text", {"url": "URL to fetch", "prompt": "What to extract"}, ["url"]),
    _t("WebSearch", "Search the web. Returns result URLs", {"query": "Search query"}, ["query"]),
    _t("Task", "Launch a subagent to handle a multi-step task", {"prompt": "Task description"}, ["prompt"]),
]
