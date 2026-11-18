---
name: obsidian
description: Work safely in any Obsidian vault (a folder with .obsidian/) — Obsidian Markdown syntax (wikilinks, embeds, callouts, properties, tags, Dataview), finding backlinks and broken links, and renaming/moving notes without breaking links. Use when creating, editing, linking, renaming or moving notes in an Obsidian vault.
---

# Obsidian vaults

## First: the vault's own rules win
Before writing, read the vault's `CLAUDE.md`/`AGENTS.md`/`README.md`. Conventions differ per vault: some use `[[wikilinks]]` and frontmatter-driven Dataview dashboards, others use relative Markdown links (`[text](../decisions/x.md)`) and templates. No rules file? Match whatever link style most existing notes use.

## Don't
- Edit `.obsidian/` (workspace.json, plugin data) unless asked — it's app state.
- Move/rename notes with plain `mv`: Obsidian's "update links on rename" only runs inside the app. Use the script below.
- Hand-maintain index/list notes that a Dataview query could produce.
- Break YAML frontmatter: it must be the very first thing in the file, between `---` lines.

## Syntax cheat sheet
| Thing | Syntax |
|---|---|
| Link / alias | `[[Note]]`, `[[Note\|shown text]]`, `[[folder/Note]]` when the name is ambiguous |
| Heading / block link | `[[Note#Heading]]`, `[[Note#^block-id]]` (mark a block with ` ^block-id` at line end) |
| Embed | `![[Note]]`, `![[Note#Heading]]`, `![[image.png\|300]]` |
| Tag | `#tag`, `#area/sub` (nested); or `tags: [a, b]` in frontmatter |
| Callout | `> [!note] Title` then `> body`; types: note, tip, warning, todo, question, quote; `[!note]-` = folded |
| Task | `- [ ] todo`, `- [x] done` |
| Comment (hidden) | `%% not rendered %%` |
| Highlight | `==text==` |

Properties (frontmatter): lists as `key: [a, b]` or YAML list; links inside properties must be quoted: `related: "[[Note]]"`. Dates `YYYY-MM-DD`.

Dataview basics (when the vault has the plugin):
````
```dataview
TABLE status, area FROM "10_Projects" WHERE type = "project" AND status = "active" SORT file.mtime DESC
```
````
Inline: `` `= this.status` ``. Fields come from frontmatter or `key:: value` lines.

## Helper script
`scripts/obsidian_tools.py` in this skill's folder (stdlib only; note paths are relative to the vault root):
```bash
S=<this skill's folder>/scripts/obsidian_tools.py
python3 $S ~/MyVault backlinks "Projects/Plan.md"                      # who links here
python3 $S ~/MyVault broken                                             # links to nothing
python3 $S ~/MyVault rename "Inbox/Old.md" "Resources/New.md"           # dry run
python3 $S ~/MyVault rename "Inbox/Old.md" "Resources/New.md" --apply   # do it (git mv if tracked)
```
Always show the dry run before `--apply`. Rename rewrites wikilinks (keeping heading/alias/embed parts) and relative Markdown links, including links inside the moved note. If the vault keeps status in frontmatter, change the property instead of moving the note.
