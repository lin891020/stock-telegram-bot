import base64
import json
import requests
from bot.config import GITHUB_TOKEN, GITHUB_REPO

_PROFILE_PATH = "profile.json"
_HEADERS = {
    "Authorization": f"token {GITHUB_TOKEN}",
    "Accept": "application/vnd.github.v3+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

def _api_url() -> str:
    return f"https://api.github.com/repos/{GITHUB_REPO}/contents/{_PROFILE_PATH}"

def read_profile() -> dict:
    """Read user profile JSON from GitHub. Returns {} if file doesn't exist."""
    resp = requests.get(_api_url(), headers=_HEADERS, timeout=10)
    if resp.status_code == 404:
        return {}
    resp.raise_for_status()
    raw = base64.b64decode(resp.json()["content"]).decode()
    return json.loads(raw)

def write_profile(data: dict) -> None:
    """Write user profile JSON to GitHub, creating or updating the file."""
    url = _api_url()
    get_resp = requests.get(url, headers=_HEADERS, timeout=10)
    sha = get_resp.json().get("sha") if get_resp.status_code == 200 else None

    encoded = base64.b64encode(
        json.dumps(data, indent=2, ensure_ascii=False).encode()
    ).decode()

    payload: dict = {"message": "Update user profile", "content": encoded}
    if sha:
        payload["sha"] = sha

    requests.put(url, headers=_HEADERS, json=payload, timeout=10).raise_for_status()
