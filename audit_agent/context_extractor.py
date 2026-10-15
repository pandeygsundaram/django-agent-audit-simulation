import os
import re
from pathlib import Path
from typing import Dict, Any, List

def parse_traceback_frames(tb_text: str) -> List[Dict[str, Any]]:
    """
    Parses a python traceback to extract file paths, line numbers, and function names.
    Pattern: File "path", line X, in func_name
    """
    pattern = re.compile(r'File "(?P<file>[^"]+)", line (?P<line>\d+), in (?P<func>\w+)')
    frames = []
    for match in pattern.finditer(tb_text):
        frames.append({
            "file": match.group("file"),
            "line": int(match.group("line")),
            "func": match.group("func")
        })
    return frames

def extract_code_snippet(file_path: str, target_line: int, window: int = 10) -> str:
    """
    Reads the file from disk and extracts lines around target_line with pointer markers.
    """
    if not os.path.exists(file_path):
        return f"[File not found on disk: {file_path}]"

    try:
        with open(file_path, "r", encoding="utf-8", errors="replace") as f:
            lines = f.readlines()

        start = max(1, target_line - window)
        end = min(len(lines), target_line + window)

        snippet_lines = []
        for i in range(start, end + 1):
            line_content = lines[i - 1].rstrip("\n")
            prefix = "--> " if i == target_line else "    "
            snippet_lines.append(f"{prefix}{i:4d} | {line_content}")

        return "\n".join(snippet_lines)
    except Exception as e:
        return f"[Error reading file {file_path}: {e}]"

def build_agent_context(event_data: Dict[str, Any], project_root: str = None) -> Dict[str, Any]:
    """
    Aggregates error info, request context, and source code excerpts around the crash.
    """
    tb_text = event_data.get("traceback", "")
    frames = parse_traceback_frames(tb_text)

    # Filter frames to focus on project code rather than site-packages/lib
    project_frames = []
    for f in frames:
        fpath = f["file"]
        is_site_packages = "site-packages" in fpath or "lib/python" in fpath or "/lib64/" in fpath
        if not is_site_packages:
            snippet = extract_code_snippet(fpath, f["line"], window=8)
            project_frames.append({
                "file": fpath,
                "line": f["line"],
                "function": f["func"],
                "code_snippet": snippet
            })

    # If no non-site-package frames found, take the very last frame
    if not project_frames and frames:
        last_frame = frames[-1]
        snippet = extract_code_snippet(last_frame["file"], last_frame["line"], window=8)
        project_frames.append({
            "file": last_frame["file"],
            "line": last_frame["line"],
            "function": last_frame["func"],
            "code_snippet": snippet
        })

    primary_frame = project_frames[-1] if project_frames else None

    return {
        "error_type": event_data.get("error_type", "UnknownError"),
        "error_message": event_data.get("error_message", ""),
        "source": event_data.get("source", "Backend"),
        "request": event_data.get("request", {}),
        "primary_frame": primary_frame,
        "all_project_frames": project_frames,
        "raw_traceback": tb_text.strip(),
    }
