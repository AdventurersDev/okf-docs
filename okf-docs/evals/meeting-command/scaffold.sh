#!/usr/bin/env bash
# Workspace: the brain-repo fixture plus a transcript file outside the brain, given to /okf-docs meeting.
set -euo pipefail
bash "$(dirname "${BASH_SOURCE[0]}")/../fixtures/setup.sh" brain-repo
mkdir -p notes
cat > notes/2026-11-19-initech-pilot-kickoff.txt <<'EOF'
Initech pilot kickoff (internal), 2026-11-19. Priya (head of product), Sam (customer success).

[00:00:10] Priya: quick one, Initech signed the pilot. We need to agree how big it is.
[00:00:35] Sam: they asked for 50 seats. I think 25 is plenty to start.
[00:01:02] Priya: agreed, we run the Initech pilot with 25 seats. Decided.
[00:01:30] Sam: ok. I'll set up the pilot workspace by Monday the 23rd.
[00:01:44] Priya: great.
[00:02:05] Sam: we should write a pilot guide at some point, other customers will ask.
[00:02:20] Priya: maybe. Could we give them SSO early? Just a thought.
[00:02:41] Sam: let's see. That's all from me.
EOF
