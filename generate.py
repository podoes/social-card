#!/usr/bin/env python3
"""Draws the podoes social card for a GitHub repository.

Reads the repository's name, description and stats from the GitHub API and
writes a 1280x640 PNG. Text is converted to outlines with the bundled fonts,
so the result looks the same on every machine.

Needs: python3, fonttools (pip install fonttools), rsvg-convert (librsvg2-bin).
"""
import argparse
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request

from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont

HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = {
    "display": os.path.join(HERE, "fonts", "Sora-SemiBold.ttf"),
    "regular": os.path.join(HERE, "fonts", "Inter-Regular.ttf"),
    "strong": os.path.join(HERE, "fonts", "Inter-SemiBold.ttf"),
}

# podoes tokens
BG, SURFACE, BORDER = "#141210", "#1E1B18", "#2E2A25"
INK, INK_SOFT, INK_MUTED = "#EDE8E1", "#D2CBC1", "#A39B90"
BRAND = "#E4521B"

W, H, PAD = 1280, 640, 80

ICONS = {
    "stars": '<path d="M12 3l2.7 5.6 6.1.9-4.4 4.3 1 6.1L12 17l-5.4 2.9 1-6.1L3.2 9.5l6.1-.9z"/>',
    "forks": '<circle cx="6" cy="5" r="2.2"/><circle cx="18" cy="5" r="2.2"/><circle cx="12" cy="19" r="2.2"/>'
             '<path d="M6 7.2v2.3a3 3 0 003 3h6a3 3 0 003-3V7.2M12 12.5v4.3"/>',
    "issues": '<circle cx="12" cy="12" r="9"/><circle cx="12" cy="12" r="1.6" fill="{c}"/>',
    "contributors": '<circle cx="9" cy="7.5" r="3.5"/><path d="M2.5 20a6.5 6.5 0 0113 0M16 4.3a3.5 3.5 0 010 6.4M18.5 14.2a6.5 6.5 0 013 5.8"/>',
    "release": '<path d="M3 12.6V4h8.6l9 9-8.6 8.6z"/><circle cx="7.6" cy="8.6" r="1.3"/>',
}
LABELS = {"stars": "stars", "forks": "forks", "issues": "open issues", "contributors": "contributors", "release": "latest"}

_cache = {}


def font(key):
    if key not in _cache:
        f = TTFont(FONTS[key])
        _cache[key] = (f, f.getGlyphSet(), f.getBestCmap(), f["head"].unitsPerEm)
    return _cache[key]


def clean(key, s):
    """Drop characters the font has no glyph for, so odd input never crashes the run."""
    cmap = font(key)[2]
    return "".join(ch for ch in s if ord(ch) in cmap)


def width(key, s, size, spacing=0.0):
    _, gs, cmap, upm = font(key)
    return sum(gs[cmap[ord(ch)]].width * size / upm + spacing * size for ch in s) - (spacing * size if s else 0)


def text(key, s, size, x, y, fill, spacing=0.0):
    """One line of text as an SVG path. y is the baseline."""
    _, gs, cmap, upm = font(key)
    k = size / upm
    parts, cx = [], x
    for ch in s:
        name = cmap[ord(ch)]
        pen = SVGPathPen(gs)
        gs[name].draw(TransformPen(pen, (k, 0, 0, -k, cx, y)))
        parts.append(pen.getCommands())
        cx += gs[name].width * k + spacing * size
    return '<path d="%s" fill="%s"/>' % (" ".join(parts), fill)


def wrap(key, s, size, max_w, max_lines):
    words, lines, cur = s.split(), [], ""
    for i, word in enumerate(words):
        trial = (cur + " " + word).strip()
        if width(key, trial, size) <= max_w or not cur:
            cur = trial
            continue
        lines.append(cur)
        cur = word
        if len(lines) == max_lines:
            break
    else:
        if cur:
            lines.append(cur)
        return lines
    last = lines[-1]
    while last and width(key, last + "...", size) > max_w:
        last = last[:-1].rstrip()
    lines[-1] = last + "..."
    return lines


def short(n):
    if n >= 1_000_000:
        return ("%.1f" % (n / 1_000_000)).rstrip("0").rstrip(".") + "M"
    if n >= 1_000:
        return ("%.1f" % (n / 1_000)).rstrip("0").rstrip(".") + "k"
    return str(n)


def mark(x, y, scale):
    """The peeker. Drawn in a 200 unit box."""
    return (
        '<g transform="translate(%s %s) scale(%s)">'
        '<circle cx="76" cy="104" r="25" fill="%s"/><circle cx="124" cy="104" r="25" fill="%s"/>'
        '<circle cx="84" cy="98" r="10" fill="%s"/><circle cx="132" cy="98" r="10" fill="%s"/>'
        '<rect x="26" y="58" width="148" height="22" rx="10" fill="%s" transform="rotate(-9 100 69)"/>'
        '<rect x="32" y="120" width="136" height="52" rx="12" fill="%s"/></g>'
    ) % (x, y, scale, INK, INK, BG, BG, BRAND, BRAND)


def api(path, token):
    base = os.environ.get("GITHUB_API_URL", "https://api.github.com").rstrip("/")
    req = urllib.request.Request(base + path, headers={
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "podoes-social-card",
    })
    if token:
        req.add_header("Authorization", "Bearer " + token)
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r), r.headers


