# v1.3.0 S5 — multi-line subprocess.run with shell=True on its own line.
# Pre-v1.3.0 the regex `[,(]\s*shell\s*=\s*True\b` required `,` or `(`
# on the same line and missed this layout entirely.
import subprocess


def run(cmd):
    return subprocess.run(
        cmd,
        shell=True,
        capture_output=True,
    )
