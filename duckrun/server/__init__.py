"""DuckRun server helpers.

local_http: shared sync HTTP client for talking to backend child servers on
loopback. trust_env=False so sandbox/proxy env vars can never route or break
localhost traffic (some httpx versions even crash parsing them).
"""
import httpx

local_http = httpx.Client(trust_env=False, timeout=5.0)
