Long-running AI stages should execute in workers.

UI threads must remain responsive.

Prefer:
- queues
- workers
- background execution
- streamed logs