"""Smoke test for capture/embedder.py against live Ollama."""

import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from capture.embedder import generate_embedding


async def main() -> None:
    print("1. Testing basic embedding generation...")
    vec = await generate_embedding("The quick brown fox jumps over the lazy dog.")
    assert isinstance(vec, list)
    assert len(vec) > 0
    assert all(isinstance(v, float) for v in vec)
    print(f"   OK — dimension={len(vec)}, first 5 values: {vec[:5]}")

    print("2. Testing that similar texts produce similar embeddings...")
    vec_a = await generate_embedding("Python is a great programming language.")
    vec_b = await generate_embedding("Python is an excellent coding language.")
    vec_c = await generate_embedding("The weather in Antarctica is extremely cold.")

    def cosine_sim(a: list[float], b: list[float]) -> float:
        dot = sum(x * y for x, y in zip(a, b))
        mag_a = sum(x * x for x in a) ** 0.5
        mag_b = sum(x * x for x in b) ** 0.5
        return dot / (mag_a * mag_b)

    sim_ab = cosine_sim(vec_a, vec_b)
    sim_ac = cosine_sim(vec_a, vec_c)
    print(f"   Similar texts similarity:   {sim_ab:.4f}")
    print(f"   Different texts similarity: {sim_ac:.4f}")
    assert sim_ab > sim_ac, "Similar texts should have higher similarity"
    print("   OK — similar texts ranked higher")

    print("\nAll embedder tests passed!")


if __name__ == "__main__":
    asyncio.run(main())
