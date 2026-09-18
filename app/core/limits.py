"""Ceilings shared by more than one layer of the app.

A user's words enter the product through two doors — a pasted script, which
lands in the API layer (`app/schemas`), and an uploaded document, which lands
in the service layer (`app/services/video`). The two doors have to agree on how
much text is acceptable, or the same words are bounded on one route and not the
other: /align runs a quadratic diff over whatever it is handed, and an
unbounded input to unbounded work is an unbounded request to expensive code.

The number therefore lives here, under both layers, so neither imports across
the boundary the other side of which it would otherwise have been violating.
"""

#: The longest script any script-taking route or reader will accept. Roughly
#: 90 minutes of narration. Everything that truncates keeps this as its cap.
MAX_SCRIPT_CHARACTERS = 120_000