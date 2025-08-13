import os
from pathlib import Path
from typing import Dict, Optional

from dotenv import dotenv_values

from snapshotter_cli.utils.console import console


def get_credential(
    env_var_name: str,
    powerloom_chain_name: str,
    cli_option_value: Optional[str],
    namespaced_env_content: Optional[Dict[str, str]] = None,
) -> Optional[str]:
    """Get a credential value from various sources in order of priority:
    1. CLI option
    2. Environment variable
    3. CWD .env file
    4. Namespaced .env file
    """
    # Priority 1: CLI option
    if cli_option_value:
        return cli_option_value

    # Priority 2: Environment variable
    env_value = os.environ.get(env_var_name)
    if env_value:
        return env_value

    # Priority 3: Check CWD .env file if no explicit namespaced_env_content was passed
    if namespaced_env_content is None:
        cwd_dot_env_path = Path(os.getcwd()) / ".env"
        if cwd_dot_env_path.exists():
            try:
                cwd_env_vars = dotenv_values(cwd_dot_env_path)
                if env_var_name in cwd_env_vars:
                    return cwd_env_vars[env_var_name]
            except Exception as e:
                console.print(f"⚠️ Error reading .env file: {e}", style="yellow")

    # Priority 4: Namespaced .env file
    if namespaced_env_content and env_var_name in namespaced_env_content:
        return namespaced_env_content[env_var_name]

    return None


def get_source_chain_rpc_url(
    source_chain_name: str, namespaced_env_content: Optional[Dict[str, str]] = None
) -> Optional[str]:
    """Get source chain RPC URL from various sources in order of priority:
    1. SOURCE_RPC_{CHAIN} environment variable
    2. CWD .env file
    3. Namespaced .env file
    """
    env_var_suffix = source_chain_name.upper().replace("-", "_")
    source_chain_specific_env_var = f"SOURCE_RPC_{env_var_suffix}"

    # Priority 1: Environment variable (chain-specific)
    env_value = os.environ.get(source_chain_specific_env_var)
    if env_value:
        return env_value

    # Priority 2: Check CWD .env file if no explicit namespaced_env_content was passed
    if namespaced_env_content is None:
        cwd_dot_env_path = Path(os.getcwd()) / ".env"
        if cwd_dot_env_path.exists():
            try:
                cwd_env_vars = dotenv_values(cwd_dot_env_path)
                # Try chain-specific var first
                if source_chain_specific_env_var in cwd_env_vars:
                    return cwd_env_vars[source_chain_specific_env_var]
                # Fallback to generic SOURCE_RPC_URL
                if "SOURCE_RPC_URL" in cwd_env_vars:
                    return cwd_env_vars["SOURCE_RPC_URL"]
            except Exception as e:
                console.print(f"⚠️ Error reading .env file: {e}", style="yellow")

    # Priority 3: Namespaced .env file
    if namespaced_env_content and "SOURCE_RPC_URL" in namespaced_env_content:
        return namespaced_env_content["SOURCE_RPC_URL"]

    return None
