"""ASCII art validation tool for CrewAI agents."""

from crewai.tools import tool


@tool("validate_art")
def validate_art(art_text: str, expected_width: int, expected_height: int) -> str:
    """Validate ASCII art dimensions and character palette.

    Args:
        art_text: The ASCII art as a multi-line string
        expected_width: Expected width in characters per line
        expected_height: Expected number of lines

    Returns:
        'PASS' or 'FAIL: [specific errors]'
    """
    errors: list[str] = []
    lines = art_text.split("\n")

    # Strip trailing empty line (common trailing newline)
    if lines and lines[-1] == "":
        lines = lines[:-1]

    # Height check (±1 tolerance)
    if abs(len(lines) - expected_height) > 1:
        errors.append(
            f"Height mismatch: got {len(lines)} lines, expected {expected_height} (±1)"
        )

    # Width check per line — pad if short, allow up to 2 chars over
    normalised: list[str] = []
    width_errors: list[str] = []
    for i, line in enumerate(lines):
        length = len(line)
        if length < expected_width:
            # Pad with spaces
            normalised.append(line.ljust(expected_width))
        elif length <= expected_width + 2:
            # Trim within tolerance
            normalised.append(line[:expected_width])
        else:
            width_errors.append(
                f"Line {i + 1}: width {length}, expected {expected_width} (max +2)"
            )
            normalised.append(line[:expected_width])

    if width_errors:
        errors.append("Width errors:\n  " + "\n  ".join(width_errors))

    # Character palette check: printable ASCII (32-126) + box-drawing (U+2500-U+257F, U+2580-U+259F)
    bad_chars: dict[str, list[int]] = {}
    for i, line in enumerate(normalised):
        for ch in line:
            cp = ord(ch)
            if (32 <= cp <= 126) or (0x2500 <= cp <= 0x257F) or (0x2580 <= cp <= 0x259F):
                continue
            key = repr(ch)
            bad_chars.setdefault(key, []).append(i + 1)

    if bad_chars:
        parts = [f"{ch} on line(s) {','.join(map(str, lns[:5]))}" for ch, lns in bad_chars.items()]
        errors.append("Invalid characters:\n  " + "\n  ".join(parts))

    if errors:
        return "FAIL: " + "\n".join(errors)
    return "PASS"
