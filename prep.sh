#!/bin/bash

# Color codes for output
GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Error handling
set -euo pipefail
trap 'echo -e "${RED}Error occurred at line $LINENO. Exiting.${NC}" >&2' ERR

echo -e "${GREEN}This process might take 5-10 mins depending on VPS specs. Time to grab a coffee! ☕ ${NC}"

# Function to detect OS and distribution
detect_os() {
    if [[ -f /etc/os-release ]]; then
        . /etc/os-release
        OS=$ID
        VERSION=$VERSION_ID
        CODENAME=$VERSION_CODENAME
    elif type lsb_release >/dev/null 2>&1; then
        OS=$(lsb_release -si | tr '[:upper:]' '[:lower:]')
        VERSION=$(lsb_release -sr)
        CODENAME=$(lsb_release -sc)
    elif [[ -f /etc/debian_version ]]; then
        OS=debian
        VERSION=$(cat /etc/debian_version)
        CODENAME=""
    else
        echo -e "${RED}Cannot detect OS distribution. This script supports Debian-based systems.${NC}"
        exit 1
    fi
}

# Function to check if running with proper privileges
check_privileges() {
    if [[ $EUID -eq 0 ]]; then
        echo -e "${YELLOW}Warning: Running as root. Docker will be configured for root user.${NC}"
        echo -e "${YELLOW}Consider running as a regular user with sudo privileges.${NC}"
    fi
}

# Function to install Docker for apt-based systems
install_docker_apt() {
    echo -e "${GREEN}Installing Docker and Docker Compose... No Docker? No party. 🐳${NC}"
    echo -e "${BLUE}Using apt package manager for $OS${NC}"

    # Install prerequisites
    echo -e "${GREEN}Installing prerequisites...${NC}"
    if ! sudo apt-get install -y -qq ca-certificates curl gnupg lsb-release screen; then
        echo -e "${RED}Failed to install prerequisites. Please check your internet connection.${NC}"
        exit 1
    fi

    # Create keyrings directory
    sudo install -m 0755 -d /etc/apt/keyrings

    # Determine Docker repository URL based on OS
    case "$OS" in
        ubuntu|debian)
            DOCKER_URL="https://download.docker.com/linux/$OS"
            ;;
        raspbian)
            DOCKER_URL="https://download.docker.com/linux/debian"
            ;;
        *)
            echo -e "${RED}Unsupported OS: $OS. This script supports Ubuntu, Debian, and Raspbian.${NC}"
            exit 1
            ;;
    esac

    # Add Docker's official GPG key
    echo -e "${GREEN}Adding Docker's GPG key...${NC}"
    if ! sudo curl -fsSL "$DOCKER_URL/gpg" -o /etc/apt/keyrings/docker.asc; then
        echo -e "${RED}Failed to download Docker GPG key. Please check your internet connection.${NC}"
        exit 1
    fi
    sudo chmod a+r /etc/apt/keyrings/docker.asc

    # Add Docker repository
    echo -e "${GREEN}Adding Docker repository...${NC}"
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] $DOCKER_URL \
    $CODENAME stable" | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

    # Update package index
    echo -e "${GREEN}Updating package index...${NC}"
    if ! sudo apt-get update -qq; then
        echo -e "${RED}Failed to update package index. Repository might be misconfigured.${NC}"
        exit 1
    fi

    # Install Docker packages
    echo -e "${GREEN}Installing Docker packages...${NC}"
    if ! sudo apt-get install -y -qq docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin; then
        echo -e "${RED}Failed to install Docker packages. Please check the error messages above.${NC}"
        exit 1
    fi

    # Start and enable Docker service
    echo -e "${GREEN}Starting Docker service...${NC}"
    if ! sudo systemctl start docker; then
        echo -e "${RED}Failed to start Docker service.${NC}"
        exit 1
    fi

    if ! sudo systemctl enable docker; then
        echo -e "${YELLOW}Warning: Failed to enable Docker service on boot.${NC}"
    fi

    # Add current user to docker group (if not root)
    if [[ $EUID -ne 0 ]]; then
        echo -e "${GREEN}Adding user $USER to docker group...${NC}"
        if ! sudo usermod -aG docker "$USER"; then
            echo -e "${YELLOW}Warning: Failed to add user to docker group.${NC}"
        else
            echo -e "${YELLOW}Note: You'll need to log out and back in for group changes to take effect.${NC}"
            echo -e "${YELLOW}Or run: newgrp docker${NC}"
        fi
    fi

    # Verify Docker installation
    echo -e "${GREEN}Verifying Docker installation...${NC}"
    if sudo docker run --rm hello-world >/dev/null 2>&1; then
        echo -e "${GREEN}✓ Docker is working correctly!${NC}"
    else
        echo -e "${RED}Docker test failed. Please check Docker daemon status.${NC}"
        sudo systemctl status docker --no-pager || true
        exit 1
    fi

    # Verify Docker Compose v2
    echo -e "${GREEN}Verifying Docker Compose v2...${NC}"
    if docker compose version >/dev/null 2>&1; then
        COMPOSE_VERSION=$(docker compose version --short)
        echo -e "${GREEN}✓ Docker Compose v2 is installed (version: $COMPOSE_VERSION)${NC}"
    else
        echo -e "${RED}Docker Compose v2 is not properly installed.${NC}"
        exit 1
    fi
}

