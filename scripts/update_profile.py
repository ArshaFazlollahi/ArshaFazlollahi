"""Build public profile cards from private/public metadata without publishing repo names."""

from __future__ import annotations

import base64
import concurrent.futures
import datetime as dt
import html
import json
import os
from pathlib import Path
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
API = "https://api.github.com"
USERNAME = "ArshaFazlollahi"
LANGUAGE_COLORS = {
    "Python": "#3572A5", "TypeScript": "#3178c6", "JavaScript": "#f1e05a",
    "Java": "#b07219", "Dart": "#00B4AB", "Lua": "#000080",
    "C++": "#f34b7d", "C": "#555555", "HTML": "#e34c26", "CSS": "#663399",
    "TeX": "#3D6117", "Shell": "#89e051", "PowerShell": "#012456",
}
PRIMARY_LANGUAGES = [
    "Python", "TypeScript", "JavaScript", "Java", "Dart", "Lua", "C++", "C",
    "HTML", "CSS", "Shell", "PowerShell", "TeX",
]
FRAMEWORK_PATTERNS = {
    "React": r'(?i)["\s]react["\s:=<>=]',
    "FastAPI": r'(?i)\bfastapi\b',
    "SQLAlchemy": r'(?i)\bsqlalchemy\b',
    "PostgreSQL": r'(?i)\bpostgres(?:ql)?\b',
    "Flutter": r'(?i)\bflutter\s*:',
    "Firebase": r'(?i)\bfirebase(?:_core|_auth|_database)?\b',
    "Playwright": r'(?i)\bplaywright\b',
    "BeautifulSoup": r'(?i)\bbeautifulsoup4\b',
    "Pandas": r'(?i)\bpandas\b',
    "NumPy": r'(?i)\bnumpy\b',
    "PySide6": r'(?i)\bpyside6\b',
    "Pytest": r'(?i)\bpytest\b',
    "Vite": r'(?i)["\s]vite["\s:=<>=]',
}
MANIFEST = re.compile(
    r"(?:^|/)(?:package\.json|requirements(?:[-\w]*)\.txt|pyproject\.toml|"
    r"pubspec\.yaml|(?:docker-)?compose\.ya?ml|Dockerfile)$"
)
EXCLUDED_PATH = re.compile(r"(?:^|/)(?:node_modules|vendor|\.venv|venv|build|dist|\.git)/")


class ProfileError(RuntimeError):
    """A safe error message that never includes a token or private URL."""


class GitHub:
    def __init__(self, token: str):
        if not token:
            raise ProfileError("PROFILE_READ_TOKEN is missing; existing cards were not changed.")
        self.token = token

    def request(self, path: str, payload=None, missing_ok=False):
        if not path.startswith("/"):
            raise ProfileError("Refusing a non-GitHub API destination.")
        body = json.dumps(payload).encode() if payload is not None else None
        request = urllib.request.Request(
            API + path, data=body,
            headers={
                "Authorization": "Bearer " + self.token,
                "Accept": "application/vnd.github+json",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "Arsha-Profile-Aggregator",
                "Content-Type": "application/json",
            },
        )
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=30) as response:
                    return json.load(response)
            except urllib.error.HTTPError as error:
                if missing_ok and error.code in (404, 409):
                    return None
                if error.code in (429, 500, 502, 503, 504) and attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                raise ProfileError(f"GitHub API returned HTTP {error.code}; existing cards were kept.") from None
            except (urllib.error.URLError, TimeoutError):
                if attempt < 2:
                    time.sleep(2 ** attempt)
                    continue
                raise ProfileError("GitHub API was unavailable; existing cards were kept.") from None
        raise ProfileError("GitHub API request failed.")

    def graphql(self, query: str, variables=None):
        result = self.request("/graphql", {"query": query, "variables": variables or {}})
        if result.get("errors"):
            raise ProfileError("GitHub GraphQL access was incomplete; existing cards were kept.")
        return result["data"]


def owned_repositories(api: GitHub):
    repositories = []
    for page in range(1, 101):
        batch = api.request(f"/user/repos?affiliation=owner&per_page=100&page={page}")
        repositories.extend(batch)
        if len(batch) < 100:
            return repositories
    raise ProfileError("Repository pagination exceeded its safety bound; cards were not changed.")


