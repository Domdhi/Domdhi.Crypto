"""shared — core infrastructure every slice rests on: SQLite access + migrations
(``db``) and runtime path resolution (``paths``). The bottom of the dependency DAG;
imports nothing from sibling slices.
"""
