A source-stated disease may ground a canonical card disease only when it is already
canonical or exactly matches a reviewed alias in the canonical source-alias file,
ignoring surrounding whitespace and letter case only.

Emit only the canonical target in `diseases`, but preserve the source's actual disease
or population wording in evidence and interpretation. Do not use fuzzy matching,
stemming, punctuation substitution, semantic inference, or nearest-term mapping. A
source term that is neither canonical nor a configured alias remains outside the
controlled vocabulary.