def repository_facts(api: GitHub, repository):
    # Private names, paths, content and per-repository values stay in memory only.
    prefix = "/repos/" + repository["full_name"]
    languages = api.request(prefix + "/languages")
    technologies = {"Docker"} if languages.get("Dockerfile", 0) else set()
    if not repository.get("size"):
        return languages, technologies
    branch = urllib.parse.quote(repository["default_branch"], safe="")
    tree = api.request(prefix + "/git/trees/" + branch + "?recursive=1", missing_ok=True)
    if tree is None:
        return languages, technologies
    if tree.get("truncated"):
        raise ProfileError("A repository inventory was truncated; existing cards were kept.")
    paths = [entry["path"] for entry in tree["tree"] if entry["type"] == "blob"]
    if any(path.startswith(".github/workflows/") and path.endswith((".yml", ".yaml")) for path in paths):
        technologies.add("GitHub Actions")
    manifests = sorted(
        (path for path in paths if MANIFEST.search(path) and not EXCLUDED_PATH.search(path)),
        key=lambda path: (path.count("/"), path),
    )[:12]
    for path in manifests:
        item = api.request(prefix + "/contents/" + urllib.parse.quote(path, safe="/"))
        if item.get("encoding") != "base64":
            continue
        content = base64.b64decode(item["content"]).decode("utf-8", errors="replace")
        if path.rsplit("/", 1)[-1] == "Dockerfile":
            technologies.add("Docker")
        for name, pattern in FRAMEWORK_PATTERNS.items():
            if re.search(pattern, content):
                technologies.add(name)
    return languages, technologies


def authored_commit_totals(api: GitHub, repositories, user_id: str, since: str):
    all_time = recent = 0
    for start in range(0, len(repositories), 25):
        parts = []
        for index, repository in enumerate(repositories[start:start + 25]):
            parts.append(
                f'r{index}: repository(owner: {json.dumps(USERNAME)}, name: {json.dumps(repository["name"])}) {{ '
                'defaultBranchRef { target { ... on Commit { '
                'all: history(author: {id: $author}, first: 1) { totalCount } '
                'recent: history(author: {id: $author}, since: $since, first: 1) { totalCount } '
                '} } } }'
            )
        data = api.graphql(
            'query($author: ID!, $since: GitTimestamp!) { ' + " ".join(parts) + ' }',
            {"author": user_id, "since": since},
        )
        for item in data.values():
            if item is None:
                raise ProfileError("A repository could not be read; existing cards were kept.")
            target = (item.get("defaultBranchRef") or {}).get("target")
            if target:
                all_time += target["all"]["totalCount"]
                recent += target["recent"]["totalCount"]
    return all_time, recent


def collect(api: GitHub):
    viewer = api.request("/user")
    if viewer["login"].lower() != USERNAME.lower():
        raise ProfileError("The token must belong to the profile owner.")
    repositories = owned_repositories(api)
    private_count = sum(bool(repository["private"]) for repository in repositories)
    expected = viewer.get("owned_private_repos")
    minimum = int(os.environ.get("PROFILE_MIN_PRIVATE_REPOS", "6"))
    if private_count < minimum or (expected is not None and private_count != expected):
        raise ProfileError("The token cannot see all expected private repositories; cards were not changed.")
    languages = {}
    technologies = {"Git"}
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        facts = pool.map(lambda repository: repository_facts(api, repository), repositories)
        for repository_languages, repository_technologies in facts:
            for language, size in repository_languages.items():
                languages[language] = languages.get(language, 0) + size
            technologies.update(repository_technologies)
    now = dt.datetime.now(dt.timezone.utc)
    since = (now - dt.timedelta(days=365)).isoformat()
    commits, recent_commits = authored_commit_totals(api, repositories, viewer["node_id"], since)
    activity = api.graphql(
        'query($from: DateTime!, $to: DateTime!) { viewer { contributionsCollection(from: $from, to: $to) { '
        'restrictedContributionsCount contributionCalendar { totalContributions } } } }',
        {"from": since, "to": now.isoformat()},
    )["viewer"]["contributionsCollection"]
    return {
        "updated": now.date().isoformat(), "username": USERNAME,
        "repositories": len(repositories), "public_repositories": len(repositories) - private_count,
        "private_repositories": private_count, "authored_commits": commits,
        "authored_commits_last_year": recent_commits,
        "contributions_last_year": activity["contributionCalendar"]["totalContributions"],
        "stars": sum(repository["stargazers_count"] for repository in repositories),
        "languages": dict(sorted(languages.items(), key=lambda item: (-item[1], item[0]))),
        "technologies": sorted(technologies),
    }


def svg_card(title: str, subtitle: str, body: str, theme: str, footer: str):
    dark = theme == "dark"
    text, muted = ("#f0f6fc", "#9198a1") if dark else ("#1f2328", "#59636e")
    accent, border = ("#58a6ff", "#30363d") if dark else ("#0969da", "#d1d9e0")
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="500" height="370" viewBox="0 0 500 370" '
        'role="img" aria-labelledby="title description">'
        f'<title id="title">{html.escape(title)}</title><desc id="description">{html.escape(subtitle)}</desc>'
        f'<style>text{{font-family:Segoe UI,Arial,sans-serif;fill:{text}}}.title{{font-size:22px;font-weight:700;fill:{accent}}}'
        f'.muted{{font-size:12px;fill:{muted}}}.label{{font-size:14px}}.value{{font-size:17px;font-weight:600}}</style>'
        f'<rect x=".5" y=".5" width="499" height="369" rx="14" fill="none" stroke="{border}"/>'
        f'<text x="26" y="38" class="title">{html.escape(title)}</text>'
        f'<text x="26" y="61" class="muted">{html.escape(subtitle)}</text>'
        + body + f'<text x="26" y="348" class="muted">{html.escape(footer)}</text></svg>\n'
    )


