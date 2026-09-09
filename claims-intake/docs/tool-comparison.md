# Cursor vs agent

I wrote the README in Cursor. I gave the agent two bounded jobs: the HTTP
integration tests, and the Dockerfile.

## What Cursor made easy

I use Claude Sonnet in Cursor. For a short file like the README it is the
right speed: I can see the paragraph, change a sentence, and keep the
`--platform linux/amd64` note in my own words. I would not have trusted an
agent to write that explanation, because the assignment asks for a joiner
explanation, not a generated one.

Sonnet is also what I reach for when I am in the editor. It is fast enough
that I stay in the file. That is the point of Cursor for me: output I can
steer while I am looking at the code.

## What the agent made awkward

The Dockerfile is the example. The project already uses uv (`uv.lock`,
`uv sync --frozen` in the devcontainer). The agent still started from a
plain `python:3.12-bookworm` image and installed with pip. When I asked it
to switch, the next turn treated uv as blocked. It only moved to
`FROM ghcr.io/astral-sh/uv:python3.12-bookworm` and `uv sync --frozen`
after I said to use uv, and then the Astral image, in so many words.

That is the agent pattern: it will finish a file, but it does not stay on
this repo's toolchain unless the prompt names the toolchain. Cursor with
Sonnet did not have that problem on the README, because I was the one
holding `pyproject.toml` open.

The tests showed a different cost. Claude Opus 5 took about 17 minutes to
write `tests/integration/test_routes.py`. Grok 4.6 on the Cursor agent was
noticeably faster on the same kind of bounded task. I would not pay that
Opus wait again for a file whose shape is already fixed by the contract.

## What I reach for

Agent, when the task is a whole new file with a closed checklist (one test
per rule, three lookup reasons). I still have to name the install tool, or
it will invent pip.

Cursor with Sonnet, when the work is a judgment call I have to stand
behind: README wording, a one-line status mapping, a review comment. I
want to see the tokens as they land.

I do not use the agent for "read the repo and pick the base image." That
is where it spent my time correcting pip.