"""Architecture generator for the NC Dev System.

Takes parsed features and produces a complete Architecture model, including
inferred database collections, API contracts, external API definitions,
port allocation, and index recommendations.
"""

from __future__ import annotations

import re
from typing import Any

from .models import (
    APIContract,
    APIEndpoint,
    Architecture,
    Complexity,
    DBCollection,
    ExternalAPI,
    Feature,
    FieldModel,
    HTTPMethod,
    Index,
)


# ---------------------------------------------------------------------------
# Port allocation (from CLAUDE.md)
# ---------------------------------------------------------------------------

DEFAULT_PORT_ALLOCATION: dict[str, int] = {
    "frontend": 23000,
    "backend": 23001,
    "mongodb": 23002,
    "redis": 23003,
    "keycloak": 23004,
    "keycloak_postgres": 23005,
}


# ---------------------------------------------------------------------------
# Field type mapping
# ---------------------------------------------------------------------------

_FIELD_TYPE_MAP: dict[str, str] = {
    "title": "str",
    "name": "str",
    "description": "str",
    "content": "str",
    "body": "str",
    "message": "str",
    "subject": "str",
    "email": "str",
    "password": "str",
    "url": "str",
    "link": "str",
    "image": "str",
    "avatar": "str",
    "phone": "str",
    "address": "str",
    "notes": "str",
    "comment": "str",
    "label": "str",
    "color": "str",
    "status": "str",
    "type": "str",
    "category": "str",
    "priority": "str",
    "price": "float",
    "amount": "float",
    "score": "float",
    "rating": "float",
    "weight": "float",
    "quantity": "int",
    "count": "int",
    "size": "int",
    "width": "int",
    "height": "int",
    "order": "int",
    "position": "int",
    "due_date": "datetime",
    "start_date": "datetime",
    "end_date": "datetime",
    "date": "datetime",
    "created_at": "datetime",
    "updated_at": "datetime",
    "deleted_at": "datetime",
    "is_active": "bool",
    "is_deleted": "bool",
    "is_archived": "bool",
    "enabled": "bool",
    "completed": "bool",
    "tags": "list[str]",
    "labels": "list[str]",
    "categories": "list[str]",
    "attachments": "list[str]",
}


# ---------------------------------------------------------------------------
# External API definitions
# ---------------------------------------------------------------------------

