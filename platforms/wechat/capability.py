"""Read the WeChat capability declaration.

Only the ``[exit]`` section is read here.  The **meaning** of the four
exit codes is defined by the contract layer
(``publish/publishkit/exit_codes.py``); this adapter merely reads the
table its own declaration carries -- the seam is the file, not an import
(spec §11.1).

The declaration is external input, so it is validated strictly: a missing
section, a missing key, an unknown key or a value that is not an integer
raises ``ValueError`` naming the offending field.
"""

from __future__ import annotations

import tomllib
from pathlib import Path

__all__ = ["default_capability_path", "load_exit_codes"]

#: The four keys of the ``[exit]`` section -- the vocabulary of the exit
#: codes.  The contract layer defines it; this reader only knows the four
#: names.
_EXIT_KEYS = ("ok", "usage", "precondition", "failed")


def default_capability_path() -> Path:
    """The declaration shipped with the repository.

    It lives next to this module -- the adapter and its declaration are
    one thing.
    """
    return Path(__file__).resolve().parent / "capability.toml"


def load_exit_codes(path: Path) -> dict[str, int]:
    """Read the ``[exit]`` section of one capability declaration."""
    path = Path(path)
    with path.open("rb") as handle:
        data = tomllib.load(handle)

    table = data.get("exit")
    if not isinstance(table, dict):
        raise ValueError("能力模型缺少字段 exit")

    for key in table:
        if key not in _EXIT_KEYS:
            raise ValueError("能力模型出现未知字段 exit.{}".format(key))

    codes = {}
    for key in _EXIT_KEYS:
        if key not in table:
            raise ValueError("能力模型缺少字段 exit.{}".format(key))
        value = table[key]
        if isinstance(value, bool) or not isinstance(value, int):
            raise ValueError("能力模型字段 exit.{} 不合法：不是整数".format(key))
        codes[key] = value
    return codes
