# NoFate skills

Agent skills from [NoFate Technology](https://nofate.net): Markdown files that teach an AI coding agent (Claude Code, Codex, and others that read `SKILL.md`) how to do a job, plus small scripts that do the work.

| Skill | What it does |
|---|---|
| [`obsidian`](skills/obsidian/SKILL.md) | Work safely in an Obsidian vault: syntax cheat sheet, backlinks, broken links, and renaming notes without breaking links. Stdlib Python, no dependencies. |
| [`shopify-publish`](skills/shopify-publish/SKILL.md) | Publish a Markdown note as a Shopify blog article, headless: dry run, draft, then live. Uploads images, GIFs and videos to Shopify Files. Needs [`uv`](https://docs.astral.sh/uv/) and a Shopify custom app. |

## Install

```bash
npx skills add nofatetech/skills
```

Or copy a folder from `skills/` into `~/.claude/skills/` (all projects) or `<repo>/.claude/skills/` (one project).

## Story

These came out of building [Vids1](https://github.com/nofatetech/LeoLucasGame1/tree/main/Vids1/vids-1), a Godot tool that turns Markdown scripts into animated videos. The write-up: [I made skills and a video creator with Godot and Markdown files](https://nofate.net/blogs/nofate-blog-newsletter/i-made-skills-and-a-video-creator-with-godot-and-markdown-files).

## License

MIT