_KNOWN_EXTERNAL_APIS: dict[str, dict[str, Any]] = {
    "stripe": {
        "name": "Stripe",
        "base_url": "https://api.stripe.com/v1",
        "auth_type": "bearer",
        "endpoints": [
            {"method": "POST", "path": "/charges", "description": "Create a charge"},
            {"method": "GET", "path": "/charges/{id}", "description": "Retrieve a charge"},
            {"method": "POST", "path": "/customers", "description": "Create a customer"},
            {"method": "POST", "path": "/payment_intents", "description": "Create payment intent"},
        ],
    },
    "twilio": {
        "name": "Twilio",
        "base_url": "https://api.twilio.com/2010-04-01",
        "auth_type": "basic",
        "endpoints": [
            {"method": "POST", "path": "/Messages.json", "description": "Send SMS"},
        ],
    },
    "sendgrid": {
        "name": "SendGrid",
        "base_url": "https://api.sendgrid.com/v3",
        "auth_type": "bearer",
        "endpoints": [
            {"method": "POST", "path": "/mail/send", "description": "Send email"},
        ],
    },
    "mailgun": {
        "name": "Mailgun",
        "base_url": "https://api.mailgun.net/v3",
        "auth_type": "basic",
        "endpoints": [
            {"method": "POST", "path": "/messages", "description": "Send email"},
        ],
    },
    "openai": {
        "name": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "auth_type": "bearer",
        "endpoints": [
            {"method": "POST", "path": "/chat/completions", "description": "Chat completion"},
            {"method": "POST", "path": "/embeddings", "description": "Create embeddings"},
        ],
    },
    "firebase": {
        "name": "Firebase",
        "base_url": "https://fcm.googleapis.com/fcm",
        "auth_type": "bearer",
        "endpoints": [
            {"method": "POST", "path": "/send", "description": "Send push notification"},
        ],
    },
    "s3": {
        "name": "AWS S3",
        "base_url": "https://s3.amazonaws.com",
        "auth_type": "aws_signature",
        "endpoints": [
            {"method": "PUT", "path": "/{bucket}/{key}", "description": "Upload object"},
            {"method": "GET", "path": "/{bucket}/{key}", "description": "Get object"},
            {"method": "DELETE", "path": "/{bucket}/{key}", "description": "Delete object"},
        ],
    },
    "cloudinary": {
        "name": "Cloudinary",
        "base_url": "https://api.cloudinary.com/v1_1",
        "auth_type": "basic",
        "endpoints": [
            {"method": "POST", "path": "/image/upload", "description": "Upload image"},
            {"method": "DELETE", "path": "/resources/image/upload", "description": "Delete image"},
        ],
    },
    "algolia": {
        "name": "Algolia",
        "base_url": "https://{app-id}-dsn.algolia.net/1",
        "auth_type": "api_key",
        "endpoints": [
            {"method": "POST", "path": "/indexes/{index}/query", "description": "Search"},
            {"method": "PUT", "path": "/indexes/{index}/{objectID}", "description": "Add/update object"},
        ],
    },
    "slack": {
        "name": "Slack",
        "base_url": "https://slack.com/api",
        "auth_type": "bearer",
        "endpoints": [
            {"method": "POST", "path": "/chat.postMessage", "description": "Send message"},
            {"method": "GET", "path": "/conversations.list", "description": "List channels"},
        ],
    },
    "github": {
        "name": "GitHub",
        "base_url": "https://api.github.com",
        "auth_type": "bearer",
        "endpoints": [
            {"method": "GET", "path": "/repos/{owner}/{repo}", "description": "Get repository"},
            {"method": "POST", "path": "/repos/{owner}/{repo}/issues", "description": "Create issue"},
        ],
    },
    "paypal": {
        "name": "PayPal",
        "base_url": "https://api-m.paypal.com/v2",
        "auth_type": "bearer",
        "endpoints": [
            {"method": "POST", "path": "/checkout/orders", "description": "Create order"},
            {"method": "POST", "path": "/checkout/orders/{id}/capture", "description": "Capture payment"},
        ],
    },
    "sentry": {
        "name": "Sentry",
        "base_url": "https://sentry.io/api/0",
        "auth_type": "bearer",
        "endpoints": [
            {"method": "POST", "path": "/store/", "description": "Report error"},
        ],
    },
    "google maps": {
        "name": "Google Maps",
        "base_url": "https://maps.googleapis.com/maps/api",
        "auth_type": "api_key",
        "endpoints": [
            {"method": "GET", "path": "/geocode/json", "description": "Geocode address"},
            {"method": "GET", "path": "/place/nearbysearch/json", "description": "Nearby search"},
        ],
    },
    "elasticsearch": {
        "name": "Elasticsearch",
        "base_url": "http://localhost:9200",
        "auth_type": "basic",
        "endpoints": [
            {"method": "POST", "path": "/{index}/_search", "description": "Search documents"},
            {"method": "PUT", "path": "/{index}/_doc/{id}", "description": "Index document"},
        ],
    },
}


# ---------------------------------------------------------------------------
# Inference helpers
# ---------------------------------------------------------------------------

def _pluralize(word: str) -> str:
    """Simple English pluralization."""
    if word.endswith("y") and not word.endswith("ey"):
        return word[:-1] + "ies"
    if word.endswith(("s", "sh", "ch", "x", "z")):
        return word + "es"
    return word + "s"


def _singularize(word: str) -> str:
    """Simple English singularization."""
    if word.endswith("ies") and len(word) > 4:
        return word[:-3] + "y"
    if word.endswith("ses") or word.endswith("xes") or word.endswith("zes"):
        return word[:-2]
    if word.endswith("shes") or word.endswith("ches"):
        return word[:-2]
    if word.endswith("s") and not word.endswith("ss"):
        return word[:-1]
    return word


def _infer_entity_name(feature_name: str) -> str:
    """Extract the primary entity name from a feature name."""
    cleaned = re.sub(
        r"\b(crud|management|system|module|feature|dashboard|"
        r"authentication|authorization|settings|configuration)\b",
        "",
        feature_name,
        flags=re.IGNORECASE,
    ).strip()
    words = [w.lower() for w in cleaned.split() if len(w) > 1]
    if not words:
        words = [feature_name.lower().split()[0]] if feature_name.split() else ["item"]
    entity = words[0].rstrip("s")
    return _pluralize(entity)


