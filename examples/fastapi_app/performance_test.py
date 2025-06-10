#!/usr/bin/env python3
"""
Performance comparison script for async-cassandra with FastAPI.

This script demonstrates the performance benefits of using async operations
compared to synchronous operations when working with Apache Cassandra.
"""

import asyncio
import time
import statistics
from typing import List, Dict, Any
import httpx
import argparse
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TimeElapsedColumn

console = Console()


async def create_test_users(client: httpx.AsyncClient, count: int) -> List[str]:
    """Create test users and return their IDs."""
    user_ids = []
    
    with Progress(
        SpinnerColumn(),
        TextColumn("[bold blue]Creating test users..."),
        BarColumn(),
        TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
        TimeElapsedColumn(),
        console=console,
    ) as progress:
        task = progress.add_task("Creating", total=count)
        
        for i in range(count):
            response = await client.post(
                "/users",
                json={
                    "name": f"Test User {i}",
                    "email": f"test{i}@example.com",
                    "age": 20 + (i % 50)
                }
            )
            if response.status_code == 201:
                user_ids.append(response.json()["id"])
            progress.update(task, advance=1)
    
    return user_ids


async def cleanup_test_users(client: httpx.AsyncClient, user_ids: List[str]) -> None:
    """Clean up test users after testing."""
    console.print("\n[yellow]Cleaning up test users...[/yellow]")
    
    tasks = [client.delete(f"/users/{user_id}") for user_id in user_ids]
    await asyncio.gather(*tasks, return_exceptions=True)
    
    console.print("[green]✓ Cleanup completed[/green]")


async def test_read_performance(
    client: httpx.AsyncClient, 
    user_ids: List[str], 
    iterations: int
) -> Dict[str, Any]:
    """Test read performance by fetching users."""
    latencies = []
    
    console.print(f"\n[cyan]Testing read performance ({iterations} requests)...[/cyan]")
    
    start_time = time.time()
    
    # Create tasks for concurrent reads
    tasks = []
    for i in range(iterations):
        user_id = user_ids[i % len(user_ids)]
        tasks.append(client.get(f"/users/{user_id}"))
    
    # Execute all requests concurrently
    responses = await asyncio.gather(*tasks, return_exceptions=True)
    
    end_time = time.time()
    total_time = end_time - start_time
    
    # Calculate individual request latencies
    successful_requests = 0
    for response in responses:
        if not isinstance(response, Exception) and response.status_code == 200:
            successful_requests += 1
    
    return {
        "total_time": total_time,
        "requests": iterations,
        "successful_requests": successful_requests,
        "requests_per_second": iterations / total_time,
        "avg_latency": total_time / iterations * 1000  # in ms
    }


async def test_write_performance(
    client: httpx.AsyncClient,
    iterations: int
) -> Dict[str, Any]:
    """Test write performance by creating users."""
    console.print(f"\n[cyan]Testing write performance ({iterations} requests)...[/cyan]")
    
    start_time = time.time()
    
    # Create tasks for concurrent writes
    tasks = []
    for i in range(iterations):
        tasks.append(
            client.post(
                "/users",
                json={
                    "name": f"Perf Test User {i}",
                    "email": f"perftest{i}@example.com",
                    "age": 25
                }
            )
        )
    
    # Execute all requests concurrently
    responses = await asyncio.gather(*tasks, return_exceptions=True)
    
    end_time = time.time()
    total_time = end_time - start_time
    
    # Count successful requests and collect IDs for cleanup
    successful_requests = 0
    created_ids = []
    for response in responses:
        if not isinstance(response, Exception) and response.status_code == 201:
            successful_requests += 1
            created_ids.append(response.json()["id"])
    
    # Cleanup created users
    if created_ids:
        await cleanup_test_users(client, created_ids)
    
    return {
        "total_time": total_time,
        "requests": iterations,
        "successful_requests": successful_requests,
        "requests_per_second": iterations / total_time,
        "avg_latency": total_time / iterations * 1000  # in ms
    }


async def test_mixed_workload(
    client: httpx.AsyncClient,
    user_ids: List[str],
    iterations: int,
    read_ratio: float = 0.8
) -> Dict[str, Any]:
    """Test mixed read/write workload."""
    console.print(
        f"\n[cyan]Testing mixed workload "
        f"({int(read_ratio * 100)}% reads, {int((1 - read_ratio) * 100)}% writes)...[/cyan]"
    )
    
    read_count = int(iterations * read_ratio)
    write_count = iterations - read_count
    
    start_time = time.time()
    
    # Create mixed tasks
    tasks = []
    created_ids = []
    
    # Add read tasks
    for i in range(read_count):
        user_id = user_ids[i % len(user_ids)]
        tasks.append(("read", client.get(f"/users/{user_id}")))
    
    # Add write tasks
    for i in range(write_count):
        tasks.append((
            "write",
            client.post(
                "/users",
                json={
                    "name": f"Mixed Test User {i}",
                    "email": f"mixed{i}@example.com",
                    "age": 30
                }
            )
        ))
    
    # Shuffle tasks to simulate real workload
    import random
    random.shuffle(tasks)
    
    # Execute all requests
    results = await asyncio.gather(*[task[1] for task in tasks], return_exceptions=True)
    
    end_time = time.time()
    total_time = end_time - start_time
    
    # Analyze results
    successful_reads = 0
    successful_writes = 0
    
    for i, (op_type, _) in enumerate(tasks):
        result = results[i]
        if not isinstance(result, Exception):
            if op_type == "read" and result.status_code == 200:
                successful_reads += 1
            elif op_type == "write" and result.status_code == 201:
                successful_writes += 1
                created_ids.append(result.json()["id"])
    
    # Cleanup created users
    if created_ids:
        await cleanup_test_users(client, created_ids)
    
    return {
        "total_time": total_time,
        "requests": iterations,
        "successful_reads": successful_reads,
        "successful_writes": successful_writes,
        "requests_per_second": iterations / total_time,
        "avg_latency": total_time / iterations * 1000  # in ms
    }