def fetch(repo, token):
    """Everything the card shows, as one small dict."""
    info, _ = api("/repos/" + repo, token)
    data = {
        "owner": info["owner"]["login"],
        "name": info["name"],
        "description": info.get("description") or "",
        "language": info.get("language") or "",
        "stars": info.get("stargazers_count", 0),
        "forks": info.get("forks_count", 0),
    }
    try:  # open issues without pull requests
        found, _ = api("/search/issues?q=repo:%s+is:issue+is:open&per_page=1" % repo, token)
        data["issues"] = found["total_count"]
    except (urllib.error.URLError, KeyError):
        data["issues"] = info.get("open_issues_count", 0)
    try:  # the last page number of a one per page listing is the count
        people, headers = api("/repos/%s/contributors?per_page=1&anon=true" % repo, token)
        m = re.search(r'[?&]page=(\d+)>; rel="last"', headers.get("Link") or "")
        data["contributors"] = int(m.group(1)) if m else len(people)
    except urllib.error.URLError:
        pass
    try:
        release, _ = api("/repos/%s/releases/latest" % repo, token)
        data["release"] = release["tag_name"]
    except urllib.error.URLError:
        pass  # no release yet
    return data


def build(data, show_stats=True):
    owner = clean("display", data["owner"])
    name = clean("display", data["name"])
    desc = clean("regular", data.get("description") or "")
    body = ['<rect width="%d" height="%d" fill="%s"/>' % (W, H, BG)]

    # mascot, top right
    body.append(mark(880, 44, 1.6))
    text_w = 760

    # owner line
    body.append(mark(PAD - 9, 66, 0.3))
    body.append(text("display", owner, 30, PAD + 62, 110, INK_MUTED, -0.01))

    # repository name, shrunk until it fits
    size = 112
    while size > 56 and width("display", name, size, -0.02) > text_w:
        size -= 4
    lines = wrap("regular", desc, 34, text_w, 2) if desc else []
    drop = size * 0.3 + 44  # from the name baseline to the first description baseline
    block = size * 0.78 + (drop + 46 * (len(lines) - 1) if lines else 0)
    top = 160 + max(0, (300 - block) / 2)
    base = top + size * 0.78
    body.append(text("display", name, size, PAD - size * 0.04, base, INK, -0.02))
    for i, line in enumerate(lines):
        body.append(text("regular", line, 34, PAD, base + drop + 46 * i, INK_SOFT))

    # footer
    body.append('<rect x="%d" y="496" width="%d" height="2" fill="%s"/>' % (PAD, W - 2 * PAD, BORDER))
    y = 566
    if show_stats:
        stats = []
        for key in ("stars", "forks", "issues", "contributors", "release"):
            if key not in data or data[key] in (None, ""):
                continue
            value = clean("strong", str(data[key])[:14]) if key == "release" else short(int(data[key]))
            stats.append((key, value, LABELS[key]))
        x = PAD
        gap = 44
        total = sum(40 + width("strong", v, 30) + 10 + width("regular", l, 24) for _, v, l in stats) + gap * (len(stats) - 1)
        while stats and total > W - 2 * PAD:  # drop from the end until the row fits
            k, v, l = stats.pop()
            total -= 40 + width("strong", v, 30) + 10 + width("regular", l, 24) + gap
        for key, value, label in stats:
            body.append('<g transform="translate(%s %s) scale(1.25)" fill="none" stroke="%s" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round">%s</g>'
                        % (round(x, 1), y - 26, INK_MUTED, ICONS[key].replace("{c}", INK_MUTED)))
            x += 40
            body.append(text("strong", value, 30, x, y, INK))
            x += width("strong", value, 30) + 10
            body.append(text("regular", label, 24, x, y, INK_MUTED))
            x += width("regular", label, 24) + gap
    else:
        body.append(text("regular", "github.com/%s/%s" % (clean("regular", data["owner"]), clean("regular", data["name"])), 28, PAD, y, INK_MUTED))
        if data.get("language"):
            lang = clean("regular", data["language"])
            lw = width("regular", lang, 28)
            body.append('<circle cx="%s" cy="%s" r="8" fill="%s"/>' % (W - PAD - lw - 22, y - 10, BRAND))
            body.append(text("regular", lang, 28, W - PAD - lw, y, INK_MUTED))

    label = "%s/%s" % (data["owner"], data["name"])
    return ('<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 %d %d" width="%d" height="%d" role="img" aria-label="%s">%s</svg>\n'
            % (W, H, W, H, label.replace('"', ""), "".join(body)))


def main():
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY"), help="owner/name, defaults to the repository the Action runs in")
    p.add_argument("--out", default=".github/social-card.png", help="where to write the PNG")
    p.add_argument("--title", help="use this in place of the repository name")
    p.add_argument("--description", help="use this in place of the repository description")
    p.add_argument("--no-stats", action="store_true", help="draw the static version without numbers")
    p.add_argument("--data", help="read the card data from a JSON file and skip the GitHub API")
    p.add_argument("--svg", action="store_true", help="also keep the SVG next to the PNG")
    a = p.parse_args()

    if a.data:
        with open(a.data, encoding="utf-8") as f:
            data = json.load(f)
    else:
        if not a.repo or "/" not in a.repo:
            sys.exit("Pass --repo owner/name or set GITHUB_REPOSITORY.")
        data = fetch(a.repo, os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN"))
    if a.title:
        data["name"] = a.title
    if a.description is not None:
        data["description"] = a.description

    svg = build(data, show_stats=not a.no_stats)
    out = os.path.abspath(a.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    svg_path = os.path.splitext(out)[0] + ".svg"
    with open(svg_path, "w", encoding="utf-8") as f:
        f.write(svg)
    subprocess.run(["rsvg-convert", "-w", str(W), "-h", str(H), svg_path, "-o", out], check=True)
    if not a.svg:
        os.remove(svg_path)
    print("wrote", a.out, {k: v for k, v in data.items() if k not in ("description",)})


if __name__ == "__main__":
    main()