def _extract_fields_from_feature(feature: Feature) -> list[FieldModel]:
    """Infer collection fields from a feature's endpoints and acceptance criteria."""
    fields: list[FieldModel] = []
    seen_names: set[str] = set()

    # Always include _id and timestamps
    standard_fields = [
        FieldModel(name="_id", type="ObjectId", required=True, description="MongoDB document ID"),
        FieldModel(name="created_at", type="datetime", required=True, description="Creation timestamp"),
        FieldModel(name="updated_at", type="datetime", required=True, description="Last update timestamp"),
    ]
    for sf in standard_fields:
        fields.append(sf)
        seen_names.add(sf.name)

    # Fields that are transient (request-only) and should NOT be stored in collections
    _transient_fields = {
        "token", "access_token", "refresh_token", "new_password",
        "confirm_password", "old_password", "password_confirmation",
        "token_type", "grant_type", "redirect_uri", "code",
    }

    # Extract fields from request bodies of POST/PUT endpoints
    for endpoint in feature.api_endpoints:
        if endpoint.request_body:
            for field_name, field_type_hint in endpoint.request_body.items():
                if field_name in seen_names:
                    continue
                if field_name in _transient_fields:
                    continue
                mongo_type = _map_to_mongo_type(field_name, field_type_hint)
                fields.append(FieldModel(
                    name=field_name,
                    type=mongo_type,
                    required=True,
                    description=f"{field_name} field",
                ))
                seen_names.add(field_name)

    # Extract fields from acceptance criteria mentions
    field_pattern = re.compile(
        r"\b(title|name|description|email|password|status|priority|"
        r"due[_ ]?date|start[_ ]?date|end[_ ]?date|category|type|"
        r"content|body|message|subject|url|link|image|avatar|"
        r"phone|address|price|amount|quantity|rating|score|tags?|"
        r"label|color|size|weight|width|height|notes?|comment|"
        r"assigned[_ ]?to|owner|user[_ ]?id|author|completed|archived)\b",
        re.IGNORECASE,
    )
    for criterion in feature.acceptance_criteria:
        for match in field_pattern.finditer(criterion):
            field_name = match.group(1).lower().replace(" ", "_")
            if field_name in seen_names:
                continue
            field_type = _FIELD_TYPE_MAP.get(field_name, "str")
            fields.append(FieldModel(
                name=field_name,
                type=field_type,
                required=field_name in ("title", "name", "email"),
                description=f"Extracted from: {criterion[:80]}",
            ))
            seen_names.add(field_name)

    # Add user_id for auth-required features
    if any(r.requires_auth for r in feature.ui_routes) and "user_id" not in seen_names:
        fields.append(FieldModel(
            name="user_id", type="ObjectId", required=True,
            description="Reference to the owning user",
        ))
        seen_names.add("user_id")

    # Add soft-delete field if mentioned
    criteria_text = " ".join(feature.acceptance_criteria).lower()
    if "soft delete" in criteria_text and "is_deleted" not in seen_names:
        fields.append(FieldModel(
            name="is_deleted", type="bool", required=True,
            description="Soft delete flag", default=False,
        ))
        fields.append(FieldModel(
            name="deleted_at", type="datetime", required=False,
            description="Deletion timestamp",
        ))

    return fields


def _map_to_mongo_type(field_name: str, type_hint: str) -> str:
    """Map a JSON schema type hint to a MongoDB-friendly type string."""
    hint_lower = type_hint.lower()
    if "date" in hint_lower or "time" in hint_lower:
        return "datetime"
    if hint_lower in ("int", "integer"):
        return "int"
    if hint_lower in ("float", "number", "decimal"):
        return "float"
    if hint_lower in ("bool", "boolean"):
        return "bool"
    if hint_lower.startswith("array") or hint_lower.startswith("list"):
        return "list"
    if hint_lower in ("object", "dict"):
        return "dict"

    # Fall back to name-based inference
    return _FIELD_TYPE_MAP.get(field_name, "str")


def _infer_indexes(collection_name: str, fields: list[FieldModel], feature: Feature) -> list[Index]:
    """Infer useful database indexes for a collection."""
    indexes: list[Index] = []
    field_names = {f.name for f in fields}

    # Email uniqueness index
    if "email" in field_names:
        indexes.append(Index(fields=["email"], unique=True))

    # User ID index for filtering
    if "user_id" in field_names:
        indexes.append(Index(fields=["user_id"], unique=False))

    # Created at index for sorting
    if "created_at" in field_names:
        indexes.append(Index(fields=["created_at"], unique=False))

    # Status + user_id compound index for filtered queries
    if "status" in field_names and "user_id" in field_names:
        indexes.append(Index(fields=["user_id", "status"], unique=False))

    # Name index if exists (often used for search)
    if "name" in field_names:
        indexes.append(Index(fields=["name"], unique=False))

    # Title index (often used for search)
    if "title" in field_names:
        indexes.append(Index(fields=["title"], unique=False))

    # Soft delete: compound index for active records
    if "is_deleted" in field_names:
        indexes.append(Index(fields=["is_deleted"], unique=False))
        if "user_id" in field_names:
            indexes.append(Index(fields=["user_id", "is_deleted"], unique=False))

    # Due date index for task-like entities
    if "due_date" in field_names:
        indexes.append(Index(fields=["due_date"], unique=False))

    # Priority index
    if "priority" in field_names:
        indexes.append(Index(fields=["priority"], unique=False))

    # Category/type index
    if "category" in field_names:
        indexes.append(Index(fields=["category"], unique=False))

    # Detect search/filter patterns from acceptance criteria
    criteria_text = " ".join(feature.acceptance_criteria).lower()
    if "search" in criteria_text or "filter" in criteria_text:
        # Text search index on common searchable fields
        searchable = [f.name for f in fields if f.type == "str" and f.name in ("title", "name", "description", "content")]
        if searchable:
            indexes.append(Index(fields=searchable, unique=False))

    # Deduplicate indexes
    seen: set[str] = set()
    unique_indexes: list[Index] = []
    for idx in indexes:
        key = "|".join(sorted(idx.fields)) + f"|{idx.unique}"
        if key not in seen:
            unique_indexes.append(idx)
            seen.add(key)

    return unique_indexes


