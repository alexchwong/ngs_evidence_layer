# Pipeline adapters

Adapters are explicit deterministic modules used when two otherwise useful modules have incompatible contracts. Pipeline YAML never contains arbitrary transformation expressions.

An adapter needs:
- a YAML asset declaring its input/output contracts;
- a registered Python handler implementing the deterministic transformation;
- tests showing the transformation is lossless for its declared semantics.

No adapter is required by the shipped default pipelines. Add one only when `pipeline-check` reports an intentional contract mismatch that should be bridged rather than fixed at the producer/consumer.