def stats_card(data, theme):
    rows = [
        ("Owned repositories", str(data["repositories"])),
        ("Public / private", f'{data["public_repositories"]} / {data["private_repositories"]}'),
        ("Authored commits · all time", f'{data["authored_commits"]:,}'),
        ("Authored commits · last 12 months", f'{data["authored_commits_last_year"]:,}'),
        ("Contributions · last 12 months", f'{data["contributions_last_year"]:,}'),
        ("Stars earned", f'{data["stars"]:,}'),
    ]
    body = "".join(
        f'<text x="26" y="{99 + index * 35}" class="label">{html.escape(label)}</text>'
        f'<text x="474" y="{99 + index * 35}" class="value" text-anchor="end">{value}</text>'
        for index, (label, value) in enumerate(rows)
    )
    body += '<text x="26" y="309" class="muted">Commit counts: account-linked authors on default branches.</text>'
    return svg_card("Arsh4's GitHub Stats", "Combined public + private activity", body, theme, "Updated " + data["updated"])


def language_card(data, theme):
    total = sum(data["languages"].values())
    ordered = list(data["languages"].items())
    entries = ordered[:9]
    if len(ordered) > 9:
        entries.append(("Other", sum(size for _, size in ordered[9:])))
    body = ""
    for index, (language, size) in enumerate(entries):
        percentage = size / total * 100 if total else 0
        y = 90 + index * 23
        color = LANGUAGE_COLORS.get(language, "#8b949e")
        body += f'<circle cx="32" cy="{y - 5}" r="4" fill="{color}"/>'
        body += f'<text x="45" y="{y}" class="label">{html.escape(language)}</text>'
        body += f'<rect x="175" y="{y - 11}" width="210" height="8" rx="4" fill="{color}" opacity=".15"/>'
        body += f'<rect x="175" y="{y - 11}" width="{percentage * 2.1:.2f}" height="8" rx="4" fill="{color}"/>'
        body += f'<text x="474" y="{y}" class="label" text-anchor="end">{percentage:.1f}%</text>'
    return svg_card("Most Used Languages", "All owned public + private repositories · code bytes", body, theme, "Not proficiency or time spent · Updated " + data["updated"])


def badge(name):
    colors = {"Python": "3776AB", "TypeScript": "3178C6", "JavaScript": "323330", "Java": "ED8B00",
              "HTML": "E34F26", "CSS": "663399", "Dart": "0175C2", "Lua": "2C2D72",
              "C++": "00599C", "C": "555555", "React": "20232A", "FastAPI": "009688",
              "PostgreSQL": "4169E1", "Docker": "2496ED", "Flutter": "02569B"}
    encoded = urllib.parse.quote(name.replace("-", "--"), safe="")
    return f'![{name}](https://img.shields.io/badge/{encoded}-{colors.get(name, "30363D")}?style=for-the-badge)'


def skills_block(data):
    languages = [language for language in PRIMARY_LANGUAGES if data["languages"].get(language)]
    return (
        "### Languages\n\n" + "\n".join(map(badge, languages)) +
        "\n\n### Frameworks, data & tooling\n\n" + "\n".join(map(badge, data["technologies"])) +
        "\n\n<sub>Based on committed languages and dependency/configuration manifests across my public and private projects. "
        "Language detection may include documentation and scaffolding; it is not a proficiency ranking.</sub>\n"
    )


def publish(data):
    # Only aggregate whitelisted data is serialized; never a repository inventory.
    allowed = {"updated", "username", "repositories", "public_repositories", "private_repositories",
               "authored_commits", "authored_commits_last_year", "contributions_last_year", "stars",
               "languages", "technologies"}
    if set(data) != allowed:
        raise ProfileError("Unexpected data fields; refusing to publish.")
    readme_path = ROOT / "README.md"
    readme = readme_path.read_text(encoding="utf-8")
    pattern = r"(<!-- SKILLS:START -->\n).*?(<!-- SKILLS:END -->)"
    readme, count = re.subn(pattern, lambda match: match[1] + skills_block(data) + "\n" + match[2], readme, flags=re.S)
    if count != 1:
        raise ProfileError("Expected exactly one managed skills section; cards were not changed.")
    outputs = {ROOT / "profile/summary.json": json.dumps(data, indent=2) + "\n", readme_path: readme}
    for theme in ("light", "dark"):
        outputs[ROOT / f"profile/stats-{theme}.svg"] = stats_card(data, theme)
        outputs[ROOT / f"profile/languages-{theme}.svg"] = language_card(data, theme)
    for path, content in outputs.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8", newline="\n")


def main():
    try:
        data = collect(GitHub(os.environ.get("PROFILE_READ_TOKEN", "")))
        publish(data)
    except ProfileError as error:
        print(str(error), file=sys.stderr)
        return 1
    print(f'Updated aggregate cards from {data["repositories"]} repositories ({data["private_repositories"]} private).')
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
