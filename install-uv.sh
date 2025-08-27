#!/bin/bash

set -e  # Exit on any error

GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
NC='\033[0m'

echo -e "${GREEN}🚀 Installing Powerloom Snapshotter CLI with uv...${NC}\n"

# Install uv if not already installed
if ! command -v uv &> /dev/null; then
    echo -e "${YELLOW}Installing uv...${NC}"
    curl -LsSf https://astral.sh/uv/install.sh | sh

    # Add uv to PATH for current session
    export PATH="$HOME/.local/bin:$PATH"

    # Add to shell config
    if [[ "$SHELL" == */zsh ]]; then
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.zshrc
    else
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
    fi
else
    echo -e "${GREEN}✓ uv is already installed${NC}"
fi

# Install the CLI globally with uv
echo -e "${YELLOW}Installing Powerloom Snapshotter CLI globally...${NC}"

# Install from PyPI (when published) or from the current directory
if [ -f "pyproject.toml" ]; then
    # Installing from source
    echo -e "${YELLOW}Installing from source...${NC}"
    uv tool install --from . powerloom-snapshotter-cli
else
    # Installing from PyPI
    echo -e "${YELLOW}Installing from PyPI...${NC}"
    uv tool install powerloom-snapshotter-cli
fi

# Ensure uv tool binaries are in PATH
UV_TOOL_BIN_DIR="$HOME/.local/bin"
if [[ ":$PATH:" != *":$UV_TOOL_BIN_DIR:"* ]]; then
    echo -e "${YELLOW}Adding uv tool bin directory to PATH...${NC}"
    export PATH="$UV_TOOL_BIN_DIR:$PATH"
fi

# Verify installation
echo -e "\n${YELLOW}Verifying installation...${NC}"
if command -v powerloom-snapshotter-cli &> /dev/null; then
    echo -e "${GREEN}✅ Installation successful!${NC}"
    echo -e "${GREEN}Version: $(powerloom-snapshotter-cli --version)${NC}"
else
    echo -e "${RED}❌ Installation verification failed${NC}"
    echo -e "${YELLOW}You may need to restart your terminal or run:${NC}"
    echo -e "  ${YELLOW}source ~/.$(basename $SHELL)rc${NC}"
    exit 1
fi

echo -e "\n${GREEN}✅ Installation complete!${NC}"
echo -e "\nYou can now use any of these commands:"
echo -e "  ${YELLOW}powerloom-snapshotter-cli${NC}"
echo -e "  ${YELLOW}snapshotter${NC}"
echo -e "\nTry: ${YELLOW}powerloom-snapshotter-cli --help${NC}"

echo -e "\nTo add $HOME/.local/bin to your PATH, either restart your shell or run:"
echo -e "  ${YELLOW}source $HOME/.local/bin/env (sh, bash, zsh)${NC}"
echo -e "  ${YELLOW}source $HOME/.local/bin/env.fish (fish)${NC}"
