"""Core markdown requirements parser for the NC Dev System.

Parses structured markdown documents and extracts features, API endpoints,
routes, external dependencies, and flags ambiguities. Uses pure regex and
markdown structure parsing -- no AI calls.
"""

from __future__ import annotations

import asyncio
import re
from pathlib import Path
from typing import Any

from .models import (
    APIEndpoint,
    Architecture,
    Complexity,
    Feature,
    HTTPMethod,
    ParseResult,
    Priority,
    Route,
    TestPlan,
)
from .architect import generate_architecture
from .test_planner import generate_test_plan


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_PRIORITY_PATTERN = re.compile(r"\(P([012])\)", re.IGNORECASE)
_HEADER_PATTERN = re.compile(r"^(#{1,6})\s+(.+)$", re.MULTILINE)
_BULLET_PATTERN = re.compile(r"^\s*[-*+]\s+(.+)$", re.MULTILINE)
_HTTP_METHOD_PATTERN = re.compile(
    r"\b(GET|POST|PUT|DELETE|PATCH)\b\s+[`/]([^\s`]+)[`]?", re.IGNORECASE
)
_ROUTE_PATTERN = re.compile(
    r"[`/](/[a-z0-9/_:{}*-]*)[`]?", re.IGNORECASE
)
_EXTERNAL_API_KEYWORDS = [
    "stripe", "twilio", "sendgrid", "mailgun", "aws", "s3", "firebase",
    "google maps", "openai", "slack", "github", "gitlab", "bitbucket",
    "paypal", "braintree", "auth0", "okta", "algolia", "elasticsearch",
    "cloudinary", "pusher", "segment", "mixpanel", "sentry", "datadog",
    "redis", "rabbitmq", "kafka", "websocket", "smtp", "oauth",
    "social login", "google login", "facebook login", "apple login",
    "twitter api", "spotify api",
]
_CRUD_KEYWORDS = {
    "create": HTTPMethod.POST,
    "add": HTTPMethod.POST,
    "new": HTTPMethod.POST,
    "register": HTTPMethod.POST,
    "signup": HTTPMethod.POST,
    "sign up": HTTPMethod.POST,
    "read": HTTPMethod.GET,
    "list": HTTPMethod.GET,
    "view": HTTPMethod.GET,
    "get": HTTPMethod.GET,
    "fetch": HTTPMethod.GET,
    "retrieve": HTTPMethod.GET,
    "search": HTTPMethod.GET,
    "filter": HTTPMethod.GET,
    "browse": HTTPMethod.GET,
    "update": HTTPMethod.PUT,
    "edit": HTTPMethod.PUT,
    "modify": HTTPMethod.PUT,
    "change": HTTPMethod.PUT,
    "delete": HTTPMethod.DELETE,
    "remove": HTTPMethod.DELETE,
    "soft delete": HTTPMethod.DELETE,
    "archive": HTTPMethod.PATCH,
    "toggle": HTTPMethod.PATCH,
    "mark": HTTPMethod.PATCH,
}
_AUTH_KEYWORDS = [
    "auth", "login", "logout", "signup", "sign up", "sign in", "register",
    "password", "session", "token", "jwt", "oauth", "keycloak", "sso",
    "role", "permission", "rbac", "acl", "credential",
]
_AMBIGUITY_PHRASES = [
    "tbd", "to be decided", "to be determined", "not sure", "maybe",
    "possibly", "or similar", "etc.", "and more", "as needed",
    "something like", "some kind of", "somehow", "figure out",
    "we'll decide later", "placeholder", "might need", "could be",
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _slugify(text: str) -> str:
    """Convert a feature name to a URL-safe slug."""
    slug = re.sub(r"[^a-z0-9]+", "-", text.lower().strip())
    return slug.strip("-")


def _infer_entity_name(feature_name: str) -> str:
    """Infer the primary entity/resource name from a feature name.

    Examples:
        'Task CRUD' -> 'tasks'
        'User Authentication' -> 'users'
        'Comment Management' -> 'comments'
        'Project Dashboard' -> 'projects'
    """
    # Remove common suffixes that don't indicate the entity
    cleaned = re.sub(
        r"\b(crud|management|system|module|feature|dashboard|"
        r"authentication|authorization|settings|configuration)\b",
        "",
        feature_name,
        flags=re.IGNORECASE,
    ).strip()

    # Take the first meaningful word
    words = [w for w in cleaned.split() if len(w) > 1]
    if not words:
        words = feature_name.lower().split()[:1]

    entity = words[0].lower().rstrip("s")
    # Basic pluralization
    if entity.endswith("y") and not entity.endswith("ey"):
        plural = entity[:-1] + "ies"
    elif entity.endswith(("s", "sh", "ch", "x", "z")):
        plural = entity + "es"
    else:
        plural = entity + "s"
    return plural


def _extract_priority(text: str) -> Priority:
    """Extract priority from text like '(P0)' or '(P1)'. Defaults to P1."""
    match = _PRIORITY_PATTERN.search(text)
    if match:
        level = int(match.group(1))
        return [Priority.P0, Priority.P1, Priority.P2][level]
    # Infer from keywords
    lower = text.lower()
    if any(kw in lower for kw in ["must", "critical", "essential", "core"]):
        return Priority.P0
    if any(kw in lower for kw in ["nice to have", "optional", "bonus", "stretch"]):
        return Priority.P2
    return Priority.P1


def _estimate_complexity(bullets: list[str], feature_name: str) -> Complexity:
    """Estimate feature complexity from its description bullets."""
    text = " ".join(bullets).lower() + " " + feature_name.lower()
    high_indicators = [
        "real-time", "realtime", "websocket", "payment", "billing",
        "integration", "oauth", "third-party", "machine learning",
        "ai", "video", "file upload", "encryption", "migration",
        "multi-tenant", "analytics", "reporting dashboard",
    ]
    low_indicators = [
        "static", "display", "about page", "landing", "faq",
        "simple", "basic", "single",
    ]
    if any(ind in text for ind in high_indicators):
        return Complexity.HIGH
    if len(bullets) <= 2 and any(ind in text for ind in low_indicators):
        return Complexity.LOW
    if len(bullets) > 5:
        return Complexity.HIGH
    return Complexity.MEDIUM


def _detect_external_apis(text: str) -> list[str]:
    """Detect references to external APIs in text."""
    lower = text.lower()
    found: list[str] = []
    for keyword in _EXTERNAL_API_KEYWORDS:
        if keyword in lower and keyword not in found:
            found.append(keyword)
    return found


def _detect_ambiguities(text: str) -> list[str]:
    """Flag ambiguous language in requirements text."""
    ambiguities: list[str] = []
    lower = text.lower()
    for phrase in _AMBIGUITY_PHRASES:
        if phrase in lower:
            # Find the sentence containing the phrase
            for line in text.splitlines():
                if phrase in line.lower():
                    cleaned = line.strip().lstrip("-*+ ").strip()
                    if cleaned:
                        ambiguities.append(
                            f"Ambiguous requirement: \"{cleaned}\" (contains '{phrase}')"
                        )
    return ambiguities


def _requires_auth(feature_name: str, bullets: list[str]) -> bool:
    """Determine if a feature requires authentication."""
    text = (feature_name + " " + " ".join(bullets)).lower()
    # Auth feature itself always requires auth infrastructure
    if any(kw in feature_name.lower() for kw in ["auth", "login", "user"]):
        return True
    # Check bullets for auth-related content
    auth_signals = ["requires login", "authenticated", "logged in", "user's",
                     "my ", "personal", "private", "admin", "role"]
    return any(sig in text for sig in auth_signals)


# ---------------------------------------------------------------------------
# Section Parsing
# ---------------------------------------------------------------------------

class _Section:
    """Represents a parsed markdown section with its header level, title, and body."""

    __slots__ = ("level", "title", "body", "children")

    def __init__(self, level: int, title: str, body: str) -> None:
        self.level = level
        self.title = title
        self.body = body
        self.children: list[_Section] = []

    def __repr__(self) -> str:
        return f"_Section(level={self.level}, title={self.title!r})"


def _parse_sections(markdown: str) -> list[_Section]:
    """Parse markdown into a tree of sections based on header levels."""
    lines = markdown.splitlines()
    sections: list[_Section] = []
    current: _Section | None = None
    body_lines: list[str] = []

    def _flush() -> None:
        nonlocal current, body_lines
        if current is not None:
            current.body = "\n".join(body_lines).strip()
            sections.append(current)
            body_lines = []

    for line in lines:
        header_match = _HEADER_PATTERN.match(line)
        if header_match:
            _flush()
            level = len(header_match.group(1))
            title = header_match.group(2).strip()
            current = _Section(level=level, title=title, body="")
        else:
            body_lines.append(line)

    _flush()

    # Build tree: nest children under parent sections
    if not sections:
        return sections

    root_sections: list[_Section] = []
    stack: list[_Section] = []

    for section in sections:
        while stack and stack[-1].level >= section.level:
            stack.pop()
        if stack:
            stack[-1].children.append(section)
        else:
            root_sections.append(section)
        stack.append(section)

    return root_sections


def _get_bullets(body: str) -> list[str]:
    """Extract bullet point content from a section body."""
    return [m.group(1).strip() for m in _BULLET_PATTERN.finditer(body)]


def _all_sections_flat(sections: list[_Section]) -> list[_Section]:
    """Flatten a section tree into a list."""
    result: list[_Section] = []
    for s in sections:
        result.append(s)
        result.extend(_all_sections_flat(s.children))
    return result


# ---------------------------------------------------------------------------
# Feature Extraction
# ---------------------------------------------------------------------------

def _extract_routes_from_bullets(
    bullets: list[str], feature_name: str, needs_auth: bool
) -> list[Route]:
    """Infer UI routes from bullet point descriptions."""
    routes: list[Route] = []
    entity = _infer_entity_name(feature_name)
    slug = _slugify(feature_name)

    # Scan bullets for explicit route references
    for bullet in bullets:
        route_matches = _ROUTE_PATTERN.findall(bullet)
        for path in route_matches:
            if path and len(path) > 1 and not path.startswith("/api"):
                routes.append(Route(
                    path=path,
                    name=bullet[:60],
                    description=bullet,
                    requires_auth=needs_auth,
                ))

    # If no explicit routes found, infer from CRUD keywords
    if not routes:
        lower_bullets = " ".join(bullets).lower()
        crud_routes_added: set[str] = set()

        # Check for list/browse patterns
        if any(kw in lower_bullets for kw in ["list", "browse", "view all", "read", "fetch"]):
            path = f"/{entity}"
            if path not in crud_routes_added:
                routes.append(Route(
                    path=path,
                    name=f"{feature_name} List",
                    description=f"List all {entity}",
                    requires_auth=needs_auth,
                ))
                crud_routes_added.add(path)

        # Check for detail/view patterns
        if any(kw in lower_bullets for kw in ["view", "detail", "read", "get"]):
            path = f"/{entity}/{{id}}"
            if path not in crud_routes_added:
                routes.append(Route(
                    path=path,
                    name=f"{feature_name} Detail",
                    description=f"View {entity} details",
                    requires_auth=needs_auth,
                ))
                crud_routes_added.add(path)

        # Check for create patterns
        if any(kw in lower_bullets for kw in ["create", "add", "new"]):
            path = f"/{entity}/new"
            if path not in crud_routes_added:
                routes.append(Route(
                    path=path,
                    name=f"Create {feature_name}",
                    description=f"Create a new {entity[:-1] if entity.endswith('s') else entity}",
                    requires_auth=needs_auth,
                ))
                crud_routes_added.add(path)

        # Check for edit patterns
        if any(kw in lower_bullets for kw in ["edit", "update", "modify"]):
            path = f"/{entity}/{{id}}/edit"
            if path not in crud_routes_added:
                routes.append(Route(
                    path=path,
                    name=f"Edit {feature_name}",
                    description=f"Edit {entity} details",
                    requires_auth=needs_auth,
                ))
                crud_routes_added.add(path)

        # Auth-specific routes
        if any(kw in feature_name.lower() for kw in ["auth", "login"]):
            auth_routes = [
                Route(path="/login", name="Login", description="User login page", requires_auth=False),
                Route(path="/register", name="Register", description="User registration page", requires_auth=False),
            ]
            if "password reset" in lower_bullets or "forgot password" in lower_bullets:
                auth_routes.append(Route(
                    path="/forgot-password", name="Forgot Password",
                    description="Password reset request page", requires_auth=False,
                ))
            for r in auth_routes:
                if r.path not in crud_routes_added:
                    routes.append(r)
                    crud_routes_added.add(r.path)

        # Dashboard route
        if "dashboard" in lower_bullets or "dashboard" in feature_name.lower():
            path = f"/{slug}"
            if path not in crud_routes_added:
                routes.append(Route(
                    path=path,
                    name=f"{feature_name}",
                    description=f"{feature_name} dashboard view",
                    requires_auth=needs_auth,
                ))

        # Fallback: if still no routes, add a generic one
        if not routes:
            routes.append(Route(
                path=f"/{slug}",
                name=feature_name,
                description=f"{feature_name} page",
                requires_auth=needs_auth,
            ))

    return routes


def _extract_api_endpoints_from_bullets(
    bullets: list[str], feature_name: str, needs_auth: bool
) -> list[APIEndpoint]:
    """Infer API endpoints from bullet descriptions."""
    endpoints: list[APIEndpoint] = []
    entity = _infer_entity_name(feature_name)
    base_path = f"/api/v1/{entity}"
    seen_methods: set[tuple[str, str]] = set()

    # First pass: look for explicit HTTP method + path references
    full_text = "\n".join(bullets)
    for match in _HTTP_METHOD_PATTERN.finditer(full_text):
        method_str = match.group(1).upper()
        path = match.group(2)
        if not path.startswith("/"):
            path = "/" + path
        method = HTTPMethod(method_str)
        key = (method_str, path)
        if key not in seen_methods:
            endpoints.append(APIEndpoint(
                method=method,
                path=path,
                description=f"{method_str} {path}",
                requires_auth=needs_auth,
                response_body={"status": "ok"},
            ))
            seen_methods.add(key)

    # Second pass: infer from CRUD keywords
    for bullet in bullets:
        lower_bullet = bullet.lower()
        for keyword, method in _CRUD_KEYWORDS.items():
            if keyword in lower_bullet:
                if method == HTTPMethod.POST:
                    path = base_path
                    desc = f"Create {entity}"
                elif method == HTTPMethod.GET:
                    if any(kw in lower_bullet for kw in ["list", "all", "browse", "search", "filter", "fetch"]):
                        path = base_path
                        desc = f"List {entity}"
                    else:
                        path = f"{base_path}/{{id}}"
                        desc = f"Get {entity} by ID"
                elif method == HTTPMethod.PUT:
                    path = f"{base_path}/{{id}}"
                    desc = f"Update {entity}"
                elif method == HTTPMethod.DELETE:
                    path = f"{base_path}/{{id}}"
                    desc = f"Delete {entity}"
                elif method == HTTPMethod.PATCH:
                    path = f"{base_path}/{{id}}"
                    desc = f"Patch {entity}"
                else:
                    continue

                key = (method.value, path)
                if key not in seen_methods:
                    request_body: dict[str, Any] | None = None
                    response_body: dict[str, Any] = {"id": "string"}

                    if method in (HTTPMethod.POST, HTTPMethod.PUT, HTTPMethod.PATCH):
                        request_body = _infer_request_body(bullets, entity)
                        response_body = {**request_body, "id": "string"} if request_body else {"id": "string"}
                    elif method == HTTPMethod.GET and path == base_path:
                        response_body = {"items": [{"id": "string"}], "total": "int"}
                    elif method == HTTPMethod.DELETE:
                        response_body = {"deleted": "bool"}

                    endpoints.append(APIEndpoint(
                        method=method,
                        path=path,
                        description=desc,
                        request_body=request_body,
                        response_body=response_body,
                        requires_auth=needs_auth,
                    ))
                    seen_methods.add(key)
                break  # Only match the first CRUD keyword per bullet

    # Auth-specific endpoints
    if any(kw in feature_name.lower() for kw in ["auth", "login"]):
        auth_endpoints = [
            (HTTPMethod.POST, "/api/v1/auth/login", "User login",
             {"email": "string", "password": "string"},
             {"access_token": "string", "token_type": "bearer"}, False),
            (HTTPMethod.POST, "/api/v1/auth/register", "User registration",
             {"email": "string", "password": "string", "name": "string"},
             {"id": "string", "email": "string"}, False),
            (HTTPMethod.POST, "/api/v1/auth/logout", "User logout",
             None, {"status": "ok"}, True),
        ]
        lower_bullets = " ".join(bullets).lower()
        if "password reset" in lower_bullets or "forgot password" in lower_bullets:
            auth_endpoints.append(
                (HTTPMethod.POST, "/api/v1/auth/forgot-password", "Request password reset",
                 {"email": "string"}, {"status": "ok"}, False)
            )
            auth_endpoints.append(
                (HTTPMethod.POST, "/api/v1/auth/reset-password", "Reset password with token",
                 {"token": "string", "new_password": "string"}, {"status": "ok"}, False)
            )

        for method, path, desc, req_body, resp_body, auth in auth_endpoints:
            key = (method.value, path)
            if key not in seen_methods:
                endpoints.append(APIEndpoint(
                    method=method, path=path, description=desc,
                    request_body=req_body, response_body=resp_body,
                    requires_auth=auth,
                ))
                seen_methods.add(key)

    # Pagination endpoint if listing is detected
    if any(e.method == HTTPMethod.GET and "{id}" not in e.path for e in endpoints):
        for ep in endpoints:
            if ep.method == HTTPMethod.GET and "{id}" not in ep.path:
                if "total" not in ep.response_body:
                    ep.response_body = {
                        "items": [{"id": "string"}],
                        "total": "int",
                        "page": "int",
                        "page_size": "int",
                    }

    return endpoints


def _infer_request_body(bullets: list[str], entity: str) -> dict[str, Any]:
    """Attempt to infer request body fields from bullet descriptions."""
    fields: dict[str, str] = {}
    field_pattern = re.compile(
        r"\b(?:with|including|has|contains?)\b\s+(.+)", re.IGNORECASE
    )
    direct_field_pattern = re.compile(
        r"(title|name|description|email|password|status|priority|"
        r"due[_ ]?date|start[_ ]?date|end[_ ]?date|category|type|"
        r"content|body|message|subject|url|link|image|avatar|"
        r"phone|address|price|amount|quantity|rating|score|tags?|"
        r"label|color|size|weight|width|height|notes?|comment)",
        re.IGNORECASE,
    )

    for bullet in bullets:
        # Look for "with title, description, ..." patterns
        match = field_pattern.search(bullet)
        if match:
            field_text = match.group(1)
            for field_match in direct_field_pattern.finditer(field_text):
                field_name = field_match.group(1).lower().replace(" ", "_")
                fields[field_name] = _guess_field_type(field_name)

        # Also scan for direct field mentions
        for field_match in direct_field_pattern.finditer(bullet):
            field_name = field_match.group(1).lower().replace(" ", "_")
            if field_name not in fields:
                fields[field_name] = _guess_field_type(field_name)

    if not fields:
        # Fallback: provide a minimal body
        fields = {"name": "string"}

    return fields


def _guess_field_type(field_name: str) -> str:
    """Guess the JSON type of a field from its name."""
    if any(kw in field_name for kw in ["date", "time", "created", "updated"]):
        return "datetime"
    if any(kw in field_name for kw in ["price", "amount", "score", "rating", "weight"]):
        return "number"
    if any(kw in field_name for kw in ["quantity", "count", "size", "width", "height"]):
        return "integer"
    if any(kw in field_name for kw in ["is_", "has_", "active", "enabled", "deleted"]):
        return "boolean"
    if any(kw in field_name for kw in ["tags", "labels", "categories"]):
        return "array"
    if field_name in ("email",):
        return "string (email)"
    if field_name in ("password",):
        return "string (password)"
    if field_name in ("url", "link", "image", "avatar"):
        return "string (url)"
    return "string"


# ---------------------------------------------------------------------------
# Main Parser
# ---------------------------------------------------------------------------

def _extract_project_name(sections: list[_Section], markdown: str) -> str:
    """Extract the project name from the top-level H1 header."""
    all_flat = _all_sections_flat(sections)
    for s in all_flat:
        if s.level == 1:
            # Remove priority markers
            name = _PRIORITY_PATTERN.sub("", s.title).strip()
            return name
    # Fallback: first line that looks like a title
    for line in markdown.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            continue
        if stripped.startswith("# "):
            return stripped.lstrip("# ").strip()
    return "Untitled Project"


def _extract_project_description(sections: list[_Section]) -> str:
    """Extract the project description from the body under the H1 or a 'Description' section."""
    all_flat = _all_sections_flat(sections)
    for s in all_flat:
        if s.level == 1 and s.body:
            return s.body.strip()
    for s in all_flat:
        if "description" in s.title.lower() or "overview" in s.title.lower():
            return s.body.strip()
    return ""


def _find_feature_sections(sections: list[_Section]) -> list[_Section]:
    """Find sections that define features.

    Features are typically H3 sections under a H2 'Features' section, or
    any H2/H3 section that looks like a feature definition.
    """
    all_flat = _all_sections_flat(sections)
    feature_sections: list[_Section] = []

    # Strategy 1: Find explicit "## Features" section and use its children
    for s in all_flat:
        if s.level == 2 and "feature" in s.title.lower():
            if s.children:
                feature_sections.extend(s.children)
            elif s.body:
                # Features might be described as bullets under the header
                feature_sections.append(s)

    # Strategy 2: If no explicit features section, treat H2/H3 sections as features
    if not feature_sections:
        for s in all_flat:
            if s.level in (2, 3) and not _is_meta_section(s.title):
                feature_sections.append(s)

    return feature_sections


def _is_meta_section(title: str) -> bool:
    """Check if a section title is a meta/organizational section, not a feature."""
    meta_keywords = [
        "overview", "description", "introduction", "background",
        "table of contents", "toc", "appendix", "glossary", "references",
        "notes", "assumptions", "constraints", "non-functional",
        "deployment", "infrastructure", "timeline", "milestones",
        "stakeholders", "team", "budget", "revision history",
        "tech stack", "technology", "architecture",
    ]
    lower = title.lower().strip()
    return any(kw in lower for kw in meta_keywords)


def _build_feature(section: _Section) -> Feature:
    """Build a Feature model from a parsed markdown section."""
    title = section.title
    priority = _extract_priority(title)
    # Clean priority marker from name
    name = _PRIORITY_PATTERN.sub("", title).strip()

    bullets = _get_bullets(section.body)
    # Also gather bullets from child sections
    for child in section.children:
        child_bullets = _get_bullets(child.body)
        bullets.extend(child_bullets)

    needs_auth = _requires_auth(name, bullets)
    complexity = _estimate_complexity(bullets, name)
    external_apis = _detect_external_apis(section.body + " " + " ".join(bullets))

    routes = _extract_routes_from_bullets(bullets, name, needs_auth)
    api_endpoints = _extract_api_endpoints_from_bullets(bullets, name, needs_auth)

    # Acceptance criteria: treat bullets as acceptance criteria
    acceptance = [b for b in bullets if b]

    # Dependency detection: look for "depends on", "requires", "after" patterns
    dependencies: list[str] = []
    # Match quoted dependency names first
    dep_quoted_pattern = re.compile(
        r'(?:depends?\s+on|requires?|after|needs?)\s+["\']([^"\']+)["\']',
        re.IGNORECASE,
    )
    # Fallback: unquoted but title-cased dependency names (stop at punctuation/newline)
    dep_unquoted_pattern = re.compile(
        r'(?:depends?\s+on|requires?|after|needs?)\s+["`]?([A-Z][A-Za-z0-9 ]{1,50}?)(?:["`.,;:\n]|$|\s+(?:for|to|in|on|with|and|or|because|since|as|so))',
        re.IGNORECASE,
    )
    full_text = section.body + " " + " ".join(bullets)
    for dep_match in dep_quoted_pattern.finditer(full_text):
        dep_name = dep_match.group(1).strip()
        if dep_name and dep_name not in dependencies:
            dependencies.append(dep_name)
    # Only try unquoted if no quoted matches found
    if not dependencies:
        for dep_match in dep_unquoted_pattern.finditer(full_text):
            dep_name = dep_match.group(1).strip()
            if dep_name and dep_name not in dependencies and len(dep_name) > 2:
                dependencies.append(dep_name)

    return Feature(
        name=name,
        description=section.body.strip() if not bullets else " ".join(bullets[:3]),
        priority=priority,
        dependencies=dependencies,
        complexity=complexity,
        ui_routes=routes,
        api_endpoints=api_endpoints,
        external_apis=external_apis,
        acceptance_criteria=acceptance,
    )


async def _read_file(path: str) -> str:
    """Read a file asynchronously using asyncio.to_thread."""
    file_path = Path(path)
    if not file_path.exists():
        raise FileNotFoundError(f"Requirements file not found: {path}")
    if not file_path.suffix.lower() in (".md", ".markdown", ".txt", ""):
        raise ValueError(f"Expected a markdown file, got: {file_path.suffix}")
    return await asyncio.to_thread(file_path.read_text, "utf-8")


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def parse_requirements(markdown_path: str) -> ParseResult:
    """Parse a markdown requirements document and return a structured ParseResult.

    This is the main entry point for the parser module. It reads a markdown
    file, extracts features, generates architecture and test plans, and
    flags any ambiguities found in the requirements.

    Args:
        markdown_path: Path to the markdown requirements file.

    Returns:
        A ParseResult containing features, architecture, test plan, and
        any ambiguities detected.

    Raises:
        FileNotFoundError: If the markdown file does not exist.
        ValueError: If the file is not a markdown file.
    """
    markdown = await _read_file(markdown_path)
    sections = _parse_sections(markdown)

    # Extract project metadata
    project_name = _extract_project_name(sections, markdown)
    project_description = _extract_project_description(sections)

    # Extract features
    feature_sections = _find_feature_sections(sections)
    features: list[Feature] = []
    for fs in feature_sections:
        feature = _build_feature(fs)
        features.append(feature)

    # Detect ambiguities across the entire document
    ambiguities = _detect_ambiguities(markdown)

    # Check for missing priorities
    features_without_priority = [
        f for f in features
        if _PRIORITY_PATTERN.search(f.name) is None
        and f.priority == Priority.P1  # defaulted, not explicitly set
    ]
    for f in features_without_priority:
        # Only flag if the priority wasn't inferable from keywords either
        lower_name = f.name.lower()
        lower_desc = f.description.lower()
        combined = lower_name + " " + lower_desc
        if not any(kw in combined for kw in ["must", "critical", "essential", "core",
                                               "nice to have", "optional", "bonus", "stretch"]):
            ambiguities.append(
                f"Feature '{f.name}' has no explicit priority; defaulting to P1"
            )

    # Check for features with no clear acceptance criteria
    for f in features:
        if not f.acceptance_criteria:
            ambiguities.append(
                f"Feature '{f.name}' has no acceptance criteria defined"
            )

    # Detect auth requirement globally
    auth_required = any(
        any(kw in f.name.lower() for kw in ["auth", "login", "user"])
        for f in features
    ) or any(
        any(kw in " ".join(f.acceptance_criteria).lower() for kw in _AUTH_KEYWORDS)
        for f in features
    )

    # Generate architecture
    architecture = await generate_architecture(
        features=features,
        project_name=project_name,
        project_description=project_description,
        auth_required=auth_required,
    )

    # Generate test plan
    test_plan = await generate_test_plan(features=features, architecture=architecture)

    return ParseResult(
        features=features,
        architecture=architecture,
        test_plan=test_plan,
        ambiguities=ambiguities,
    )