# Function to install Docker for yum/dnf-based systems
install_docker_yum() {
    echo -e "${GREEN}Installing Docker and Docker Compose... No Docker? No party. 🐳${NC}"
    echo -e "${BLUE}Using $PKG_MANAGER package manager for $OS${NC}"

    # Remove old Docker versions if any
    echo -e "${GREEN}Removing old Docker versions if present...${NC}"
    sudo $PKG_MANAGER remove -y -q docker docker-client docker-client-latest docker-common \
        docker-latest docker-latest-logrotate docker-logrotate docker-engine \
        podman runc 2>/dev/null || true

    # Install prerequisites
    echo -e "${GREEN}Installing prerequisites...${NC}"
    if ! sudo $PKG_MANAGER install -y -q yum-utils device-mapper-persistent-data lvm2; then
        echo -e "${RED}Failed to install prerequisites.${NC}"
        exit 1
    fi

    # Add Docker repository
    echo -e "${GREEN}Adding Docker repository...${NC}"

    # Download the Docker repo file directly - more reliable across different systems
    local repo_url="https://download.docker.com/linux/${OS}/docker-ce.repo"

    # For RHEL-based systems that don't have their own repo, use CentOS repo
    if [[ "$OS" =~ ^(rhel|rocky|almalinux|ol)$ ]]; then
        repo_url="https://download.docker.com/linux/centos/docker-ce.repo"
    fi

    # Download and install the repo file
    if ! sudo curl -fsSL "$repo_url" -o /etc/yum.repos.d/docker-ce.repo; then
        echo -e "${RED}Failed to download Docker repository file.${NC}"
        exit 1
    fi

    echo -e "${GREEN}✓ Docker repository added successfully.${NC}"

    # Install Docker
    echo -e "${GREEN}Installing Docker packages...${NC}"
    if ! sudo $PKG_MANAGER install -y -q docker-ce docker-ce-cli containerd.io docker-compose-plugin; then
        echo -e "${RED}Failed to install Docker packages.${NC}"
        exit 1
    fi

    # Start and enable Docker service
    echo -e "${GREEN}Starting Docker service...${NC}"
    if ! sudo systemctl start docker; then
        echo -e "${RED}Failed to start Docker service.${NC}"
        exit 1
    fi

    if ! sudo systemctl enable docker; then
        echo -e "${YELLOW}Warning: Failed to enable Docker service on boot.${NC}"
    fi

    # Add current user to docker group (if not root)
    if [[ $EUID -ne 0 ]]; then
        echo -e "${GREEN}Adding user $USER to docker group...${NC}"
        if ! sudo usermod -aG docker "$USER"; then
            echo -e "${YELLOW}Warning: Failed to add user to docker group.${NC}"
        else
            echo -e "${YELLOW}Note: You'll need to log out and back in for group changes to take effect.${NC}"
            echo -e "${YELLOW}Or run: newgrp docker${NC}"
        fi
    fi

    # Verify Docker installation
    echo -e "${GREEN}Verifying Docker installation...${NC}"
    if sudo docker run --rm hello-world >/dev/null 2>&1; then
        echo -e "${GREEN}✓ Docker is working correctly!${NC}"
    else
        echo -e "${RED}Docker test failed. Please check Docker daemon status.${NC}"
        sudo systemctl status docker --no-pager || true
        exit 1
    fi

    # Verify Docker Compose v2
    echo -e "${GREEN}Verifying Docker Compose v2...${NC}"
    if docker compose version >/dev/null 2>&1; then
        COMPOSE_VERSION=$(docker compose version --short)
        echo -e "${GREEN}✓ Docker Compose v2 is installed (version: $COMPOSE_VERSION)${NC}"
    else
        echo -e "${RED}Docker Compose v2 is not properly installed.${NC}"
        exit 1
    fi
}

# Function to install Docker (router)
install_docker() {
    case "$PKG_MANAGER" in
        apt)
            install_docker_apt
            ;;
        dnf|yum)
            install_docker_yum
            ;;
    esac
}

# Detect OS first to check compatibility
detect_os

