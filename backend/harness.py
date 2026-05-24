import os
import subprocess
import json
from typing import Optional

def call_harness_agent(prompt: str) -> Optional[str]:
    """
    Programmatic gRPC bridge communicating with the Antigravity 2.0 IDE agent harness
    via the 'agentapi' CLI utility. Runs cascades and harvests responses.
    """
    print(f"[Harness Bridge] Dispatching prompt to Language Server cascade...")
    
    # 1. Prepare environment context with project binding
    env = os.environ.copy()
    if "ANTIGRAVITY_PROJECT_ID" not in env:
        # Default to active workspace name to satisfy initialization constraints
        env["ANTIGRAVITY_PROJECT_ID"] = "GraphAgentDB"
        
    try:
        # 2. Spawn agentapi subprocess
        cmd = ["agentapi", "new-conversation", "--model=flash", prompt]
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            shell=True,
            env=env,
            timeout=40
        )
        
        # 3. Harvest response
        if result.returncode == 0:
            stdout_text = result.stdout.strip()
            if not stdout_text:
                return None
                
            # Attempt to decode JSON envelope returned by language_server
            try:
                data = json.loads(stdout_text)
                if "response" in data:
                    resp = data["response"]
                    if isinstance(resp, dict) and "text" in resp:
                        return resp["text"]
                    return str(resp)
            except json.JSONDecodeError:
                # Fallback to direct string yield if non-JSON output
                return stdout_text
                
        print(f"[Harness Bridge] Harness execution failed (Exit code: {result.returncode})")
        print(f"Stdout: {result.stdout.strip()}")
        print(f"Stderr: {result.stderr.strip()}")
        
    except subprocess.TimeoutExpired:
        print("[Harness Bridge] Harness execution timed out after 40 seconds.")
    except Exception as e:
        print(f"[Harness Bridge] Failed to execute harness bridge: {e}")
        
    return None