def _build_db_collection(feature: Feature) -> DBCollection | None:
    """Build a DBCollection from a feature, if the feature implies data persistence."""
    # Auth features use the dedicated _build_users_collection() instead
    auth_keywords = {"auth", "login", "user authentication", "sign in", "signup"}
    if any(kw in feature.name.lower() for kw in auth_keywords):
        return None  # Handled separately via _build_users_collection()

    # Skip features that don't seem to need a collection
    has_crud = any(
        ep.method in (HTTPMethod.POST, HTTPMethod.PUT, HTTPMethod.DELETE, HTTPMethod.PATCH)
        for ep in feature.api_endpoints
    )
    if not has_crud and not feature.api_endpoints:
        return None

    entity_name = _infer_entity_name(feature.name)
    fields = _extract_fields_from_feature(feature)
    indexes = _infer_indexes(entity_name, fields, feature)

    return DBCollection(
        name=entity_name,
        fields=fields,
        indexes=indexes,
    )


def _build_api_contracts(features: list[Feature]) -> list[APIContract]:
    """Group all API endpoints into contracts organized by base path."""
    path_groups: dict[str, list[APIEndpoint]] = {}

    for feature in features:
        for endpoint in feature.api_endpoints:
            # Extract the base path: /api/v1/{resource}
            parts = endpoint.path.strip("/").split("/")
            if len(parts) >= 3:
                base = "/" + "/".join(parts[:3])
            elif len(parts) >= 2:
                base = "/" + "/".join(parts[:2])
            else:
                base = "/" + parts[0] if parts else "/api"

            if base not in path_groups:
                path_groups[base] = []
            # Avoid exact duplicates within the same group
            existing_keys = {(e.method, e.path) for e in path_groups[base]}
            if (endpoint.method, endpoint.path) not in existing_keys:
                path_groups[base].append(endpoint)

    contracts: list[APIContract] = []
    for base_path in sorted(path_groups.keys()):
        contracts.append(APIContract(
            base_path=base_path,
            endpoints=path_groups[base_path],
        ))

    return contracts


def _resolve_external_apis(features: list[Feature]) -> list[ExternalAPI]:
    """Build ExternalAPI definitions from features' external_apis references."""
    seen: set[str] = set()
    external_apis: list[ExternalAPI] = []

    for feature in features:
        for api_name in feature.external_apis:
            lower_name = api_name.lower().strip()
            if lower_name in seen:
                continue
            seen.add(lower_name)

            if lower_name in _KNOWN_EXTERNAL_APIS:
                info = _KNOWN_EXTERNAL_APIS[lower_name]
                external_apis.append(ExternalAPI(
                    name=info["name"],
                    base_url=info["base_url"],
                    endpoints=info["endpoints"],
                    auth_type=info.get("auth_type"),
                ))
            else:
                # Unknown external API -- create a stub definition
                external_apis.append(ExternalAPI(
                    name=api_name.title(),
                    base_url=f"https://api.{lower_name.replace(' ', '')}.com",
                    endpoints=[{"method": "GET", "path": "/", "description": f"{api_name} API"}],
                    auth_type="api_key",
                ))

    return external_apis


def _determine_auth_required(features: list[Feature], explicit_auth: bool) -> bool:
    """Determine if the project needs authentication infrastructure."""
    if explicit_auth:
        return True
    auth_keywords = {"auth", "login", "user", "session", "permission", "role"}
    for feature in features:
        name_words = set(feature.name.lower().split())
        if name_words & auth_keywords:
            return True
        if any(r.requires_auth for r in feature.ui_routes):
            return True
    return False


