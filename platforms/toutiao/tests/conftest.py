import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT / "platforms") not in sys.path:
    sys.path.insert(0, str(REPO_ROOT / "platforms"))

SOURCE_POSTS = REPO_ROOT / "source" / "_posts"
CAPABILITIES = REPO_ROOT / "platforms" / "toutiao"

#: The directories inside the repository that the commands write into when
#: they are not told otherwise.  ``platforms/toutiao/outbox/`` holds tracked
#: snapshots; ``platforms/toutiao/out/`` holds the Phase 0 packages the pilot work
#: depends on.  A test that forgets one of the options writes here.
OUTBOX_DIR = REPO_ROOT / "platforms" / "toutiao" / "outbox"
PACKAGES_DIR = REPO_ROOT / "platforms" / "toutiao" / "out"
WRITABLE_IN_THE_REPOSITORY = (OUTBOX_DIR, PACKAGES_DIR)


def _tracked_files(directory: Path):
    """The names of the files in ``directory`` that git tracks.

    ``None`` when git cannot answer -- the check is then skipped rather
    than failed, because "git is missing" is not "the repository is dirty".

    ``-z`` is not optional here.  Without it git quotes every path that
    holds a non-ASCII character and writes the bytes as octal escapes
    (``"platforms/toutiao/outbox/db-logical_decode-postgresql\\351\\207\\217..."``),
    so a file whose name contains Chinese never matches the real name on
    disk -- and a **tracked** file gets reported as untracked.  The
    snapshot names are derived from the article titles, and those are
    Chinese, so this is not a hypothetical.
    """
    try:
        result = subprocess.run(
            [
                "git", "ls-files", "-z", "--",
                str(directory.relative_to(REPO_ROOT)),
            ],
            cwd=str(REPO_ROOT),
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError:
        return None
    if result.returncode != 0:
        return None
    names = set()
    for entry in result.stdout.split(b"\0"):
        if not entry:
            continue
        names.add(Path(entry.decode("utf-8", "surrogateescape")).name)
    return names


@pytest.fixture(scope="session", autouse=True)
def the_repository_is_never_written_to():
    """No test may leave anything behind in the repository.

    Two different checks, because they catch different things:

    - the **outbox** may only hold files git tracks.  A snapshot that a
      test wrote is untracked, and an untracked file there survives the
      session -- so the next run's "before" snapshot already contains it
      and a session-scoped comparison would never see it.  Asking git is
      the only way to notice a leftover from an earlier run.
    - the **packages directory** is compared against the snapshot taken at
      the **start of the session**, not "before and after this test": the
      second kind cannot see what the previous test left behind.  That is
      how a test wrote a package into ``platforms/toutiao/outbox/`` and the old
      per-test comparison still reported everything was fine.
    """
    def snapshot():
        seen = {}
        for directory in WRITABLE_IN_THE_REPOSITORY:
            if directory.is_dir():
                seen[directory] = {p.name for p in directory.iterdir()}
            else:
                seen[directory] = set()
        return seen

    before = snapshot()
    yield

    after = snapshot()
    for directory, names in after.items():
        added = names - before[directory]
        assert not added, (
            "有测试往仓库的 {} 里写了东西：{}".format(
                directory.relative_to(REPO_ROOT), "、".join(sorted(added))
            )
        )

    tracked = _tracked_files(OUTBOX_DIR)
    if tracked is not None:
        untracked = sorted(after[OUTBOX_DIR] - tracked)
        assert not untracked, (
            "platforms/toutiao/outbox/ 里有没被 git 跟踪的文件：{} —— "
            "它们是某次测试留下的，删掉它们".format("、".join(untracked))
        )


@pytest.fixture(autouse=True)
def isolated_credentials(monkeypatch):
    """Keep the developer's own credentials out of every test.

    A real ``TT_CLIENT_ID`` in the developer's shell, or a real
    ``platforms/toutiao/secrets.json``, must never change what a test does -- and
    must never be sent to a test's fake server.  Tests that need
    credentials set their own.
    """
    monkeypatch.delenv("TT_CLIENT_ID", raising=False)
    monkeypatch.delenv("TT_CLIENT_SECRET", raising=False)
    monkeypatch.delenv("TT_ACCESS_TOKEN", raising=False)
    # 站点地址：开发者本机真设的 ``SITE_URL`` 不该漏进头条的测试。
    # （``TT_SOURCE_URL`` 是一个没人读的死变量——全仓只有这一处提到它。）
    monkeypatch.delenv("SITE_URL", raising=False)
    monkeypatch.delenv("TT_NOTIFY", raising=False)
    monkeypatch.delenv("TT_NOTIFY_KEY", raising=False)
    # The scheduling layer's variables: they decide where the snapshot
    # goes, so a leftover one in the developer's shell would change what
    # a test writes.
    monkeypatch.delenv("PUBLISH_OUTBOX_DIR", raising=False)
    monkeypatch.delenv("PUBLISH_REPO", raising=False)
    monkeypatch.delenv("PUBLISH_STATE_DIR", raising=False)


@pytest.fixture(scope="session")
def repo_root() -> Path:
    return REPO_ROOT


@pytest.fixture(scope="session")
def source_posts() -> Path:
    return SOURCE_POSTS


@pytest.fixture(scope="session")
def capabilities() -> Path:
    return CAPABILITIES
