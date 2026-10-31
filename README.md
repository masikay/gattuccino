# Gattuccino

The [Catppuccin](https://catppuccin.com) palette for the GNOME desktop: a GNOME Shell theme, matching colors for applications, and two small extensions, all set up by one script.

- **GNOME Shell theme** in Latte for the light style, and in the dark flavor of your choice for the dark style: Frappé, Macchiato or Mocha.
- **Application colors** for GTK 4 / libadwaita and GTK 3, optionally for Flatpak applications too.
- **The style and the accent follow Settings.** Pick *Default* or *Dark* in *Settings > Appearance* and the Shell and applications switch between Latte and your dark flavor; pick an accent there and they use its Catppuccin counterpart.
- **Optional effects:** translucent top bar and popups, a floating, rounded top bar that docks when a window comes close, and the accent color on whatever is selected or under the pointer.

This is an unofficial project, named *Gattuccino*: `gatto`, Italian for cat, and `cappuccino` — the same construction as "Catppuccin" itself (cat + cappuccino), carried over into Italian. It is not affiliated with Catppuccin or GNOME.

Until October 2026 this project was itself called `gnome-catppuccin`. An install made under that name is migrated automatically: `apply` moves the preferences and state over, and replaces the old theme folders, application color files and extensions with their new-named equivalents.

## Requirements

- GNOME Shell 48 or later
- Python 3.9 or later, and `git`
- A Sass compiler: `sassc` (packaged by every distribution), or the Python module (`pip install libsass`)
- The [User Themes](https://extensions.gnome.org/extension/19/user-themes/) extension, to load the Shell theme (package `gnome-shell-extension-user-theme` or `gnome-shell-extensions`, depending on the distribution)
- An internet connection the first time, and after each GNOME upgrade, to download the GNOME Shell stylesheets the theme is built from

Optional: the [adw-gtk3](https://github.com/lassekongo83/adw-gtk3) theme, for GTK 3 applications to follow.

## Quick start

```sh
git clone <this repository>
cd gattuccino
./gattuccino configure
```

`configure` asks for each preference in turn, then offers to apply them. Afterwards, log out and back in so that GNOME Shell loads the extensions.

With the defaults you get Latte for the light style and Mocha for the dark style, with the accent picked in Settings, in the Shell and in applications.

## Commands

| Command | What it does |
|---|---|
| `./gattuccino configure` | Ask for every preference, save them, and offer to apply |
| `./gattuccino configure --flavor frappe --apply` | Change just the preferences given, and apply |
| `./gattuccino apply` | Build and install what the preferences say; remove what they no longer ask for |
| `./gattuccino show` | Print the preferences |
| `./gattuccino build --output FOLDER` | Build into a folder and change nothing else |
| `./gattuccino uninstall` | Remove everything and put back the settings that were changed |

## Preferences

Every preference is an option of `configure`, and a line in `~/.config/gattuccino/preferences.ini`.

| Preference | Values | Default | |
|---|---|---|---|
| `--flavor` | `frappe`, `macchiato`, `mocha` | `mocha` | Flavor of the dark style. Latte is always installed too, for the light style |
| `--accent` | `follow`, or one of the 14 accents | `follow` | `follow` uses the accent picked in Settings > Appearance |
| `--shell-theme` / `--no-shell-theme` | | on | Install the GNOME Shell theme in `~/.themes` |
| `--gtk-theme` / `--no-gtk-theme` | | on | Install the application colors in `~/.config/gtk-4.0` and `~/.config/gtk-3.0` |
| `--flatpak` / `--no-flatpak` | | off | Let Flatpak applications read the application colors |
| `--accent-selection` / `--no-accent-selection` | | off | Use the accent color for what is selected or under the pointer, in the Shell and in applications |
| `--panel-opacity` | `0` to `1` | `1` | Opacity of the top bar |
| `--popup-opacity` | `0` to `1` | `1` | Opacity of popup menus, quick settings and the calendar |
| `--floating-panel` / `--no-floating-panel` | | off | Float the top bar as a rounded bar, docked while a window is near |
| `--panel-gap` | `0` to `12` | `6` | Gap around the floating bar, in pixels |
| `--panel-radius` | `round`, or `0` to `100` | `round` | Corner radius of the floating bar, in pixels |
| `--docked-panel-opacity` | `same`, or `0` to `1` | `same` | Opacity of the floating bar while docked |
| `--dock-like-panel` / `--no-dock-like-panel` | | off | Give the dock of Dash to Dock or Ubuntu Dock the color and opacity of the top bar |
| `--shell-version` | `auto`, or a version | `auto` | GNOME Shell version to build the theme for |

The accents are `rosewater`, `flamingo`, `pink`, `mauve`, `red`, `maroon`, `peach`, `yellow`, `green`, `teal`, `sky`, `sapphire`, `blue` and `lavender`.

Some examples:

```sh
# Frappé for the dark style (Latte stays the light one), everything else unchanged
./gattuccino configure --flavor frappe --apply

# Translucent popups, and a translucent floating bar that turns solid when it docks
./gattuccino configure --popup-opacity 0.8 --floating-panel \
    --panel-opacity 0.7 --docked-panel-opacity 1 --apply

# Always mauve, whatever is picked in Settings
./gattuccino configure --accent mauve --apply

# Only the application colors, also for Flatpak applications
./gattuccino configure --no-shell-theme --flatpak --apply

# The accent color on selected sidebar rows and highlighted menu items
./gattuccino configure --accent-selection --apply
```

## What is installed where

| What | Where | When |
|---|---|---|
| Shell themes, named `gattuccino-FLAVOR-ACCENT`, for Latte and the dark flavor | `~/.themes` | `shell-theme` is on |
| `gtk.css`, `gattuccino-latte.css`, `gattuccino-FLAVOR.css` and `gattuccino-accent.css` | `~/.config/gtk-4.0`, `~/.config/gtk-3.0` | `gtk-theme` is on |
| `gattuccino-selection.css` | `~/.config/gtk-4.0`, `~/.config/gtk-3.0` | `gtk-theme` and `accent-selection` are on |
| `gattuccino-dock.css`, in each shell theme | `~/.themes` | `shell-theme` and `accent-selection` are on |
| Extension `catppuccin-accent@gattuccino` | `~/.local/share/gnome-shell/extensions` | `shell-theme` or `gtk-theme` is on |
| Extension `floating-panel@gattuccino` | `~/.local/share/gnome-shell/extensions` | `shell-theme` and `floating-panel` are on |
| Preferences, and a record of what was changed | `~/.config/gattuccino` | always |
| The downloaded GNOME Shell stylesheets | `~/.cache/gattuccino` | `shell-theme` is on |

`apply` also changes a few settings, and remembers what they were:

- with `shell-theme` on, the theme selected in User Themes;
- with `gtk-theme` on, the GTK 3 theme, set to `adw-gtk3` or `adw-gtk3-dark` (for the current style) if it is installed;
- with `flatpak` on, the folders Flatpak applications may read.

A `gtk.css` of your own is kept as `gtk.css.before-gattuccino`. `uninstall` puts all of this back, and so does turning the preference off again.

`apply` never overwrites or removes a theme folder that it did not create.

## The accent color

GNOME Settings offers nine accent colors, and GNOME Shell and libadwaita turn each into a fixed color of their own. With `accent` set to `follow`, each stands for a Catppuccin accent instead:

| Picked in Settings | blue | teal | green | yellow | orange | red | pink | purple | slate |
|---|---|---|---|---|---|---|---|---|---|
| Catppuccin accent | blue | teal | green | yellow | peach | red | pink | mauve | lavender |

A Shell theme cannot change its accent by itself, so nine themes are installed for each of the two flavors, one per accent, and the `catppuccin-accent` extension switches between them when you pick another accent. It also rewrites `gattuccino-accent.css` for applications, and the swatches in Settings show the Catppuccin colors.

- The Shell changes at once. Applications show the new accent the next time they are started.
- The extension only switches between themes whose names differ by the flavor and accent at the end, and only rewrites the files this project wrote. Any other theme you select in User Themes is left alone.
- Red and peach are also the palette's error and warning colors: with one of them as accent, the two look the same.

To use an accent that is not in the picker, such as `sky` or `rosewater`, set it with `--accent`. Only that accent is then installed, for both flavors, and the picker in Settings has no effect on it.

## Selected and hovered things

Everywhere something is selected or sits under the pointer, GNOME draws it as a shade of the text color: a selected sidebar row, an item in a menu, a day in the calendar, an icon in the overview, a button in the top bar. `accent-selection` makes all of that a shade of the accent instead, in the Shell and in applications alike:

```sh
./gattuccino configure --accent-selection --apply
```

Two strengths, so that a hover does not read as a second selection:

| Drawn with | Where |
|---|---|
| The accent itself, with the flavor's `base` color on top | A selected sidebar row, the selected window in the window switcher |
| A tint of the accent: a fifth of it, or a third while pressed | The item under the pointer or picked out by the keyboard in a menu, and a hovered row, overview icon, search result, calendar day, dock icon, quick settings button or top bar button |

Only the two states that mean "this one" take the accent itself, because only there is the text ours to color with it. Everything else is tinted and keeps the text color it had. Menus in particular: their text belongs to the application, and some applications (Chromium and the browsers built on it, among them Brave) draw their own on top of whatever is behind it, which the accent itself left without contrast.

In the dock of Dash to Dock the tint marks the application in focus as well as the icon under the pointer, and the windows and notification counters take the accent itself. See [Dash to Dock](#dash-to-dock) below.

In applications this is a small stylesheet of its own, `gattuccino-selection.css`, in `~/.config/gtk-4.0` and `gtk-3.0`. This is the one place where the application colors are rules and not just colors. It names the accent through the variables of `gattuccino-accent.css` instead of spelling it out, so it keeps up with the accent on its own. The flavor files import it, not `gtk.css`: the `catppuccin-accent` extension therefore never touches it, and turning the preference on needs no logging out, only restarting the applications.

The same stylesheet also names the color of selected text without any transparency in it. GNOME tints selected text with a fraction of the accent over whatever is behind, and GTK composites that when it paints. Chromium, and the browsers built on it, do not let GTK paint: they ask it for the color and drop the transparency, which left the full accent behind their own text, and in Brave made the selected URL in the address bar unreadable. The composited color is named here instead, so there is no transparency to drop. The text color is named with it, because GNOME draws selected glyphs transparent and lets the text painted underneath show through the tint: an opaque background on its own would cover the text rather than tint it. Since this rides in the same file, it needs `accent-selection` on, although the problem it fixes has nothing to do with the preference.

In the Shell it is part of the theme, built from four more edits to GNOME's own stylesheet. Almost everything that highlights goes through one of its Sass mixins, so those edits reach the whole desktop, menus included; the window switcher colors its own selection and is changed separately. GNOME's own `st-mix` does the mixing when the Shell loads the theme, so a tint still composites over whatever is behind the widget, a translucent top bar included.

Left deliberately alone: the parts that are not about selection at all, such as scrollbars and the red window-close button.

One limit: in GTK 3 applications the *selected* row keeps its own color. GTK 3 has no way for a stylesheet to match a selected row, so only the hover and the menu items follow there.

## Light and dark

Latte and the dark flavor of the `flavor` preference are always installed together, and the style picked in *Settings > Appearance* chooses between them: *Default* gives Latte, *Dark* gives the dark flavor. The `catppuccin-accent` extension makes the switch, so it happens as soon as you change the style:

- the Shell changes at once;
- `gtk.css` is pointed at the colors of the other flavor, and the GTK 3 theme switches between `adw-gtk3` and `adw-gtk3-dark`. As with the accent, applications show the new colors the next time they are started.

`apply` no longer sets the style itself: it builds and selects the flavor for the style you have picked.

Latte is built from GNOME Shell's light stylesheet, the dark flavors from its dark one. As in GNOME itself, the overview and on-screen displays stay dark in Latte; they use Latte's text color as their background.

## The floating bar

With `floating-panel` on, the top bar floats as a rounded bar, and goes back to a normal full-width bar while a window on the current workspace is maximized, tiled, or close to it. `docked-panel-opacity` gives it another opacity in that state, for instance `1` for a solid bar under maximized windows.

A theme cannot know where windows are: the `floating-panel` extension tells it. To stop the bar from floating for a while without changing anything else:

```sh
gnome-extensions disable floating-panel@gattuccino
```

## Dash to Dock

[Dash to Dock](https://micheleg.github.io/dash-to-dock/), and Ubuntu Dock, which is the same extension, draw the dock with the Shell theme's style for the dash of the overview. So the dock already has the Catppuccin colors, as long as *Use built-in theme* is off in the extension's settings (Appearance).

By default the dock therefore looks like the overview's dash. With `dock-like-panel` on, it takes the color and opacity of the top bar instead (`panel-opacity`), with icons and running dots to match. The dash of the overview itself is not changed.

With `accent-selection` on, the dock also follows the accent: the icon of the application in focus and the icon under the pointer take a light, translucent accent, and the windows counter indicators and the notification counter the accent itself. As in Dash to Dock's own look, focused and hovered icons are drawn the same way, so it is the counter indicator below the icon that marks the focused one. The dash of the overview is again left as it is.

For the theme to decide, leave these as they are by default in the extension's settings: *Use built-in theme* off, *Customize the dash color* off, *Customize opacity* on *Default*, and *Customize windows counter indicators* off. Any of them replaces the theme's color, opacity or indicator color with the extension's own.

The stylesheet of an extension outranks any Shell theme, whatever the theme says, and Dash to Dock states the highlight of a focused and of a hovered icon, the color of the notification counter, and the separator in its own. So the accent for the dock cannot be part of the theme: it is a stylesheet of its own, `gattuccino-dock.css`, built next to each theme's stylesheet and loaded by the `catppuccin-accent` extension, which is an extension stylesheet in turn. There `!important` is what gets ahead of Dash to Dock, and it is the one place in this project that uses it. The separator stays a white overlay, faint on the light bar of Latte.

## Blur

GNOME Shell themes cannot blur what is behind them. For a blurred bar and popups, add the [Blur my Shell](https://github.com/aunetx/blur-my-shell) extension and turn off its *Override background* options, so that the colors of the theme are kept.

## Flatpak applications

Flatpak applications cannot read `~/.config/gtk-4.0` and `~/.config/gtk-3.0` unless they are allowed to. The `flatpak` preference allows it, read-only, for all applications of your user (`flatpak override --user`), and takes it back when it is turned off.

GTK 3 Flatpak applications also need the theme itself:

```sh
flatpak install org.gtk.Gtk3theme.adw-gtk3 org.gtk.Gtk3theme.adw-gtk3-dark
```

## After a GNOME upgrade

The Shell theme is generated from the stylesheets of one GNOME Shell release. After upgrading GNOME, run `./gattuccino apply` again to rebuild it for the new one.

If your distribution's version has no upstream release of the same name, set the closest one, for example `./gattuccino configure --shell-version 49.2`.

## Limits

- The login screen is not themed. The lock screen keeps GNOME's look too, as GNOME Shell disables extensions there.
- Buttons and cards inside translucent popups stay solid, so that they remain readable. Notification banners, on-screen displays, the window switcher and dialogs are not translucent.
- GTK 3 applications only follow with the adw-gtk3 theme. Qt, Electron and Firefox do not use these colors at all.
- With `accent-selection` on, GTK 3 applications get the accent on menu items and on hovered sidebar rows, but not on the selected row: GTK 3 stylesheets cannot match one.
- Applications that set colors of their own keep them.
- The floating bar changes shape in one step: GNOME Shell cross-fades colors, not positions.

## How it works

Nothing here is a stylesheet written from scratch. The Shell theme is GNOME Shell's own stylesheet, downloaded for your version and recompiled with the Catppuccin palette in place of Adwaita's, plus a few targeted edits for the accent and the optional effects. Each edit checks that the line it changes is there, so an unsupported GNOME Shell release fails with a message instead of producing a half-themed desktop.

The application colors are not a GTK theme either: they set the color variables that libadwaita exposes for recoloring, and the named colors adw-gtk3 shares with it.

```
gattuccino                  the command
src/gattuccino/              the package it imports (in src/: it shares its name with the command)
  palette.py                the four flavors, and how GNOME's accents map to Catppuccin's
  preferences.py            the preferences and their checks
  sources.py                downloads the GNOME Shell stylesheets
  shell_theme.py            builds the Shell theme
  gtk_theme.py              generates the application colors
  desktop.py                paths, gsettings, extensions, Flatpak
  install.py                apply and uninstall
extensions/                 the two extensions
tests/                      tests
```

## Tests

```sh
python3 -m unittest discover -s tests -t .
```

The tests run the real command in a throwaway home folder, with stand-ins for `gsettings`, `gnome-extensions`, `flatpak` and `gnome-shell`, so they change nothing on the machine. The extensions are tested with [Node.js](https://nodejs.org) against stand-ins for GNOME Shell's objects; those tests are skipped if it is not installed. The first run downloads the GNOME Shell stylesheets into `tests/.cache`.

## Credits and license

- Based on [gnome-catppuccin](https://github.com/elisesouche/gnome-catppuccin) by Élise Souche, which had the idea of recompiling GNOME Shell's stylesheet with the Catppuccin palette.
- The palette is [Catppuccin](https://github.com/catppuccin/palette)'s.
- The generated Shell theme is derived from [GNOME Shell](https://gitlab.gnome.org/GNOME/gnome-shell)'s stylesheets, which are licensed under the GPL, version 2 or later. They are downloaded when the theme is built and are not part of this repository.

This project is under the MIT license: see [LICENSE](LICENSE).
