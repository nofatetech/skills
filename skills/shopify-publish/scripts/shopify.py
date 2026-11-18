#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = ["httpx", "markdown", "python-frontmatter"]
# ///
"""Headless Shopify blog publisher for vault Markdown notes.

Standalone port of ProjectOSWorkbench's shopify_publish.py: same frontmatter
contract (shopify_article_id, shopify_blog_id, shopify_store, publish, ...), so
notes published here and from the Workbench stay interchangeable.

Credentials: env vars SHOPIFY_STORE, SHOPIFY_CLIENT_ID, SHOPIFY_CLIENT_SECRET,
SHOPIFY_ACCESS_TOKEN, SHOPIFY_BLOG_ID, SHOPIFY_AUTHOR override the Workbench
config at ~/.workbench/config.json. Secrets are never printed.

  shopify.py check                      # token + list blogs
  shopify.py publish NOTE [--dry-run] [--draft | --live]
  shopify.py upload FILE [--alt TEXT]   # image/GIF/video → Shopify Files CDN URL
"""

import argparse
import json
import mimetypes
import os
import re
import sys
import time
from datetime import date
from pathlib import Path

import frontmatter
import httpx
import markdown

API_VERSION = "2026-07"
CONFIG = Path.home() / ".workbench" / "config.json"
LIVE = {"publish", "published", "public", "live", "true", "yes", "1"}
RESTRICTED = {"private", "password", "subscribers", "subscriber-only", "members",
              "members-only", "paid", "paid-subscribers"}
FM_RE = re.compile(r"^---\n(.*?)\n---\n?(.*)$", re.DOTALL)
WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")

ARTICLE_FIELDS = "id title handle isPublished blog { id handle }"
Q_BLOGS = "{ blogs(first: 50) { nodes { id title handle } } }"
Q_ARTICLE = f"query($id: ID!) {{ article(id: $id) {{ {ARTICLE_FIELDS} }} }}"
M_CREATE = f"""mutation($article: ArticleCreateInput!) {{
  articleCreate(article: $article) {{ article {{ {ARTICLE_FIELDS} }} userErrors {{ field message }} }}
}}"""
M_UPDATE = f"""mutation($id: ID!, $article: ArticleUpdateInput!) {{
  articleUpdate(id: $id, article: $article) {{ article {{ {ARTICLE_FIELDS} }} userErrors {{ field message }} }}
}}"""
M_STAGED = """mutation($input: [StagedUploadInput!]!) {
  stagedUploadsCreate(input: $input) {
    stagedTargets { url resourceUrl parameters { name value } } userErrors { field message }
  }
}"""
M_FILE = """mutation($files: [FileCreateInput!]!) {
  fileCreate(files: $files) { files { id fileStatus } userErrors { field message } }
}"""
Q_FILE = """query($id: ID!) { node(id: $id) {
  ... on MediaImage { fileStatus image { url } }
  ... on Video { fileStatus sources { url mimeType height } }
} }"""


class Fail(Exception):
    pass


# --- config & transport -------------------------------------------------------

def load_config() -> dict:
    cfg = {}
    if CONFIG.exists():
        data = json.loads(CONFIG.read_text())
        cfg = {k[len("shopify_"):]: str(v or "").strip()
               for k, v in data.items() if k.startswith("shopify_")}
    for key in ("store", "client_id", "client_secret", "access_token", "blog_id", "author"):
        if os.environ.get(f"SHOPIFY_{key.upper()}"):
            cfg[key] = os.environ[f"SHOPIFY_{key.upper()}"].strip()
    cfg["store"] = cfg.get("store", "").lower()
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]*\.myshopify\.com", cfg["store"]):
        raise Fail("Set SHOPIFY_STORE (name.myshopify.com) or shopify_store in ~/.workbench/config.json.")
    if not cfg.get("access_token") and not (cfg.get("client_id") and cfg.get("client_secret")):
        raise Fail("No Shopify credentials: need client_id + client_secret, or access_token.")
    return cfg


def redact(text: str, cfg: dict) -> str:
    text = re.sub(r"<[^>]*>", " ", text)
    for key in ("client_secret", "access_token", "client_id"):
        if cfg.get(key):
            text = text.replace(cfg[key], "[redacted]")
    return " ".join(text.split())[:300]


_token_cache: dict = {}


def token(cfg: dict) -> str:
    if cfg.get("access_token"):
        return cfg["access_token"]
    if "t" not in _token_cache:
        r = httpx.post(f"https://{cfg['store']}/admin/oauth/access_token", timeout=30, data={
            "grant_type": "client_credentials",
            "client_id": cfg["client_id"], "client_secret": cfg["client_secret"]})
        if r.status_code != 200 or not r.json().get("access_token"):
            raise Fail(f"Token request failed: HTTP {r.status_code} {redact(r.text, cfg)}")
        _token_cache["t"] = r.json()["access_token"]
    return _token_cache["t"]