async def compare_with_sync(client: httpx.AsyncClient, requests: int) -> None:
    """Compare async performance with simulated sync performance."""
    console.print("\n[bold]Comparing Async vs Sync Performance[/bold]")
    
    # Test async performance
    async_resp = await client.get(f"/performance/async?requests={requests}")
    async_data = async_resp.json()
    
    # Test sync performance (simulated)
    sync_resp = await client.get(f"/performance/sync?requests={requests}")
    sync_data = sync_resp.json()
    
    # Create comparison table
    table = Table(title="Performance Comparison")
    table.add_column("Metric", style="cyan")
    table.add_column("Async", style="green")
    table.add_column("Sync (Simulated)", style="yellow")
    table.add_column("Improvement", style="bold magenta")
    
    # Calculate improvements
    time_improvement = sync_data["total_time"] / async_data["total_time"]
    rps_improvement = async_data["requests_per_second"] / sync_data["requests_per_second"]
    
    table.add_row(
        "Total Time (s)",
        f"{async_data['total_time']:.3f}",
        f"{sync_data['total_time']:.3f}",
        f"{time_improvement:.2f}x faster"
    )
    
    table.add_row(
        "Avg Latency (ms)",
        f"{async_data['avg_time_per_request'] * 1000:.2f}",
        f"{sync_data['avg_time_per_request'] * 1000:.2f}",
        f"{time_improvement:.2f}x faster"
    )
    
    table.add_row(
        "Requests/Second",
        f"{async_data['requests_per_second']:.2f}",
        f"{sync_data['requests_per_second']:.2f}",
        f"{rps_improvement:.2f}x higher"
    )
    
    console.print(table)


async def run_performance_tests(
    base_url: str,
    test_users: int,
    read_iterations: int,
    write_iterations: int,
    mixed_iterations: int
) -> None:
    """Run comprehensive performance tests."""
    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        # Check health first
        console.print("[bold]Checking application health...[/bold]")
        health_resp = await client.get("/health")
        
        if health_resp.status_code != 200:
            console.print("[red]❌ Application is not healthy![/red]")
            return
        
        health_data = health_resp.json()
        if not health_data["cassandra_connected"]:
            console.print("[red]❌ Cassandra is not connected![/red]")
            return
        
        console.print("[green]✓ Application is healthy[/green]")
        
        # Create test users
        user_ids = await create_test_users(client, test_users)
        console.print(f"[green]✓ Created {len(user_ids)} test users[/green]")
        
        # Run tests
        results = {}
        
        # Read performance test
        if read_iterations > 0:
            results["read"] = await test_read_performance(client, user_ids, read_iterations)
        
        # Write performance test
        if write_iterations > 0:
            results["write"] = await test_write_performance(client, write_iterations)
        
        # Mixed workload test
        if mixed_iterations > 0:
            results["mixed"] = await test_mixed_workload(client, user_ids, mixed_iterations)
        
        # Display results
        console.print("\n[bold]Performance Test Results[/bold]")
        
        table = Table(title="Test Summary")
        table.add_column("Test Type", style="cyan")
        table.add_column("Total Requests", style="white")
        table.add_column("Successful", style="green")
        table.add_column("Total Time (s)", style="white")
        table.add_column("Requests/Second", style="yellow")
        table.add_column("Avg Latency (ms)", style="white")
        
        for test_type, data in results.items():
            if test_type == "mixed":
                successful = data["successful_reads"] + data["successful_writes"]
            else:
                successful = data["successful_requests"]
            
            table.add_row(
                test_type.capitalize(),
                str(data["requests"]),
                str(successful),
                f"{data['total_time']:.3f}",
                f"{data['requests_per_second']:.2f}",
                f"{data['avg_latency']:.2f}"
            )
        
        console.print(table)
        
        # Compare with sync
        await compare_with_sync(client, 100)
        
        # Cleanup test users
        await cleanup_test_users(client, user_ids)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Performance testing for async-cassandra with FastAPI"
    )
    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="Base URL of the FastAPI application"
    )
    parser.add_argument(
        "--test-users",
        type=int,
        default=10,
        help="Number of test users to create"
    )
    parser.add_argument(
        "--read-iterations",
        type=int,
        default=1000,
        help="Number of read operations to perform"
    )
    parser.add_argument(
        "--write-iterations",
        type=int,
        default=100,
        help="Number of write operations to perform"
    )
    parser.add_argument(
        "--mixed-iterations",
        type=int,
        default=500,
        help="Number of mixed operations to perform"
    )
    
    args = parser.parse_args()
    
    console.print(
        f"[bold cyan]async-cassandra Performance Test[/bold cyan]\n"
        f"URL: {args.url}\n"
        f"Test Users: {args.test_users}\n"
        f"Read Iterations: {args.read_iterations}\n"
        f"Write Iterations: {args.write_iterations}\n"
        f"Mixed Iterations: {args.mixed_iterations}\n"
    )
    
    try:
        asyncio.run(
            run_performance_tests(
                args.url,
                args.test_users,
                args.read_iterations,
                args.write_iterations,
                args.mixed_iterations
            )
        )
    except KeyboardInterrupt:
        console.print("\n[yellow]Performance test interrupted by user[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
        raise


if __name__ == "__main__":
    main()