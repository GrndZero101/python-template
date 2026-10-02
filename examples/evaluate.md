# Review a spec run

A model was given the spec named at the end of this prompt, unedited, in this project, which was
generated fresh from the python-template copier template. Nobody steered it. Your job is to judge
what it built, and above all to work out what the **template** should change as a result. Do not
edit anything.

Read, in this order:

1. **The spec.** Its interface, output, failure table and "Tests that should exist".
2. **The work.** Everything since the first commit, which is the generated project as it shipped:
   `git log --oneline --all` and `git diff $(git rev-list --max-parents=0 HEAD) --stat`, then the
   changed files. Note whether it branched before its first edit and how it finished.
3. **`.gate.log`.** Each line is one gate run. A block the agent then fixed is the gate working;
   the same block repeated means its message did not say how to fix it.
4. **The build session's transcript.** Under `~/.claude/projects/`, in the directory named after
   this project's path, the `.jsonl` file whose first user message is the spec. Look for which
   skills it loaded, the gate output it was shown, and where it went wrong and recovered.
5. **This project's `CLAUDE.md` and `python-cli-modern` skill**, to judge the work by the rules it
   was given.

Report, briefly:

- **Verdict.** Does it meet the spec? Go through the failure table and the tests that should exist,
  row by row: done, done wrongly, or missing.
- **Rules.** Each `CLAUDE.md` rule the work breaks, especially the "convention — review only" rows,
  since nothing else catches those. Give the file and line.
- **Cost of getting there.** Gate blocks, false starts, tokens spent on things the template could
  have settled up front.
- **Template findings.** The section that matters. For each problem: was it the template (a missing
  or misleading skill recipe, a gate message that did not name the fix, a rule nothing enforces, an
  unclear scaffold) or just the model? For each template cause, propose a concrete change: which
  file in the template, and preferably a mechanical check, a script or reference code rather than
  more prose.
