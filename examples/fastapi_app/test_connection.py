#!/usr/bin/env python3
"""Test basic connection to Cassandra."""

import asyncio
from cassandra.cluster import Cluster

# Test sync connection first
print("Testing sync connection to Cassandra...")
try:
    cluster = Cluster(['127.0.0.1'], port=9042)
    session = cluster.connect()
    print("✅ Sync connection successful!")
    
    # Test a simple query
    result = session.execute("SELECT release_version FROM system.local")
    for row in result:
        print(f"Cassandra version: {row.release_version}")
    
    session.shutdown()
    cluster.shutdown()
except Exception as e:
    print(f"❌ Sync connection failed: {e}")
    import traceback
    traceback.print_exc()

# Test async connection
print("\nTesting async connection with async-cassandra...")
async def test_async():
    try:
        from async_cassandra import AsyncCluster
        
        cluster = AsyncCluster(contact_points=['127.0.0.1'], port=9042)
        session = await cluster.connect()
        print("✅ Async connection successful!")
        
        # Test a simple query
        result = await session.execute("SELECT release_version FROM system.local")
        row = result.one()
        if row:
            print(f"Cassandra version (async): {row.release_version}")
        
        await session.close()
        await cluster.shutdown()
    except Exception as e:
        print(f"❌ Async connection failed: {e}")
        import traceback
        traceback.print_exc()

asyncio.run(test_async())