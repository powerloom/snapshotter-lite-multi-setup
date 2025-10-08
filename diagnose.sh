#!/bin/bash

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Function to check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Function to check if a port is in use
check_port() {
    if command_exists lsof; then
        lsof -i:"$1" >/dev/null 2>&1
    else
        netstat -tuln | grep -q ":$1 "
    fi
}

# Function to find next available port
find_next_available_port() {
    local port=$1
    while check_port $port; do
        port=$((port + 1))
    done
    echo $port
}

# Function to get all used Docker subnets in 172.18.0.0/16 range
get_used_subnets() {
    local networks="$1"
    echo "$networks" | while read -r network; do
        docker network inspect "$network" 2>/dev/null | grep -o '"Subnet": "172\.18\.[0-9]\+\.0/24"' | cut -d'.' -f3
    done
}

# Function to apply filters to a list of names (case-insensitive)
apply_filters() {
    local input="$1"
    local result="$input"

    # Apply slot_id filter
    if [ -n "$FILTER_SLOT_ID" ]; then
        result=$(echo "$result" | grep -i "$FILTER_SLOT_ID" || true)
    fi

    # Apply chain filter (case-insensitive)
    if [ -n "$FILTER_CHAIN" ]; then
        result=$(echo "$result" | grep -i "$FILTER_CHAIN" || true)
    fi

    # Apply market filter (case-insensitive)
    if [ -n "$FILTER_MARKET" ]; then
        result=$(echo "$result" | grep -i "$FILTER_MARKET" || true)
    fi

    echo "$result"
}

# Parse command line arguments
AUTO_CLEANUP=false
FILTER_SLOT_ID=""
FILTER_CHAIN=""
FILTER_MARKET=""

while getopts "ys:c:m:" opt; do
    case $opt in
        y) AUTO_CLEANUP=true ;;
        s) FILTER_SLOT_ID="$OPTARG" ;;
        c) FILTER_CHAIN="$OPTARG" ;;
        m) FILTER_MARKET="$OPTARG" ;;
        *) echo "Usage: $0 [-y] [-s SLOT_ID] [-c CHAIN] [-m MARKET]" >&2
           echo "  -y            Auto cleanup without prompts" >&2
           echo "  -s SLOT_ID    Filter by specific slot ID" >&2
           echo "  -c CHAIN      Filter by chain name (e.g., mainnet, devnet)" >&2
           echo "  -m MARKET     Filter by market name (e.g., uniswapv2, aavev3)" >&2
           exit 1 ;;
    esac
done

# Display filter information if any filters are active
FILTER_MSG=""
if [ -n "$FILTER_SLOT_ID" ]; then
    FILTER_MSG="${FILTER_MSG}Slot ID: ${FILTER_SLOT_ID}, "
fi
if [ -n "$FILTER_CHAIN" ]; then
    FILTER_MSG="${FILTER_MSG}Chain: ${FILTER_CHAIN}, "
fi
if [ -n "$FILTER_MARKET" ]; then
    FILTER_MSG="${FILTER_MSG}Market: ${FILTER_MARKET}, "
fi

if [ -n "$FILTER_MSG" ]; then
    # Remove trailing comma and space
    FILTER_MSG="${FILTER_MSG%, }"
    echo "🔍 Starting Powerloom Node Diagnostics (Filters: ${FILTER_MSG})..."
else
    echo "🔍 Starting Powerloom Node Diagnostics..."
fi

# Phase 1: System Checks
echo -e "\n📦 Checking Docker installation..."
if ! command_exists docker; then
    echo -e "${RED}❌ Docker is not installed${NC}"
    echo "Please install Docker first: https://docs.docker.com/get-docker/"
    exit 1
fi

if ! docker info >/dev/null 2>&1; then
    echo -e "${RED}❌ Docker daemon is not running${NC}"
    echo "Please start Docker service"
    exit 1
fi
echo -e "${GREEN}✅ Docker is installed and running${NC}"

# Check docker-compose
echo -e "\n🐳 Checking docker-compose..."
if ! command_exists docker-compose && ! docker compose version >/dev/null 2>&1; then
    echo -e "${RED}❌ Neither docker-compose nor docker compose plugin found${NC}"
    echo "Please install docker-compose or Docker Compose plugin"
    exit 1
fi
echo -e "${GREEN}✅ Docker Compose is available${NC}"