# Check if OS is supported and set package manager
case "$OS" in
    ubuntu|debian|raspbian)
        echo -e "${GREEN}✓ Detected supported OS: $OS (apt-based)${NC}"
        PKG_MANAGER="apt"
        ;;
    fedora|rhel|centos|rocky|almalinux|ol)
        echo -e "${GREEN}✓ Detected supported OS: $OS (yum/dnf-based)${NC}"
        # Use dnf if available, otherwise fall back to yum
        if command -v dnf &> /dev/null; then
            PKG_MANAGER="dnf"
        else
            PKG_MANAGER="yum"
        fi
        ;;
    *)
        echo -e "${RED}⚠️  Warning: Unsupported OS detected.${NC}"
        echo -e "${RED}   Detected OS: $OS${NC}"
        echo -e "${YELLOW}   You'll need to manually install:${NC}"
        echo -e "${YELLOW}   1. Docker and Docker Compose${NC}"
        echo -e "${YELLOW}   2. Then run: ./install-uv.sh${NC}"
        echo -e ""
        echo -e "${YELLOW}   For Docker installation on $OS, visit:${NC}"
        echo -e "${YELLOW}   https://docs.docker.com/engine/install/${NC}"
        exit 1
        ;;
esac

# Check privileges
check_privileges

# Update package lists
echo -e "${GREEN}Updating package lists...${NC}"
case "$PKG_MANAGER" in
    apt)
        if ! sudo apt-get update -qq -y; then
            echo -e "${YELLOW}Warning: Package update had issues. Continuing anyway...${NC}"
        fi
        ;;
    dnf|yum)
        if ! sudo $PKG_MANAGER makecache -q; then
            echo -e "${YELLOW}Warning: Package cache update had issues. Continuing anyway...${NC}"
        fi
        ;;
esac

# Install Docker and Docker Compose
if ! command -v docker &> /dev/null; then
    install_docker
else
    echo -e "${GREEN}Docker is already installed.${NC}"

    # Check if Docker daemon is running
    if ! sudo docker ps >/dev/null 2>&1; then
        echo -e "${YELLOW}Docker is installed but not running. Starting Docker...${NC}"
        if ! sudo systemctl start docker; then
            echo -e "${RED}Failed to start Docker daemon.${NC}"
            exit 1
        fi
    fi

    # Check Docker Compose v2
    if ! docker compose version >/dev/null 2>&1; then
        echo -e "${YELLOW}Docker Compose v2 not found. Installing...${NC}"
        case "$PKG_MANAGER" in
            apt)
                if ! sudo apt-get install -y -qq docker-compose-plugin; then
                    echo -e "${RED}Failed to install Docker Compose v2.${NC}"
                    exit 1
                fi
                ;;
            dnf|yum)
                if ! sudo $PKG_MANAGER install -y -q docker-compose-plugin; then
                    echo -e "${RED}Failed to install Docker Compose v2.${NC}"
                    exit 1
                fi
                ;;
        esac
    fi

    # Check if user is in docker group (if not root)
    if [[ $EUID -ne 0 ]] && ! groups | grep -q docker; then
        echo -e "${YELLOW}User $USER is not in docker group. Adding...${NC}"
        if sudo usermod -aG docker "$USER"; then
            echo -e "${YELLOW}Note: You'll need to log out and back in for group changes to take effect.${NC}"
            echo -e "${YELLOW}Or run: newgrp docker${NC}"
        fi
    fi

    # Show installed Docker version
    echo -e "${GREEN}✓ Docker version: $(docker --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)${NC}"
fi

# Install Powerloom Snapshotter CLI and dependencies (includes uv installation)
echo -e "${GREEN}Installing Powerloom Snapshotter CLI and dependencies...${NC}"
./install-uv.sh

# Summary of installed components
echo -e "\n${BLUE}=== Installation Summary ===${NC}"
if command -v docker &> /dev/null; then
    echo -e "${GREEN}✓ Docker $(docker --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)${NC}"
fi
if docker compose version &>/dev/null 2>&1; then
    echo -e "${GREEN}✓ Docker Compose $(docker compose version --short 2>/dev/null)${NC}"
fi
if command -v uv &> /dev/null; then
    echo -e "${GREEN}✓ uv $(uv --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')${NC}"
fi
if command -v powerloom-snapshotter-cli &> /dev/null; then
    echo -e "${GREEN}✓ Powerloom CLI $(powerloom-snapshotter-cli --version 2>/dev/null | grep -oE '[0-9]+\.[0-9]+\.[0-9]+')${NC}"
fi

# Success message
echo -e "\n${GREEN}🎉 All dependencies installed successfully! You're all set🚀. Run these two commands to deploy your nodes! 👇\n\n1) ./bootstrap.sh\n2) uv run python multi_clone.py ${NC}"
