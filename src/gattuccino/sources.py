"""Gets the GNOME Shell stylesheets the theme is built from.

The theme has to be generated from the stylesheets of the GNOME Shell release
it will run on, so they are downloaded for that exact version, once, and kept
in the cache folder.
"""

import os
import re
import shutil
import subprocess
import tempfile

# The official repository first, then its read-only mirror
REPOSITORIES = (
    "https://gitlab.gnome.org/GNOME/gnome-shell.git",
    "https://github.com/GNOME/gnome-shell.git",
)

# First release whose stylesheets this project knows how to edit
MINIMUM_VERSION = 48


class SourcesError(Exception):
    pass


def installed_version():
    """Version of the installed GNOME Shell, e.g. "49.10", or None."""
    try:
        output = subprocess.run(["gnome-shell", "--version"], capture_output=True, text=True).stdout
    except OSError:
        return None
    match = re.search(r"(\d+(?:\.[0-9a-z]+)*)", output)
    return match.group(1) if match else None


def major(version: str) -> int:
    return int(version.split(".")[0])


def check_version(version: str):
    if not re.fullmatch(r"\d+(\.[0-9a-z]+)*", version):
        raise SourcesError(f"'{version}' is not a GNOME Shell version (expected something like 49.2).")
    if major(version) < MINIMUM_VERSION:
        raise SourcesError(f"GNOME Shell {version} is not supported: version {MINIMUM_VERSION} or later is needed.")


def _git(*args):
    # Never stop to ask for credentials: the repositories are public
    environment = dict(os.environ, GIT_TERMINAL_PROMPT="0")
    return subprocess.run(["git", *args], capture_output=True, text=True, env=environment)


def _download(url: str, version: str, destination: str) -> str:
    """Fetch data/theme of the release tagged `version`; returns git's error output on failure."""
    # Only the theme folder is needed: try a sparse checkout first, which
    # downloads a few hundred kilobytes instead of the whole tree.
    clone = _git("clone", "--quiet", "--depth", "1", "--branch", version,
                 "--filter=blob:none", "--sparse", url, destination)
    if clone.returncode == 0:
        sparse = _git("-C", destination, "sparse-checkout", "set", "data/theme")
        if sparse.returncode == 0 and os.path.isdir(f"{destination}/data/theme/gnome-shell-sass"):
            return ""
    shutil.rmtree(destination, ignore_errors=True)

    clone = _git("clone", "--quiet", "--depth", "1", "--branch", version, url, destination)
    if clone.returncode == 0 and os.path.isdir(f"{destination}/data/theme/gnome-shell-sass"):
        return ""
    shutil.rmtree(destination, ignore_errors=True)
    return clone.stderr.strip() or "the release has no data/theme/gnome-shell-sass folder"


def theme_sources(version: str, cache_dir: str, log=print) -> str:
    """Path of GNOME Shell's data/theme folder for `version`, downloading it if needed."""
    check_version(version)
    theme_dir = f"{cache_dir}/gnome-shell-{version}/theme"
    if os.path.isdir(f"{theme_dir}/gnome-shell-sass"):
        return theme_dir

    if not shutil.which("git"):
        raise SourcesError("git is needed to download the GNOME Shell stylesheets.")

    log(f"Downloading the GNOME Shell {version} stylesheets...")
    errors = []
    for url in REPOSITORIES:
        with tempfile.TemporaryDirectory(prefix="gattuccino-") as temporary:
            error = _download(url, version, f"{temporary}/gnome-shell")
            if error:
                errors.append(f"  {url}\n    {error.splitlines()[-1]}")
                continue
            os.makedirs(os.path.dirname(theme_dir), exist_ok=True)
            shutil.rmtree(theme_dir, ignore_errors=True)
            shutil.copytree(f"{temporary}/gnome-shell/data/theme", theme_dir)
            return theme_dir

    raise SourcesError(
        f"Could not download the GNOME Shell {version} stylesheets:\n" + "\n".join(errors) +
        "\nIf your distribution's version has no release of that exact name, "
        "set the closest one with: gattuccino configure --shell-version VERSION")