# Check existing containers and networks
echo -e "\n🔍 Checking existing Powerloom containers..."
ALL_CONTAINERS=$(docker ps -a --filter "name=snapshotter-lite-v2" --filter "name=powerloom" --filter "name=local-collector" --filter "name=autoheal" --format "{{.Names}}")
EXISTING_CONTAINERS=$(apply_filters "$ALL_CONTAINERS")
if [ -n "$EXISTING_CONTAINERS" ]; then
    echo -e "${YELLOW}Found existing Powerloom containers:${NC}"
    echo "$EXISTING_CONTAINERS"
fi

echo -e "\n🌐 Checking existing Legacy Docker networks for Powerloom Snapshotter containers..."
EXISTING_NETWORKS=$(docker network ls --filter "name=snapshotter-lite-v2" --format "{{.Name}}")
if [ -n "$EXISTING_NETWORKS" ]; then
    echo -e "${YELLOW}Found existing Powerloom networks:${NC}"
    echo "$EXISTING_NETWORKS"
fi

# Check Docker subnet usage in 172.18.0.0/16 range
echo -e "\n🌐 Checking Legacy Docker subnet usage in 172.18.0.0/16 range..."
NETWORK_LIST=$(docker network ls --format '{{.Name}}')
USED_SUBNETS=$(get_used_subnets "$NETWORK_LIST" | sort -n)
if [ -n "$USED_SUBNETS" ]; then
    echo -e "${YELLOW}Found the following subnets in use:${NC}"
    while read -r octet; do
        echo "172.18.${octet}.0/24"
    done <<< "$USED_SUBNETS"

    # Find available subnets
    echo -e "\n${GREEN}First 5 available subnets:${NC}"
    current=0
    count=0
    while [ $count -lt 5 ] && [ $current -lt 256 ]; do
        if ! echo "$USED_SUBNETS" | grep -q "^$current$"; then
            echo "172.18.${current}.0/24"
            count=$((count + 1))
        fi
        current=$((current + 1))
    done
fi

# Check for cloned directories (but don't remove them yet)
echo -e "\n📁 Checking for Powerloom deployment directories..."
# Matches patterns like:
# - powerloom-premainnet-v2-*
# - powerloom-testnet-v2-*
# - powerloom-mainnet-v2-*
if [[ "$OSTYPE" == "darwin"* ]]; then
    # macOS version
    ALL_DIRS=$(find . -maxdepth 1 -type d \( -name "powerloom-premainnet-v2-*" -o -name "powerloom-testnet*" -o -name "powerloom-mainnet-v2-*" \) -exec basename {} \; || true)
else
    # Linux version
    ALL_DIRS=$(find . -maxdepth 1 -type d \( -name "powerloom-premainnet-v2-*" -o -name "powerloom-testnet*" -o -name "powerloom-mainnet-v2-*" \) -exec basename {} \; || true)
fi

# Apply filters to directories
EXISTING_DIRS=$(apply_filters "$ALL_DIRS")

if [ -n "$EXISTING_DIRS" ]; then
    echo -e "${YELLOW}Found existing Powerloom deployment directories:${NC}"
    echo "$EXISTING_DIRS"
fi

# Phase 2: Cleanup Options
echo -e "\n🧹 Cleanup Options:"

