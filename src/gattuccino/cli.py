"""Command line: configure, apply, show, build, uninstall."""

import argparse
import os
import sys

from . import install, preferences as prefs, shell_theme, sources
from .desktop import Desktop

ERRORS = (prefs.PreferenceError, install.InstallError, shell_theme.BuildError, sources.SourcesError)

DESCRIPTION = """\
Catppuccin for GNOME: a GNOME Shell theme, matching colors for applications,
and two small extensions (floating top bar, accent color following Settings).

  gattuccino configure    choose your preferences (asks questions)
  gattuccino apply        build and install what the preferences say
  gattuccino show         print the preferences
  gattuccino uninstall    remove everything again
"""


def _option(name: str) -> str:
    return "--" + name.replace("_", "-")


def _add_preference_options(parser):
    for name, spec in prefs.SPECS.items():
        if spec.parse is prefs._boolean:
            parser.add_argument(_option(name), dest=name, default=None,
                                action=argparse.BooleanOptionalAction, help=spec.help)
        else:
            parser.add_argument(_option(name), dest=name, default=None, metavar="VALUE",
                                help=f"{spec.help} ({spec.values})")


def _show(preferences, desktop, out=print):
    width = max(len(name) for name in prefs.SPECS)
    for name, spec in prefs.SPECS.items():
        out(f"  {name.replace('_', '-'):<{width}}  {preferences.text(name):<10}  {spec.help}")
    out(f"\nStored in {desktop.preferences_path}")


def _ask(preferences):
    """Ask for every preference in turn; Enter keeps the current value."""
    print("Press Enter to keep the value in [brackets].\n")
    for name, spec in prefs.SPECS.items():
        if name in prefs.FLOATING_ONLY and not preferences.floating_panel:
            continue
        while True:
            try:
                answer = input(f"{spec.help}\n  {spec.values} [{preferences.text(name)}]: ").strip()
            except EOFError:
                print()
                raise prefs.PreferenceError("no answer: preferences not changed") from None
            if not answer:
                break
            try:
                preferences.set(name, answer)
                break
            except prefs.PreferenceError as e:
                print(f"  {e}")
        print()


def _yes(question: str) -> bool:
    try:
        return input(f"{question} [Y/n]: ").strip().lower() in ("", "y", "yes")
    except EOFError:
        return False


def _configure(args, desktop):
    preferences = prefs.load(desktop.preferences_path)
    given = {name: getattr(args, name) for name in prefs.SPECS if getattr(args, name) is not None}

    if given:
        for name, value in given.items():
            preferences.set(name, ("yes" if value else "no") if isinstance(value, bool) else value)
        apply_now = args.apply
    elif sys.stdin.isatty():
        _ask(preferences)
        apply_now = args.apply or None  # ask below
    else:
        raise prefs.PreferenceError("nothing to change: give options (see `configure --help`), "
                                    "or run it in a terminal to be asked")

    prefs.save(preferences, desktop.preferences_path)
    _show(preferences, desktop)
    if apply_now is None:
        print()
        apply_now = _yes("Apply now?")
    if apply_now:
        print()
        install.apply(preferences, desktop)
    else:
        print("\nRun `gattuccino apply` to put them in effect.")


def _build(args, desktop):
    """Build into a folder without installing anything."""
    preferences = prefs.load(desktop.preferences_path)
    output = os.path.abspath(args.output)
    if preferences.shell_theme:
        shell_theme.require_compiler()
        version, themes = install.build_shell_themes(preferences, desktop.cache_dir)
        for name, (flavor, accent, css) in themes.items():
            shell_theme.write_theme(f"{output}/themes/{name}", css, flavor, accent, version)
    if preferences.gtk_theme:
        for folder, contents in install.gtk_files(preferences, desktop).items():
            os.makedirs(f"{output}/{folder}", exist_ok=True)
            for name, text in contents.items():
                with open(f"{output}/{folder}/{name}", "w", encoding="utf-8") as f:
                    f.write(text)
    print(f"Built in {output}")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(prog="gattuccino", description=DESCRIPTION,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    commands = parser.add_subparsers(dest="command", metavar="COMMAND")

    configure = commands.add_parser(
        "configure", help="choose your preferences",
        description="Without options, asks for each preference in turn. "
                    "With options, changes just those and keeps the rest.")
    _add_preference_options(configure)
    configure.add_argument("--apply", action="store_true", help="apply the preferences right away")

    commands.add_parser("apply", help="build and install what the preferences say",
                        description="Builds the shell theme for your GNOME Shell version and installs "
                                    "everything the preferences ask for; removes what they no longer ask for.")
    commands.add_parser("show", help="print the preferences")
    build = commands.add_parser("build", help="build into a folder without installing",
                                description="Builds the shell themes and application colors of the "
                                            "current preferences into a folder, and changes nothing else.")
    build.add_argument("--output", default="_build", metavar="FOLDER", help="where to build (default: ./_build)")
    commands.add_parser("uninstall", help="remove everything again",
                        description="Removes the themes, colors and extensions this installed and puts "
                                    "back the settings it changed. Your preferences file is kept.")

    args = parser.parse_args(argv)
    desktop = Desktop()
    try:
        if args.command == "configure":
            _configure(args, desktop)
        elif args.command == "apply":
            install.apply(prefs.load(desktop.preferences_path), desktop)
        elif args.command == "show":
            _show(prefs.load(desktop.preferences_path), desktop)
        elif args.command == "build":
            _build(args, desktop)
        elif args.command == "uninstall":
            install.uninstall(desktop)
        else:
            parser.print_help()
    except ERRORS as e:
        print(f"gattuccino: {e}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        print()
        return 130
    return 0
