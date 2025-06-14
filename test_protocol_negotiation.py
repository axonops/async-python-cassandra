#!/usr/bin/env python3
"""
Test how cassandra-driver handles protocol version negotiation.
"""

# When you specify a protocol_version:
# - Driver uses EXACTLY that version, no negotiation
# - If server doesn't support it, connection fails

# When you DON'T specify protocol_version:
# - Driver starts with its MAX supported version
# - If server doesn't support it, negotiates down
# - Ends up with highest version both support

# Example scenarios:
print("""
Protocol Negotiation Behavior:

1. Client supports v5, Server supports v6, specify v5:
   Result: Uses v5 (no upgrade)

2. Client supports v5, Server supports v6, no specification:
   Result: Uses v5 (client's max)

3. Client supports v6, Server supports v5, specify v6:
   Result: Fails (server doesn't support v6)

4. Client supports v6, Server supports v5, no specification:
   Result: Negotiates down to v5

Current async-cassandra behavior:
- Always sets protocol_version=5
- This PREVENTS using v6+ even if available!
- We're limiting users to v5 exactly, not v5+
""")