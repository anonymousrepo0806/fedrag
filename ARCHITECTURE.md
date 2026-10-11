# fedrag architecture

Three components factor out of fedrag_sim.py / fl_net.py so the system has
one clean picture instead of logic spread across the training loop:

```
                        +-----------------------+
                        |   Coordinator/Server  |
                        |  (FedAvg/FedProx/...  |
                        |   aggregation, best-  |
                        |   round selection)     |
                        +-----------+-----------+
                                    ^
                                    |  ConnectionModule
                     +--------------+--------------+
                     |                              |
            +--------+--------+            +--------+--------+
            |  Edge (client 0) |            |  Edge (client N) |
            |                  |     ...    |                  |
            |  EdgeController  |            |  EdgeController  |
            |  (round timing,  |            |  (round timing,  |
            |   loss/val/test  |            |   loss/val/test  |
            |   history)       |            |   history)       |
            +--------+---------+            +--------+---------+
                     |                                |
                     v                                v
            +--------+--------------------------------+---------+
            |                 CacheStore                        |
            |  (sparql_ext external-FAIR-source adjacency       |
            |   cache today; same save/load surface for fqp's   |
            |   Bloom summaries or a KGC model cache tomorrow)  |
            +----------------------------------------------------+
```

## EdgeController (`edge_controller.py`)

One instance per client/edge. It owns that edge's own bookkeeping only:

- `start_round(r)` / `end_round(r, loss=...)` -- brackets one local-training
  call and records the wall time, returning it so the caller can still log
  the same number it always did.
- `.history` -- every round's `{round, train_secs, loss, val_score,
  test_score}`.
- `.total_local_train_secs`, `.cumulative_train_secs_by_round`,
  `.best_round()` -- this edge's own slice of the metrics
  `fedrag_sim.compute_training_efficiency` reports project-wide.

`EdgeFleet` is the coordinator-side registry: `fleet.get(client_id)` gets
or creates that edge's controller, so the server/simulation driver can
assemble the `per_round_client_secs` matrix from the fleet instead of
re-deriving client ordering by hand.

Wired into:
- `fedrag_sim.py`'s `cmd_train` round loop (single-process simulation) --
  replaces the loop's manual `client_secs[ci] = ...` bookkeeping. Verified
  behavior-preserving: a 64-combo sweep run before and after this change
  produced identical `best_round`, `convergence_round` and accuracy
  numbers (wall-clock timings differ by run-to-run noise only, as expected).
- `fl_net.py`'s `cmd_client` (real multi-process/Docker mode) -- each
  client container's own process owns one `EdgeController` for its local
  round loop. Verified against a real local (no-Docker) HTTP run: one
  server process + three client processes on localhost, `EdgeController`
  reporting correct per-client train times (not an aggregate average).

## ConnectionModule (`connection_module.py`)

The interface an edge uses to reach the coordinator: `call(method, path,
data) -> response`, plus `send_update` / `get_model` / `send_eval`
convenience wrappers.

- `HTTPConnectionModule` -- real transport: retrying HTTP client, used by
  `fl_net.py`'s `cmd_client` to reach the coordinator's `http.server`
  process. This is a straight extraction of what used to be an inline
  `Conn` class in `fl_net.py`; `fl_net.py` now does `Conn =
  HTTPConnectionModule` so every existing caller is unchanged. Verified
  with a real local server + 3-client run over actual HTTP (see below).
- `LocalConnectionModule` -- the in-process analogue for
  `fedrag_sim.py`'s single-process simulation, where "sending" a message
  to the coordinator is just a function call because client and server
  share memory. Provided for a future multi-process simulation mode or a
  notebook that wants to swap transports without touching training code;
  not wired into `cmd_train`'s hot path today, since that loop's direct
  in-memory state updates are already covered by the behavior-preserving
  tests above and don't need an extra layer to work correctly.

## CacheStore (`cache_store.py`)

One place that turns `(namespace, key)` into a file under a root
directory and does the pickling, instead of every module inventing its
own `pickle.dump(..., open(path, "wb"))` call.

- `FileCacheHandle(path).save_plain(obj)` / `.load_plain()` -- used by
  `sparql_ext.py`'s `build_cache` (writing the external-FAIR-source
  adjacency cache) and `SparqlExtEngine.__init__` (reading it back), with
  the on-disk format unchanged (still a plain pickle at the path the
  caller chose with `--out`), so existing cache files keep loading.
  Verified by rebuilding a cache against a live fake SPARQL server after
  the switch and confirming identical adjacency output, and by rerunning
  `demo_before_after.py`'s two-source federation scenario end to end.
- `CacheStore(root)` -- the namespaced form (`save`/`load` with an
  envelope recording when and what was cached) for anything that wants a
  shared cache directory instead of one explicit path per call; available
  for `fqp.py`'s Bloom summaries or a trained KGC model to adopt the same
  way without a new on-disk layout.

## Why this split

Every piece above already existed in some form (timing variables inline
in `cmd_train`'s loop, an HTTP client class inline in `fl_net.py`, a bare
`pickle.dump` in `sparql_ext.py`). Pulling them into named modules with a
narrow interface doesn't change what the system does -- it changes what a
diagram of the system looks like, and it means a future piece (a real
multi-process simulation, a different FL transport, a second kind of
cache) has an existing seam to plug into instead of another bespoke
implementation next to the first.