if [ -n "$EXISTING_CONTAINERS" ]; then
    if [ "$AUTO_CLEANUP" = true ]; then
        remove_containers="y"
    else
        read -p "Would you like to stop and remove existing Powerloom containers? (y/n): " remove_containers
    fi
    if [ "$remove_containers" = "y" ]; then
        echo -e "\n${YELLOW}Stopping running containers... (timeout: 10s per container)${NC}"
        # Stop containers with timeout and track failures in parallel
        STOP_FAILED=false
        STUBBORN_CONTAINERS=""
        echo "$EXISTING_CONTAINERS" | xargs -P64 -I {} bash -c '
            container="$1"
            if docker ps -q --filter "name=$container" | grep -q .; then
                echo -e "Attempting to stop container ${container}..."
                if ! timeout 15 docker stop --timeout 10 "$container" 2>/dev/null; then
                    echo -e "\033[1;33m⚠️ Container ${container} could not be stopped gracefully after 10 seconds\033[0m"
                    # Return the container name for force kill
                    echo "$container"
                    exit 1
                fi
            fi
        ' -- {} 2>&1 | while read line; do
            if [[ ! "$line" =~ ^Attempting && ! "$line" =~ ^⚠️ ]]; then
                STUBBORN_CONTAINERS="$STUBBORN_CONTAINERS $line"
            else
                echo "$line"
            fi
        done || STOP_FAILED=true

        # Force kill stubborn containers
        if [ "$STOP_FAILED" = true ]; then
            echo -e "\n${YELLOW}Force killing stubborn containers...${NC}"
            # First try docker kill
            echo "$EXISTING_CONTAINERS" | xargs -P64 -I {} bash -c '
                container="$1"
                if docker ps -q --filter "name=$container" | grep -q .; then
                    echo -e "Force killing container ${container}..."
                    docker kill "$container" 2>/dev/null || true
                fi
            ' -- {}

            # Give a moment for containers to die
            sleep 2
        fi

        echo -e "\n${YELLOW}Removing containers...${NC}"
        # Remove containers in parallel and track failures
        REMOVE_FAILED=false
        echo "$EXISTING_CONTAINERS" | xargs -P64 -I {} bash -c '
            container="$1"
            echo -e "Removing container ${container}..."
            if ! docker rm -f "$container" 2>/dev/null; then
                # If removal still fails, try to get more info
                if docker ps -a --filter "name=$container" --format "{{.Names}}" | grep -q .; then
                    echo -e "\033[0;31m❌ Container ${container} still exists and could not be removed\033[0m"
                    # Try one more aggressive approach
                    container_id=$(docker ps -aq --filter "name=$container" | head -1)
                    if [ -n "$container_id" ]; then
                        echo -e "Attempting final force removal of container ID ${container_id}..."
                        docker rm -f "$container_id" 2>&1 || echo -e "\033[0;31m❌ Final removal attempt failed\033[0m"
                    fi
                fi
                exit 1
            fi
        ' -- {} || REMOVE_FAILED=true

        if [ "$STOP_FAILED" = true ] || [ "$REMOVE_FAILED" = true ]; then
            echo -e "${YELLOW}⚠️ Some containers encountered issues during cleanup:${NC}"
            [ "$STOP_FAILED" = true ] && echo -e "${YELLOW}- Some containers could not be stopped gracefully${NC}"
            [ "$REMOVE_FAILED" = true ] && echo -e "${YELLOW}- Some containers could not be removed${NC}"
        else
            echo -e "${GREEN}✅ All containers successfully cleaned up${NC}"
        fi
    fi
fi

# Check for existing screen sessions
echo -e "\n🖥️ Checking existing Powerloom screen sessions..."
# Get screen sessions and extract just the session names (after the PID.)
ALL_SCREENS=$(screen -ls | grep -E 'powerloom-(premainnet|testnet|mainnet)-v2|snapshotter|pl_.*_.*_[0-9]+' || true)
# Apply filters only to the session name part (after the dot), not the PID
if [ -n "$ALL_SCREENS" ]; then
    EXISTING_SCREENS=""
    while IFS= read -r line; do
        if [ -n "$line" ]; then
            # Extract session name (part after the first dot)
            session_name=$(echo "$line" | sed 's/^[[:space:]]*[0-9]*\.//')
            # Apply filters to session name only
            filtered=$(apply_filters "$session_name")
            if [ -n "$filtered" ]; then
                EXISTING_SCREENS="${EXISTING_SCREENS}${EXISTING_SCREENS:+$'\n'}$line"
            fi
        fi
    done <<< "$ALL_SCREENS"
else
    EXISTING_SCREENS=""
fi
if [ -n "$EXISTING_SCREENS" ]; then
    echo -e "${YELLOW}Found existing Powerloom screen sessions:${NC}"
    echo "$EXISTING_SCREENS"
    if [ "$AUTO_CLEANUP" = true ]; then
        kill_screens="y"
    else
        read -p "Would you like to terminate these screen sessions? (y/n): " kill_screens
    fi
    if [ "$kill_screens" = "y" ]; then
        echo -e "\n${YELLOW}Killing screen sessions...${NC}"
        echo "$EXISTING_SCREENS" | cut -d. -f1 | awk '{print $1}' | xargs -r kill
        echo -e "${GREEN}✅ Screen sessions terminated${NC}"
    fi
fi

