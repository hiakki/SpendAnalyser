# Spend Analyser

Read `AGENTS.md` for architecture, privacy constraints, financial correctness rules,
graph discovery, and verification commands. Those project rules take precedence
over generated tool guidance. Keep all changes inside this repository.

## gstack (recommended)

This project uses [gstack](https://github.com/garrytan/gstack) for AI-assisted workflows.
It is configured in team mode using an existing global installation. Check it with:

```bash
bash scripts/gstack.sh doctor
```

Skills like /qa, /ship, /review, /investigate, and /browse are provided by the global
installation (names may use the `/gstack-` prefix). Use the matching skill for the
task. Route browser work through /browse and use `bash scripts/gstack.sh browse`
for its bundled browser. The wrapper keeps state inside ignored `.gstack/` and
defaults to telemetry, artifact sync, and automatic updates off.

The wrapper discovers `GSTACK_ROOT`, `~/.codex/skills/gstack`,
`~/.claude/skills/gstack`, or the installed skills source. Do not run a global
installer or upgrade as part of routine project work.
