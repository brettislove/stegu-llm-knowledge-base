"""
Thin wrapper around Microsoft Graph's /drive endpoints, used by file_tools.py
as the storage backend in place of local disk.

Auth: client-credentials flow (app-only), targeting one fixed drive
(the business OneDrive of DRIVE_USER). Token is cached and refreshed
automatically.

Large-file handling: Graph's simple `PUT .../content` upload rejects
anything over ~4MB (some docs say up to 4MB works, above that returns
400/413). Any write above LARGE_FILE_THRESHOLD_BYTES goes through an
upload session (chunked PUT) instead. This matters here specifically
because migrated source files run up to ~50MB.
"""

import re
import time
import requests
from typing import List, Optional

GRAPH_BASE = "https://graph.microsoft.com/v1.0"

# OneDrive-illegal characters in file/folder names: " * : < > ? / \ |
# plus leading/trailing spaces and periods, plus a handful of reserved
# Windows device names that OneDrive also rejects.
_ILLEGAL_CHARS_RE = re.compile(r'["*:<>?/\\|]')
_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *{f"COM{i}" for i in range(1, 10)},
    *{f"LPT{i}" for i in range(1, 10)},
}


def sanitize_filename(name: str) -> str:
    """Rewrites `name` so it's safe to use as a OneDrive file/folder name.
    Replaces illegal characters with '_', strips leading/trailing spaces
    and dots, and disambiguates reserved Windows device names. Falls back
    to 'untitled' if the result would be empty."""
    name = _ILLEGAL_CHARS_RE.sub("_", name)
    name = name.strip(" .")
    if not name:
        return "untitled"
    if name.upper() in _RESERVED_NAMES:
        name = f"_{name}"
    return name


LARGE_FILE_THRESHOLD_BYTES = 4 * 1024 * 1024  # 4MB — Graph's simple-upload ceiling
UPLOAD_CHUNK_SIZE = 5 * 1024 * 1024  # must be a multiple of 320 KiB; 5MB is safely so


class GraphError(RuntimeError):
    """Wraps a non-2xx Graph response with status + body for easier debugging."""

    def __init__(self, resp: requests.Response):
        self.status_code = resp.status_code
        self.body = resp.text
        super().__init__(f"Graph API error {resp.status_code}: {resp.text[:500]}")


class GraphNotFound(GraphError):
    """Raised specifically for 404s so file_tools.py can translate these
    into FileNotFoundError without string-matching response bodies."""

    pass


def _raise_for_status(resp: requests.Response):
    if resp.ok:
        return
    if resp.status_code == 404:
        raise GraphNotFound(resp)
    raise GraphError(resp)


