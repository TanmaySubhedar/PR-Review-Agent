from pydantic import BaseModel


class CommitInfo(BaseModel):
    sha: str
    message: str
    author: str


class PREvent(BaseModel):
    repo_full_name: str
    pr_number: int
    pr_url: str
    title: str
    description: str = ""
    base_sha: str
    head_sha: str
    base_ref: str
    head_ref: str
    clone_url: str
    changed_files: list[str] = []
    commits: list[CommitInfo] = []
