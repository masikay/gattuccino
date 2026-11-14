# Catppuccin for fzf

The files in `themes/` are the `.rc` themes of the official port,
<https://github.com/catppuccin/fzf>, unchanged, at commit
`7508f8141286fb95249100a2b5325960320dcf32` (2026-06-28): one for each flavor,
`catppuccin-fzf-FLAVOR.rc`, in the format of fzf's options file
(`FZF_DEFAULT_OPTS_FILE`). They are under the MIT license in `LICENSE`,
Copyright (c) 2021 Catppuccin.

The port has no accent. gattuccino copies the one of the flavor in use and
puts the accent in two places, the `prompt` and the `pointer` (the port has
mauve and rosewater there), and says so in the first lines of the file it writes.
