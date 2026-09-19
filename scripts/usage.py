# python-file: module
"""The answer every script of this repository gives to ``--usage``.

The shape is the one the process requires of every file meant to be run
(SDLC-0025, SDLC-0036), but the code is local: this repository holds
measurements, mounts no convention and reaches for no library outside itself.

    import usage

    COMMANDS = (usage.command("run", "Sprawdza pomiary.", changes=False),)

    if usage.asked(argv):
        return usage.emit(usage.report("validate.py", COMMANDS))

Standard library only. Identifiers, docstrings and comments are English; text
printed for the owner is Polish (SDLC-0001).
"""

import json
from typing import Dict, List, Optional, Sequence

FLAG = "--usage"
PLAIN_COMMAND = "run"


def asked(argv: Sequence[str]) -> bool:
    """Whether this call is the one asking the script to describe itself."""
    return FLAG in tuple(argv)[1:]


def described(name: str, description: str) -> Dict[str, str]:
    """One position of a described list: a name and what it is for."""
    return {"name": name, "description": description}


def command(name: str, summary: str, changes: bool = False,
            arguments: Optional[Sequence[Dict[str, str]]] = None,
            confirms: Optional[Sequence[Dict[str, str]]] = None) -> Dict[str, object]:
    """One command of a script, in the shape the schema of the process requires."""
    entry: Dict[str, object] = {"name": name, "summary": summary,
                                "changes": bool(changes)}
    if arguments:
        entry["arguments"] = list(arguments)
    if confirms:
        entry["confirms"] = list(confirms)
    return entry


def plain(summary: str,
          arguments: Optional[Sequence[Dict[str, str]]] = None,
          changes: bool = False,
          confirms: Optional[Sequence[Dict[str, str]]] = None) -> List[Dict[str, object]]:
    """The single position of a script that has no commands of its own."""
    return [command(PLAIN_COMMAND, summary, changes=changes,
                    arguments=arguments, confirms=confirms)]


def report(name: str, commands: Sequence[Dict[str, object]],
           summary: Optional[str] = None) -> Dict[str, object]:
    """The answer itself."""
    answer: Dict[str, object] = {"result": "PASS", "name": name,
                                 "commands": list(commands)}
    if summary:
        answer["summary"] = summary
    return answer


def emit(answer: Dict[str, object]) -> int:
    """Answer on standard output and the exit code that repeats its result."""
    print(json.dumps(answer, ensure_ascii=False, indent=2))
    return 0 if answer.get("result") == "PASS" else 1