def gql(cfg: dict, query: str, variables: dict | None = None, op: str | None = None) -> dict:
    r = httpx.post(f"https://{cfg['store']}/admin/api/{API_VERSION}/graphql.json", timeout=60,
                   headers={"X-Shopify-Access-Token": token(cfg)},
                   json={"query": query, "variables": variables or {}})
    if r.status_code != 200:
        raise Fail(f"Admin API HTTP {r.status_code}: {redact(r.text, cfg)}")
    body = r.json()
    if body.get("errors"):
        raise Fail("; ".join(str(e.get("message", e)) for e in body["errors"]))
    data = body.get("data") or {}
    if op:
        node = data.get(op) or {}
        if node.get("userErrors"):
            raise Fail("; ".join(e.get("message", "?") for e in node["userErrors"]))
        return node
    return data


# --- commands -----------------------------------------------------------------

def cmd_check(cfg: dict, _args) -> None:
    blogs = gql(cfg, Q_BLOGS)["blogs"]["nodes"]
    print(f"OK: {cfg['store']} (author: {cfg.get('author') or '—'})")
    for b in blogs:
        mark = "  ← default" if b["id"] == cfg.get("blog_id") else ""
        print(f"  {b['id']}  {b['handle']}  {b['title']}{mark}")


def build_article(path: Path, cfg: dict, status_override: str | None):
    meta, body = (lambda p: (p.metadata, p.content or ""))(frontmatter.load(str(path)))
    kind = str(meta.get("type") or "").lower()
    if kind in {"product", "page"} or meta.get("shopify_product_id") or meta.get("shopify_page_id"):
        raise Fail(f"{path.name} is a Shopify {kind or 'product/page'} note, not a blog article.")
    title = str(meta.get("title") or "").strip()
    h1 = re.search(r"^#\s+(.+?)\s*$", body, re.M)
    if not title:
        title = h1.group(1).strip() if h1 else path.stem
    if h1 and h1.group(1).strip() == title:
        body = body.replace(h1.group(0), "", 1)
    title = WIKILINK_RE.sub(lambda m: m.group(1).split("|")[-1], title)
    local = re.findall(r"!\[[^\]]*\]\((?!https?://)([^)]+)\)|!\[\[([^\]]+)\]\]", body)
    if local:
        names = ", ".join(a or b for a, b in local)
        raise Fail(f"Local embeds won't render on Shopify: {names}. Run `upload` and use the CDN URL.")
    body = WIKILINK_RE.sub(lambda m: m.group(1).split("|")[-1], body)
    html = markdown.markdown(body.strip(), extensions=["extra", "sane_lists", "smarty"])
    raw = status_override or meta.get("publish", "draft")
    status = "publish" if str(raw).strip().lower() in LIVE else "draft"
    audience = str(meta.get("audience") or meta.get("visibility") or "").lower()
    if status == "publish" and audience in RESTRICTED:
        raise Fail("Note is marked for a restricted audience; Shopify articles are public.")
    tags = list(dict.fromkeys(t.strip() for t in (
        meta.get("tags") if isinstance(meta.get("tags"), list)
        else str(meta.get("tags") or "").split(",")) if str(t).strip()))
    blog_id = str(meta.get("shopify_blog_id") or cfg.get("blog_id") or "")
    if not blog_id.startswith("gid://shopify/Blog/"):
        raise Fail("No blog: set shopify_blog_id (note) or SHOPIFY_BLOG_ID; see `check`.")
    payload = {"blogId": blog_id, "title": title, "body": html,
               "tags": tags, "isPublished": status == "publish"}
    summary = str(meta.get("summary") or meta.get("description") or "").strip()
    if summary:
        payload["summary"] = markdown.markdown(summary)
    article_id = str(meta.get("shopify_article_id") or "").strip()
    if not article_id:
        if not cfg.get("author"):
            raise Fail("No author: set SHOPIFY_AUTHOR or shopify_author.")
        payload["author"] = {"name": cfg["author"]}
    if article_id and meta.get("shopify_store") and meta["shopify_store"] != cfg["store"]:
        raise Fail("This note belongs to a different Shopify store.")
    return payload, article_id, status


def writeback(path: Path, fields: dict) -> None:
    """Edit frontmatter lines in place so the rest of the note keeps its formatting."""
    text = path.read_text(encoding="utf-8")
    m = FM_RE.match(text)
    fm, body = (m.group(1), m.group(2)) if m else ("", "\n" + text)
    lines = fm.split("\n") if fm else []
    for key, value in fields.items():
        idx = next((i for i, l in enumerate(lines) if re.match(rf"^{re.escape(key)}\s*:", l)), None)
        if idx is None:
            lines.append(f"{key}: {value}")
        else:
            lines[idx] = f"{key}: {value}"
    path.write_text("---\n" + "\n".join(lines) + "\n---\n" + body, encoding="utf-8")


