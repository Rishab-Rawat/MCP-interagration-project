"""One-command demo for the submission."""
import asyncio
from matching_agent import run_agent

JD = "React developer with 3+ years experience. Strong JavaScript and Node.js skills."

if __name__ == "__main__":
    result = asyncio.run(run_agent(JD))
    print(result["report"])
