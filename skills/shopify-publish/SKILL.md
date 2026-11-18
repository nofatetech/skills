---
name: shopify-publish
description: Publish a Markdown note (e.g. from an Obsidian vault) as a Shopify blog article, headless, and upload images/GIFs/videos to Shopify Files for embedding. Use when asked to publish, post, update, or unpublish a blog post/article on Shopify or "the website", or to put media on the store.
---

# Shopify blog publishing

`scripts/shopify.py` is a self-contained `uv` script (dependencies declared inline; `uv` installs them on first run). Run `scripts/shopify.py --help` for commands. Published state lives in the note's frontmatter, so re-publishing updates the same article.

## Setup (once)
A Shopify custom app (Dev Dashboard) with `read_content`/`write_content` access (plus `write_files` for uploads), installed on the store. Credentials come from env vars, or from the optional `~/.workbench/config.json` (`shopify_*` keys, shared with [ProjectOS Workbench](https://github.com/nofatetech/ProjectOSWorkbench)):

| Env var | Meaning |
|---|---|
| `SHOPIFY_STORE` | `name.myshopify.com` |
| `SHOPIFY_CLIENT_ID` + `SHOPIFY_CLIENT_SECRET` | app credentials (client-credentials grant; app and store in the same organization) |
| `SHOPIFY_ACCESS_TOKEN` | alternative: an Admin API token |
| `SHOPIFY_BLOG_ID` | default blog, `gid://shopify/Blog/…` (`check` lists them) |
| `SHOPIFY_AUTHOR` | author name for new articles |

Never print, cat, or echo the config file or these values; the script redacts secrets itself.

## Publish a note

1. **Note ready.** Frontmatter: `title`, `summary`, `tags`, `publish: draft`. The body may open with `# <title>`; the script drops that H1 because Shopify renders the title. If the vault has published posts already, match their frontmatter.
2. **Media hosted.** Every image/GIF/video is a Shopify CDN URL: `scripts/shopify.py upload FILE --alt "..."` prints the URL (the highest-quality MP4 for video). Embed images as `![alt](url)`; videos as raw HTML `<video src="url" controls playsinline preload="metadata"></video>`. The script refuses notes with local embeds.
3. **Dry run** — `scripts/shopify.py publish NOTE --dry-run`. Done when it prints `would create/update` with the right title, tags, and status.
4. **Push as draft** — `scripts/shopify.py publish NOTE --draft`. It writes `shopify_article_id`, `shopify_blog_id`, `shopify_store`, `publish`, `published_at`, `shopify_published_url` back into the note. Give the user the printed admin link to preview.
5. **Go live only on the user's explicit say-so** — `scripts/shopify.py publish NOTE --live`. Unpublish = `--draft` again.

Without `--draft`/`--live`, the note's `publish:` value decides (`publish`/`live`/`true` → live, anything else → draft).

## Facts
- `scripts/shopify.py check` verifies credentials, lists blogs, and marks the default.
- Live URLs print on the `myshopify.com` domain; Shopify redirects them to the store's primary domain.
- `[[wikilinks]]` become plain text: link to other posts with full URLs.
- A note with `audience: private`/`members`/`paid` is refused as live: Shopify articles are public.
- Pages, products, themes, and email campaigns are out of scope.