def cmd_publish(cfg: dict, args) -> None:
    path = Path(args.note).expanduser()
    if not path.is_file():
        raise Fail(f"Note not found: {path}")
    override = "publish" if args.live else "draft" if args.draft else None
    payload, article_id, status = build_article(path, cfg, override)
    action = "update" if article_id else "create"
    print(f"{'DRY RUN — would ' if args.dry_run else ''}{action} [{status}] "
          f"\"{payload['title']}\" tags={payload['tags']} ({len(payload['body'])} chars HTML)")
    if args.dry_run:
        return
    if article_id:
        remote = gql(cfg, Q_ARTICLE, {"id": article_id}).get("article")
        if not remote:
            raise Fail("shopify_article_id in the note was not found on the store.")
        if remote["blog"]["id"] != payload["blogId"]:
            raise Fail("This article belongs to a different blog.")
        art = gql(cfg, M_UPDATE, {"id": article_id, "article": payload}, "articleUpdate")["article"]
    else:
        art = gql(cfg, M_CREATE, {"article": payload}, "articleCreate")["article"]
    status = "publish" if art["isPublished"] else "draft"
    url = f"https://{cfg['store']}/blogs/{art['blog']['handle']}/{art['handle']}" if status == "publish" else ""
    fields = {"shopify_article_id": art["id"], "shopify_store": cfg["store"],
              "shopify_blog_id": art["blog"]["id"], "shopify_published_url": url,
              "published_at": date.today().isoformat(), "publish": status}
    if not frontmatter.load(str(path)).metadata.get("wp_post_id"):
        fields["published_url"] = url  # Workbench parity: WordPress owns it when present
    writeback(path, fields)
    admin = f"https://admin.shopify.com/store/{cfg['store'].split('.')[0]}/articles/{art['id'].rsplit('/', 1)[-1]}"
    print(f"{action}d [{status}] {art['id']}\n  admin: {admin}" + (f"\n  live:  {url}" if url else ""))


def cmd_upload(cfg: dict, args) -> None:
    f = Path(args.file).expanduser()
    if not f.is_file():
        raise Fail(f"File not found: {f}")
    mime = mimetypes.guess_type(f.name)[0] or ""
    kind = "IMAGE" if mime.startswith("image/") else "VIDEO" if mime.startswith("video/") else None
    if not kind:
        raise Fail(f"{f.name}: only images (png/jpg/gif/webp) and videos (mp4/webm) are supported.")
    data = f.read_bytes()
    target = gql(cfg, M_STAGED, {"input": [{
        "filename": f.name, "mimeType": mime, "httpMethod": "POST",
        "resource": kind, "fileSize": str(len(data))}]}, "stagedUploadsCreate")["stagedTargets"][0]
    r = httpx.post(target["url"], data={p["name"]: p["value"] for p in target["parameters"]},
                   files={"file": (f.name, data, mime)}, timeout=600)
    if r.status_code >= 300:
        raise Fail(f"Upload failed: HTTP {r.status_code}")
    file_id = gql(cfg, M_FILE, {"files": [{
        "originalSource": target["resourceUrl"], "contentType": kind,
        "alt": args.alt or f.stem}]}, "fileCreate")["files"][0]["id"]
    for _ in range(60 if kind == "VIDEO" else 15):
        node = gql(cfg, Q_FILE, {"id": file_id}).get("node") or {}
        if node.get("fileStatus") == "FAILED":
            raise Fail(f"Shopify failed to process {f.name}.")
        mp4s = [s for s in node.get("sources") or [] if s.get("mimeType") == "video/mp4"]
        url = (node.get("image") or {}).get("url") or (
            max(mp4s, key=lambda s: s.get("height") or 0)["url"] if mp4s else None)
        if url:
            print(url)
            return
        time.sleep(2)
    print(f"Uploaded as {file_id}; still processing — rerun later or check Admin → Content → Files.")


def main() -> int:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("check")
    pub = sub.add_parser("publish")
    pub.add_argument("note")
    pub.add_argument("--dry-run", action="store_true")
    g = pub.add_mutually_exclusive_group()
    g.add_argument("--draft", action="store_true")
    g.add_argument("--live", action="store_true")
    up = sub.add_parser("upload")
    up.add_argument("file")
    up.add_argument("--alt", default="")
    args = p.parse_args()
    try:
        cfg = load_config()
        {"check": cmd_check, "publish": cmd_publish, "upload": cmd_upload}[args.cmd](cfg, args)
    except (Fail, httpx.HTTPError) as ex:
        print(f"error: {ex}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