# ---------------------------------------------------------------------------
# Users collection builder
# ---------------------------------------------------------------------------

def _build_users_collection() -> DBCollection:
    """Build a standard users collection for auth-enabled projects."""
    return DBCollection(
        name="users",
        fields=[
            FieldModel(name="_id", type="ObjectId", required=True, description="MongoDB document ID"),
            FieldModel(name="email", type="str", required=True, description="User email address"),
            FieldModel(name="password_hash", type="str", required=True, description="Hashed password"),
            FieldModel(name="name", type="str", required=True, description="Display name"),
            FieldModel(name="is_active", type="bool", required=True, description="Account active flag", default=True),
            FieldModel(name="roles", type="list[str]", required=True, description="User roles", default=[]),
            FieldModel(name="created_at", type="datetime", required=True, description="Account creation timestamp"),
            FieldModel(name="updated_at", type="datetime", required=True, description="Last update timestamp"),
            FieldModel(name="last_login", type="datetime", required=False, description="Last login timestamp"),
        ],
        indexes=[
            Index(fields=["email"], unique=True),
            Index(fields=["is_active"], unique=False),
            Index(fields=["created_at"], unique=False),
        ],
    )


# ---------------------------------------------------------------------------
# Health endpoints
# ---------------------------------------------------------------------------

def _health_contract() -> APIContract:
    """Generate the mandatory health check API contract."""
    return APIContract(
        base_path="/api/v1/health",
        endpoints=[
            APIEndpoint(
                method=HTTPMethod.GET,
                path="/api/v1/health",
                description="Basic health check",
                response_body={"status": "ok", "version": "string"},
                requires_auth=False,
            ),
            APIEndpoint(
                method=HTTPMethod.GET,
                path="/api/v1/health/ready",
                description="Readiness check with database ping",
                response_body={"status": "ok", "database": "connected"},
                requires_auth=False,
            ),
        ],
    )


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

async def generate_architecture(
    features: list[Feature],
    project_name: str,
    project_description: str = "",
    auth_required: bool = False,
) -> Architecture:
    """Generate a complete Architecture from a list of parsed features.

    This function:
    - Infers MongoDB collections from CRUD features
    - Groups API endpoints into contracts
    - Resolves external API definitions
    - Determines authentication requirements
    - Sets port allocation per CLAUDE.md spec

    Args:
        features: List of parsed Feature models.
        project_name: Name of the project.
        project_description: Optional project description.
        auth_required: Whether auth was explicitly detected.

    Returns:
        A fully populated Architecture model.
    """
    # Build DB collections
    collections: list[DBCollection] = []
    collection_names: set[str] = set()

    for feature in features:
        coll = _build_db_collection(feature)
        if coll and coll.name not in collection_names:
            collections.append(coll)
            collection_names.add(coll.name)

    # Auth: ensure users collection exists
    needs_auth = _determine_auth_required(features, auth_required)
    if needs_auth and "users" not in collection_names:
        collections.insert(0, _build_users_collection())
        collection_names.add("users")

    # Sessions collection for auth
    if needs_auth and "sessions" not in collection_names:
        collections.append(DBCollection(
            name="sessions",
            fields=[
                FieldModel(name="_id", type="ObjectId", required=True, description="Session ID"),
                FieldModel(name="user_id", type="ObjectId", required=True, description="User reference"),
                FieldModel(name="token", type="str", required=True, description="Session token"),
                FieldModel(name="expires_at", type="datetime", required=True, description="Expiry timestamp"),
                FieldModel(name="created_at", type="datetime", required=True, description="Creation timestamp"),
            ],
            indexes=[
                Index(fields=["token"], unique=True),
                Index(fields=["user_id"], unique=False),
                Index(fields=["expires_at"], unique=False),
            ],
        ))

    # Build API contracts
    api_contracts = _build_api_contracts(features)

    # Prepend health check contract
    api_contracts.insert(0, _health_contract())

    # Resolve external APIs
    external_apis = _resolve_external_apis(features)

    # Port allocation
    port_allocation = dict(DEFAULT_PORT_ALLOCATION)
    if not needs_auth:
        # Remove keycloak ports if auth not needed
        port_allocation.pop("keycloak", None)
        port_allocation.pop("keycloak_postgres", None)

    return Architecture(
        project_name=project_name,
        description=project_description,
        features=features,
        db_collections=collections,
        api_contracts=api_contracts,
        external_apis=external_apis,
        auth_required=needs_auth,
        port_allocation=port_allocation,
    )