class GraphClient:
    def __init__(
        self, tenant_id: str, client_id: str, client_secret: str, drive_user: str
    ):
        self.tenant_id = tenant_id
        self.client_id = client_id
        self.client_secret = client_secret
        self.drive_user = drive_user
        self._token: Optional[str] = None
        self._token_expiry: float = 0

    # ---- auth ----

    def _get_token(self) -> str:
        if self._token and time.time() < self._token_expiry - 60:
            return self._token
        resp = requests.post(
            f"https://login.microsoftonline.com/{self.tenant_id}/oauth2/v2.0/token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": "https://graph.microsoft.com/.default",
                "grant_type": "client_credentials",
            },
            timeout=30,
        )
        resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        self._token_expiry = time.time() + data["expires_in"]
        return self._token

    def _headers(self, extra: Optional[dict] = None) -> dict:
        h = {"Authorization": f"Bearer {self._get_token()}"}
        if extra:
            h.update(extra)
        return h

    def _drive_base(self) -> str:
        return f"{GRAPH_BASE}/users/{self.drive_user}/drive"

    def _item_url(self, path: str) -> str:
        """URL for a specific item by path, e.g. '.../root:/wiki/foo.md:'"""
        path = path.strip("/")
        if not path:
            return f"{self._drive_base()}/root"
        return f"{self._drive_base()}/root:/{path}:"

    # ---- reads ----

    def item_metadata(self, path: str) -> Optional[dict]:
        """Returns metadata dict, or None if the item doesn't exist."""
        resp = requests.get(self._item_url(path), headers=self._headers(), timeout=30)
        if resp.status_code == 404:
            return None
        _raise_for_status(resp)
        return resp.json()

    def exists(self, path: str) -> bool:
        return self.item_metadata(path) is not None

    def list_children(self, path: str = "") -> List[dict]:
        """Non-recursive listing of one folder. Returns [] if the folder
        doesn't exist (matches file_tools.py's existing 'not found -> []'
        behavior for list_files/list_dirs)."""
        url = (
            f"{self._item_url(path)}/children"
            if path
            else f"{self._drive_base()}/root/children"
        )
        items = []
        resp = requests.get(url, headers=self._headers(), timeout=30)
        if resp.status_code == 404:
            return []
        _raise_for_status(resp)
        data = resp.json()
        items.extend(data.get("value", []))
        # Graph paginates; follow @odata.nextLink until exhausted
        next_link = data.get("@odata.nextLink")
        while next_link:
            resp = requests.get(next_link, headers=self._headers(), timeout=30)
            _raise_for_status(resp)
            data = resp.json()
            items.extend(data.get("value", []))
            next_link = data.get("@odata.nextLink")
        return items

    def list_all_files_recursive(
        self, path: str = "", name_filter: Optional[str] = None
    ) -> List[dict]:
        """Walks the tree under `path`, returning metadata dicts for every
        file (not folder). Used by list_files/grep, which today use
        Path.rglob('*.md') against the whole tree. `name_filter` is a
        suffix check (e.g. '.md') applied before recursing into cost of
        reading file content."""
        results = []
        stack = [path]
        while stack:
            current = stack.pop()
            for child in self.list_children(current):
                child_path = f"{current}/{child['name']}" if current else child["name"]
                if "folder" in child:
                    stack.append(child_path)
                elif "file" in child:
                    if name_filter is None or child["name"].endswith(name_filter):
                        child["_path"] = child_path  # stash resolved relative path
                        results.append(child)
        return results

    def read_file(self, path: str) -> bytes:
        resp = requests.get(
            f"{self._item_url(path)}/content", headers=self._headers(), timeout=60
        )
        _raise_for_status(resp)
        return resp.content

    # ---- writes ----

    def write_file(self, path: str, content: bytes) -> dict:
        """Writes content to `path`, creating parent folders implicitly
        (Graph does NOT auto-create intermediate folders on PUT the way
        local mkdir(parents=True) does, so callers must ensure_folder()
        first — file_tools.py handles this, mirroring the old
        path.parent.mkdir(parents=True, exist_ok=True))."""
        if len(content) > LARGE_FILE_THRESHOLD_BYTES:
            return self._write_large_file(path, content)
        resp = requests.put(
            f"{self._item_url(path)}/content",
            headers=self._headers({"Content-Type": "application/octet-stream"}),
            data=content,
            timeout=60,
        )
        _raise_for_status(resp)
        return resp.json()

    def _write_large_file(self, path: str, content: bytes) -> dict:
        """Chunked upload via an upload session, required above ~4MB.
        Each chunk must be a multiple of 320 KiB except the final chunk."""
        path = path.strip("/")
        session_resp = requests.post(
            f"{self._item_url(path)}/createUploadSession",
            headers=self._headers(),
            json={"item": {"@microsoft.graph.conflictBehavior": "replace"}},
            timeout=30,
        )
        _raise_for_status(session_resp)
        upload_url = session_resp.json()["uploadUrl"]

        total = len(content)
        result = None
        for start in range(0, total, UPLOAD_CHUNK_SIZE):
            end = min(start + UPLOAD_CHUNK_SIZE, total)
            chunk = content[start:end]
            # NOTE: no Authorization header on upload-session PUTs — the
            # session URL itself is pre-authorized.
            resp = requests.put(
                upload_url,
                headers={
                    "Content-Length": str(len(chunk)),
                    "Content-Range": f"bytes {start}-{end - 1}/{total}",
                },
                data=chunk,
                timeout=120,
            )
            if resp.status_code not in (200, 201, 202):
                _raise_for_status(resp)
            if resp.status_code in (200, 201):
                result = resp.json()
        return result or {}

    def ensure_folder(self, path: str) -> dict:
        """Idempotently ensures every folder in `path` exists, creating
        any missing segments. Mirrors Path.mkdir(parents=True, exist_ok=True)."""
        path = path.strip("/")
        if not path:
            return {}
        parts = path.split("/")
        current = ""
        result = {}
        for part in parts:
            parent = current
            existing = self.item_metadata(f"{current}/{part}" if current else part)
            if existing is None:
                url = (
                    f"{self._item_url(parent)}/children"
                    if parent
                    else f"{self._drive_base()}/root/children"
                )
                resp = requests.post(
                    url,
                    headers=self._headers(),
                    json={
                        "name": part,
                        "folder": {},
                        "@microsoft.graph.conflictBehavior": "replace",
                    },
                    timeout=30,
                )
                _raise_for_status(resp)
                result = resp.json()
            else:
                result = existing
            current = f"{current}/{part}" if current else part
        return result

    def delete_item(self, path: str) -> None:
        resp = requests.delete(
            self._item_url(path), headers=self._headers(), timeout=30
        )
        if resp.status_code == 404:
            raise GraphNotFound(resp)
        _raise_for_status(resp)

    def move_item(
        self, path: str, new_parent_path: str, new_name: Optional[str] = None
    ) -> dict:
        """Moves an item to a new parent folder (by path), optionally
        renaming it in the same call. new_parent_path='' means root.

        The destination parent folder must already exist — this method
        does not create it. Callers (file_tools.py's move_file/delete_file)
        call ensure_folder() on the destination before calling this."""
        parent_meta = (
            self.item_metadata(new_parent_path)
            if new_parent_path
            else self.item_metadata("")
        )
        if parent_meta is None:
            raise FileNotFoundError(
                f"move_item destination folder does not exist: {new_parent_path!r} "
                f"(call ensure_folder() first)"
            )
        payload = {"parentReference": {"id": parent_meta["id"]}}
        if new_name:
            payload["name"] = new_name
        resp = requests.patch(
            self._item_url(path),
            headers=self._headers({"Content-Type": "application/json"}),
            json=payload,
            timeout=30,
        )
        _raise_for_status(resp)
        return resp.json()

    def rename_item(self, path: str, new_name: str) -> dict:
        resp = requests.patch(
            self._item_url(path),
            headers=self._headers({"Content-Type": "application/json"}),
            json={"name": new_name},
            timeout=30,
        )
        _raise_for_status(resp)
        return resp.json()


# gc = GraphClient(
#     tenant_id="2611c644-8735-4385-8334-712801f70262",
#     client_id="7d12905a-07ac-4ed2-befe-ac7f37bd410f",
#     client_secret="***REDACTED-AZURE-SECRET***",
#     drive_user="admin@stegu.cz",
# )
# print(gc.list_children())  # should list root
# gc.create_folder("", "wiki")  # create /wiki/
# gc.write_file("wiki/test.md", b"# hi")  # write a test file
# print(gc.read_file("wiki/test.md"))  # read it back
# gc.delete_item("wiki/test.md")  # clean up
