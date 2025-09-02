# Performance

PyInj targets O(1) resolution and predictable overhead:

- O(1) type lookups via token tables
- Cached signatures to avoid repeated reflection
- Lock-free fast path for singletons
- Minimal per-binding memory footprint

```python
# Pseudo-benchmark
# 1000 services registered
# ~0.0001ms resolution, ~500 bytes/service
```

