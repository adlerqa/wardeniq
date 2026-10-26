"""Repository-path / owner / ref validation for the GitHub and GitLab clients and the
paths an LLM may propose for Start Developing."""
import coverage as cov
import github
import gitlab
import pytest

from conftest import FakeLLM


@pytest.mark.parametrize("bad", [
    "../collaborators/x", "src/../../x", "/etc/passwd", "C:/x.py", "a\\..\\b",
    ".github/workflows/ci.yml", ".GitHub/workflows/x.yml", "src/.git/config",
    "a\x00b.py", "a\nb.py", "", ".", "./", ".gitlab-ci.yml",
])
def test_safe_repo_path_rejects(bad):
    assert github.safe_repo_path(bad) is None


@pytest.mark.parametrize("good,expected", [
    ("src/app.py", "src/app.py"), ("src//pkg/mod.py", "src/pkg/mod.py"),
    ("docs/.well-known/x.txt", "docs/.well-known/x.txt"), ("src\\win.py", "src/win.py"),
])
def test_safe_repo_path_accepts(good, expected):
    assert github.safe_repo_path(good) == expected


def test_generated_code_drops_unsafe_paths():
    llm = FakeLLM(response={"files": [
        {"path": "../../collaborators/bob", "content": "x"},
        {"path": ".github/workflows/x.yml", "content": "x"},
        {"path": "/src/ok.py", "content": "print(1)"},
        {"path": "src/ok2.py", "content": "print(2)"},
    ]})
    out = cov.generate_feature_code(llm, "python", "F", "req", [])
    assert [f["path"] for f in out["files"]] == ["src/ok2.py"]


class _Recorder:
    def __init__(self):
        self.urls = []

    def __call__(self, url, *a, **kw):
        self.urls.append(url)

        class R:
            status_code = 200

            def raise_for_status(self):
                pass

            def json(self):
                return {"object": {"sha": "abc"}}
        return R()


def test_put_file_refuses_unsafe_path_and_quotes_segments(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(github.httpx, "put", rec)
    gh = github.GitHub("t")
    with pytest.raises(ValueError):
        gh.put_file("o", "n", "../../collaborators/eve", "x", "m", "main")
    with pytest.raises(ValueError):
        gh.put_file("o", "n", ".github/workflows/a.yml", "x", "m", "main")
    assert rec.urls == []
    gh.put_file("o", "n", "src/a b#?.py", "x", "m", "main")
    assert rec.urls == ["https://api.github.com/repos/o/n/contents/src/a%20b%23%3F.py"]


@pytest.mark.parametrize("owner,name", [
    ("o/../x", "n"), ("o", ".."), ("o", "n/../../user"), ("", "n"), ("o", "n?x=1"),
    ("-o", "n"), ("o", "n\n"),
])
def test_owner_name_validated(owner, name, monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(github.httpx, "get", rec)
    with pytest.raises(ValueError):
        github.GitHub("t").get_repo(owner, name)
    assert rec.urls == []


@pytest.mark.parametrize("ref", ["../x", "a..b", "a b", "a~1", "-x", "x.lock", "a/", "a\x01", "a?b"])
def test_branch_validated(ref, monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(github.httpx, "get", rec)
    with pytest.raises(ValueError):
        github.GitHub("t").branch_sha("o", "n", ref)
    assert rec.urls == []


def test_valid_branch_with_slash_is_allowed(monkeypatch):
    rec = _Recorder()
    monkeypatch.setattr(github.httpx, "get", rec)
    assert github.GitHub("t").branch_sha("o", "n.js", "feature/x-1") == "abc"
    assert rec.urls == ["https://api.github.com/repos/o/n.js/git/ref/heads/feature/x-1"]


def test_parse_repo_url_validates():
    assert github.parse_repo_url("https://github.com/acme/widget.git") == ("acme", "widget")
    with pytest.raises(ValueError):
        github.parse_repo_url("acme/../../user")


@pytest.mark.parametrize("bad", ["group/../x", "group//x", "x", "g/p?x", "g/p\n", "g/./p"])
def test_gitlab_project_path_validated(bad):
    with pytest.raises(ValueError):
        gitlab.validate_project_path(bad)
    with pytest.raises(ValueError):
        gitlab.GitLab("t").list_webhooks(bad)


def test_gitlab_project_path_ok():
    assert gitlab.validate_project_path("group/sub.group/my-project") == "group/sub.group/my-project"
