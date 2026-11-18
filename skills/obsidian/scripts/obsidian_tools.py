#!/usr/bin/env python3
"""Small Obsidian vault helpers that work without the Obsidian app.

  obsidian_tools.py VAULT backlinks NOTE        # notes linking to NOTE
  obsidian_tools.py VAULT broken                # links that resolve to nothing
  obsidian_tools.py VAULT rename OLD NEW [--apply]  # move a file and rewrite links to it

NOTE/OLD/NEW are paths relative to the vault root (e.g. "10_Projects/Foo.md").
Handles [[wikilinks]] (incl. ![[embeds]], #heading, ^block, |alias) and relative
Markdown links [text](path.md). Ignores fenced and inline code. rename is a dry
run unless --apply; it uses `git mv` when the vault is a git repo.
"""
import os
import re
import subprocess
import sys
from pathlib import Path
from urllib.parse import quote, unquote

SKIP_DIRS = {".obsidian", ".git", ".trash", "node_modules", "vendor"}
WIKI = re.compile(r"(!?)\[\[([^\]|#^]*)([#^][^\]|]*)?(\|[^\]]*)?\]\]")
MDLINK = re.compile(r"(!?)\[([^\]]*)\]\(<?([^)>\s]+)>?\)")
CODE = re.compile(r"```.*?```|~~~.*?~~~|`[^`\n]*`", re.S)


def files(vault):
    for root, dirs, names in os.walk(vault):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for n in names:
            yield Path(root, n).relative_to(vault)


def blank_code(text):
    """Replace code spans with spaces so offsets stay valid."""
    return CODE.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), text)


class Vault:
    def __init__(self, root):
        self.root = Path(root).resolve()
        self.all = sorted(files(self.root))
        self.by_name = {}
        for p in self.all:
            for key in (p.name.lower(), p.stem.lower() if p.suffix == ".md" else None):
                if key:
                    self.by_name.setdefault(key, []).append(p)

    def resolve_wiki(self, target):
        t = target.strip().replace("\\", "/")
        if not t:
            return None  # [[#heading]] = same note
        low = t.lower()
        for cand in (low, low + ".md"):
            for p in self.all:
                if p.as_posix().lower() == cand:
                    return p
        hits = self.by_name.get(low.rsplit("/", 1)[-1]) or []
        hits = [h for h in hits if h.as_posix().lower().endswith(low) or h.as_posix().lower().endswith(low + ".md")]
        return min(hits, key=lambda h: len(h.parts)) if hits else False

    def resolve_md(self, src, href):
        if re.match(r"^[a-z][a-z0-9+.-]*:", href, re.I) or href.startswith("#"):
            return None  # external URL or same-note anchor
        path = unquote(href.split("#", 1)[0])
        p = (self.root / src.parent / path).resolve()
        try:
            rel = p.relative_to(self.root)
        except ValueError:
            return False
        return rel if (self.root / rel).exists() else False

    def links(self, src):
        """Yield (kind, match, resolved) for each link in src (md notes only)."""
        text = (self.root / src).read_text(encoding="utf-8", errors="replace")
        scan = blank_code(text)
        for m in WIKI.finditer(scan):
            yield "wiki", m, self.resolve_wiki(m.group(2))
        for m in MDLINK.finditer(scan):
            yield "md", m, self.resolve_md(src, m.group(3))

    def notes(self):
        return [p for p in self.all if p.suffix == ".md"]


def cmd_backlinks(v, note):
    target = Path(note)
    for src in v.notes():
        for kind, m, res in v.links(src):
            if res == target:
                print(f"{src}\t{m.group(0)}")


def cmd_broken(v):
    n = 0
    for src in v.notes():
        for kind, m, res in v.links(src):
            if res is False:
                n += 1
                print(f"{src}\t{m.group(0)}")
    print(f"{n} broken link(s)", file=sys.stderr)


def cmd_rename(v, old, new, apply):
    old, new = Path(old), Path(new)
    if old not in v.all:
        sys.exit(f"not found in vault: {old}")
    if (v.root / new).exists():
        sys.exit(f"already exists: {new}")
    edits = {}
    for src in v.notes():
        text = (v.root / src).read_text(encoding="utf-8", errors="replace")
        out, last, changed = [], 0, False
        new_src = new if src == old else src  # links inside the moved note itself
        for kind, m, res in v.links(src):
            if kind == "md" and src == old and res is not False and res is not None:
                pass  # relative links from the moved note must be recomputed
            elif res != old:
                continue
            if kind == "wiki":
                orig = m.group(2).strip()
                # keep the user's style: bare name if unambiguous, else full path
                if "/" in orig:
                    tgt = new.with_suffix("").as_posix() if new.suffix == ".md" else new.as_posix()
                else:
                    tgt = new.stem if new.suffix == ".md" else new.name
                    others = [p for p in v.by_name.get(tgt.lower(), []) if p != old]
                    if others:  # another note already has this name -> use full path
                        tgt = new.with_suffix("").as_posix() if new.suffix == ".md" else new.as_posix()
                rep = f"{m.group(1)}[[{tgt}{m.group(3) or ''}{m.group(4) or ''}]]"
            else:
                dest = new if res == old else res
                anchor = "#" + m.group(3).split("#", 1)[1] if "#" in m.group(3) else ""
                rel = os.path.relpath(dest, new_src.parent).replace(os.sep, "/")
                href = quote(rel) + anchor if "%" in m.group(3) else rel + anchor
                if " " in href:
                    href = f"<{href}>"
                rep = f"{m.group(1)}[{m.group(2)}]({href})"
            if rep != m.group(0):
                out.append((m.start(), m.end(), rep))
        if out:
            out.sort()
            buf = []
            for s, e, r in out:
                buf.append(text[last:s]); buf.append(r); last = e
            buf.append(text[last:])
            edits[src] = ("".join(buf), out)
    print(f"rename {old} -> {new}")
    for src, (_, out) in edits.items():
        for s, e, r in out:
            print(f"  {src}: -> {r}")
    print(f"{sum(len(o) for _, o in edits.values())} link(s) in {len(edits)} note(s)")
    if not apply:
        print("dry run; pass --apply to write")
        return
    for src, (text, _) in edits.items():
        (v.root / src).write_text(text, encoding="utf-8")
    (v.root / new).parent.mkdir(parents=True, exist_ok=True)
    in_git = subprocess.run(["git", "-C", str(v.root), "ls-files", "--error-unmatch", str(old)],
                            capture_output=True).returncode == 0
    if in_git:
        subprocess.run(["git", "-C", str(v.root), "mv", str(old), str(new)], check=True)
    else:
        (v.root / old).rename(v.root / new)
    print("applied")


def main(argv):
    if len(argv) < 2:
        sys.exit(__doc__)
    v, cmd, rest = Vault(argv[0]), argv[1], argv[2:]
    if cmd == "backlinks" and len(rest) == 1:
        cmd_backlinks(v, rest[0])
    elif cmd == "broken" and not rest:
        cmd_broken(v)
    elif cmd == "rename" and len(rest) in (2, 3):
        cmd_rename(v, rest[0], rest[1], "--apply" in rest)
    else:
        sys.exit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1:])
