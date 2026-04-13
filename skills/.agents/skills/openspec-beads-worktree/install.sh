#!/bin/bash
set -e

# OpenSpec + Beads + Git Worktree Skill Installer
# Version: 1.0.0

echo "======================================"
echo "OpenSpec + Beads + Worktree Skill"
echo "Installation Script"
echo "======================================"
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Helper functions
print_success() {
    echo -e "${GREEN}✓${NC} $1"
}

print_error() {
    echo -e "${RED}✗${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}⚠${NC} $1"
}

# Check prerequisites
echo "Checking prerequisites..."
echo ""

# Check for git
if command -v git &> /dev/null; then
    GIT_VERSION=$(git --version | cut -d' ' -f3)
    print_success "Git found: $GIT_VERSION"
else
    print_error "Git not found"
    echo "Please install Git: https://git-scm.com/downloads"
    exit 1
fi

# Check for Node.js (for OpenSpec)
if command -v node &> /dev/null; then
    NODE_VERSION=$(node --version)
    print_success "Node.js found: $NODE_VERSION"
else
    print_warning "Node.js not found (optional for OpenSpec CLI)"
fi

# Check for npm (for OpenSpec)
if command -v npm &> /dev/null; then
    NPM_VERSION=$(npm --version)
    print_success "npm found: $NPM_VERSION"
else
    print_warning "npm not found (optional for OpenSpec CLI)"
fi

# Check for Beads
if command -v bd &> /dev/null; then
    BD_VERSION=$(bd version 2>&1 | head -n1)
    print_success "Beads found: $BD_VERSION"
else
    print_warning "Beads not found"
    echo "Installing Beads..."
    
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        if command -v brew &> /dev/null; then
            brew tap steveyegge/beads
            brew install bd
            print_success "Beads installed via Homebrew"
        else
            print_warning "Homebrew not found, trying alternative install..."
            curl -fsSL https://raw.githubusercontent.com/steveyegge/beads/main/scripts/install.sh | bash
        fi
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        # Linux
        curl -fsSL https://raw.githubusercontent.com/steveyegge/beads/main/scripts/install.sh | bash
    else
        print_error "Unsupported OS: $OSTYPE"
        echo "Please install Beads manually: https://github.com/steveyegge/beads"
        exit 1
    fi
fi

# Check for Claude Code
if command -v claude &> /dev/null; then
    print_success "Claude Code found"
else
    print_warning "Claude Code not found"
    echo "Install Claude Code: https://claude.ai/download"
fi

echo ""
echo "======================================"
echo "Installing Skill"
echo "======================================"
echo ""

# Determine installation directory
if command -v claude &> /dev/null; then
    # Claude Code installation
    INSTALL_DIR="$HOME/.claude/skills/openspec-beads-worktree"
    print_success "Installing to Claude Code: $INSTALL_DIR"
else
    # Standalone installation
    INSTALL_DIR="$HOME/.claude-skills/openspec-beads-worktree"
    print_warning "Claude Code not found, installing standalone: $INSTALL_DIR"
fi

# Create directory
mkdir -p "$INSTALL_DIR"

# Copy skill files
if [ -f "SKILL.md" ]; then
    cp SKILL.md "$INSTALL_DIR/"
    print_success "Copied SKILL.md"
else
    print_error "SKILL.md not found in current directory"
    exit 1
fi

if [ -f "README.md" ]; then
    cp README.md "$INSTALL_DIR/"
    print_success "Copied README.md"
fi

if [ -f "EXAMPLE.md" ]; then
    cp EXAMPLE.md "$INSTALL_DIR/"
    print_success "Copied EXAMPLE.md"
fi

# Copy example files
if [ -d "openspec-example" ]; then
    cp -r openspec-example "$INSTALL_DIR/"
    print_success "Copied example OpenSpec files"
fi

echo ""
echo "======================================"
echo "Optional: Install OpenSpec CLI"
echo "======================================"
echo ""

read -p "Install OpenSpec CLI? (y/N): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    if command -v npm &> /dev/null; then
        npm install -g openspec
        print_success "OpenSpec CLI installed"
    else
        print_error "npm not found, cannot install OpenSpec CLI"
    fi
else
    print_warning "Skipping OpenSpec CLI installation"
    echo "You can use manual OpenSpec structure instead"
fi

echo ""
echo "======================================"
echo "Optional: Install GNU Parallel"
echo "======================================"
echo ""

if command -v parallel &> /dev/null; then
    print_success "GNU Parallel already installed"
else
    read -p "Install GNU Parallel for parallel execution? (y/N): " -n 1 -r
    echo
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        if [[ "$OSTYPE" == "darwin"* ]]; then
            brew install parallel
            print_success "GNU Parallel installed"
        elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
            if command -v apt-get &> /dev/null; then
                sudo apt-get install -y parallel
            elif command -v yum &> /dev/null; then
                sudo yum install -y parallel
            else
                print_error "Package manager not found"
            fi
        fi
    fi
fi

echo ""
echo "======================================"
echo "Verification"
echo "======================================"
echo ""

# Verify installation
if [ -f "$INSTALL_DIR/SKILL.md" ]; then
    print_success "Skill installed successfully"
else
    print_error "Skill installation failed"
    exit 1
fi

# Test Beads
if command -v bd &> /dev/null; then
    print_success "Beads is ready"
else
    print_error "Beads not found in PATH"
    echo "You may need to restart your terminal or add Beads to PATH"
fi

# Test git worktree
if git worktree list &> /dev/null 2>&1; then
    print_success "Git worktree support available"
else
    print_warning "Git worktree test inconclusive (may work in git repositories)"
fi

echo ""
echo "======================================"
echo "Installation Complete!"
echo "======================================"
echo ""
echo "Skill installed to: $INSTALL_DIR"
echo ""
echo "Next steps:"
echo "1. Navigate to a git repository"
echo "2. Create an OpenSpec proposal (or use example)"
echo "3. Open Claude Code and say:"
echo "   'Implement the <proposal-name> OpenSpec proposal using Beads and worktrees'"
echo ""
echo "For detailed usage, see:"
echo "  $INSTALL_DIR/README.md"
echo "  $INSTALL_DIR/EXAMPLE.md"
echo ""
echo "Quick test:"
echo "  cd /path/to/your/project"
echo "  bd init  # Initialize Beads"
echo "  cp -r $INSTALL_DIR/example-openspec openspec/changes/add-user-authentication"
echo "  claude  # Then invoke the skill"
echo ""
echo "Questions or issues?"
echo "  https://github.com/yourusername/openspec-beads-worktree-skill/issues"
echo ""