if [ -n "$EXISTING_NETWORKS" ]; then
    # Smart network removal based on filters
    if [ -n "$FILTER_SLOT_ID" ]; then
        # Never remove networks when filtering by slot ID (other slots might be using them)
        echo -e "${YELLOW}ℹ️ Skipping network removal (filtering by slot ID - networks are shared across slots)${NC}"
    else
        # For chain/market filters or no filters, only remove networks that are actually empty
        if [ "$AUTO_CLEANUP" = true ]; then
            remove_networks="y"
        else
            read -p "Would you like to remove empty Powerloom networks? (y/n): " remove_networks
        fi
        if [ "$remove_networks" = "y" ]; then
            echo -e "\n${YELLOW}Checking and removing empty networks...${NC}"
            NETWORK_REMOVAL_FAILED=false
            NETWORKS_KEPT=0
            NETWORKS_REMOVED=0

            for network in $EXISTING_NETWORKS; do
                # Check if network has any connected containers
                # Look for the "Containers": { section and check if it's empty or has entries
                NETWORK_INFO=$(docker network inspect "$network" 2>/dev/null || echo "")
                if [ -n "$NETWORK_INFO" ]; then
                    # Check if Containers section exists and has entries
                    # Empty containers section looks like: "Containers": {},
                    # Non-empty has entries like: "Containers": { "abc123...": { ... } },
                    HAS_CONTAINERS=$(echo "$NETWORK_INFO" | grep -A2 '"Containers":' | grep -c '"Name":' || echo "0")
                else
                    HAS_CONTAINERS="0"
                fi

                if [ "$HAS_CONTAINERS" -eq "0" ]; then
                    # Network is empty, safe to remove
                    if docker network rm "$network" 2>/dev/null; then
                        echo -e "${GREEN}✅ Removed empty network: ${network}${NC}"
                        NETWORKS_REMOVED=$((NETWORKS_REMOVED + 1))
                    else
                        echo -e "${YELLOW}⚠️ Failed to remove network ${network}${NC}"
                        NETWORK_REMOVAL_FAILED=true
                    fi
                else
                    echo -e "${YELLOW}ℹ️ Keeping network ${network} (still has connected containers)${NC}"
                    NETWORKS_KEPT=$((NETWORKS_KEPT + 1))
                fi
            done

            if [ "$NETWORKS_REMOVED" -gt 0 ]; then
                echo -e "${GREEN}✅ Removed ${NETWORKS_REMOVED} empty network(s)${NC}"
            fi
            if [ "$NETWORKS_KEPT" -gt 0 ]; then
                echo -e "${YELLOW}ℹ️ Kept ${NETWORKS_KEPT} network(s) with active containers${NC}"
            fi
            if [ "$NETWORK_REMOVAL_FAILED" = true ]; then
                echo -e "${YELLOW}⚠️ Some networks could not be removed${NC}"
            fi
        fi
    fi
fi

# Remove directories after containers and networks are cleaned up
if [ -n "$EXISTING_DIRS" ]; then
    if [ "$AUTO_CLEANUP" = true ]; then
        remove_dirs="y"
    else
        read -p "Would you like to remove the Powerloom deployment directories? (y/n): " remove_dirs
    fi
    if [ "$remove_dirs" = "y" ]; then
        echo -e "\n${YELLOW}Removing deployment directories...${NC}"
        echo "$EXISTING_DIRS" | xargs -I {} rm -rf "{}"
        echo -e "${GREEN}✅ Deployment directories removed${NC}"
    fi
fi

# Add system-wide cleanup option with context-aware message
if [ "${NETWORK_REMOVAL_FAILED:-false}" = true ]; then
    echo -e "\n${YELLOW}Due to network removal failures, a system-wide cleanup is recommended.${NC}"
fi

# Skip the final system-wide cleanup prompt if AUTO_CLEANUP is true
if [ "$AUTO_CLEANUP" = true ]; then
    deep_clean="n"
else
    read -p "Would you like to remove unused Docker resources (only unused images, networks, and cache)? (y/n): " deep_clean
fi
if [ "$deep_clean" = "y" ]; then
    echo -e "\n${YELLOW}Removing unused Docker resources...${NC}"

    echo -e "\n${YELLOW}Running docker network prune...${NC}"
    docker network prune -f

    echo -e "\n${YELLOW}Running docker system prune...${NC}"
    docker system prune -a

    echo -e "${GREEN}✅ Cleanup complete${NC}"
fi

echo -e "\n${GREEN}✅ Diagnostic check complete${NC}"
