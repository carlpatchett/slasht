#!/usr/bin/env bash
set -e

REPO="carlpatchett/slasht"
BINARY="slasht"
INSTALL_DIR="${INSTALL_DIR:-$HOME/.local/bin}"

# Detect OS and Arch
OS="$(uname -s | tr '[:upper:]' '[:lower:]')"
ARCH="$(uname -m)"

case "$ARCH" in
  x86_64) ARCH="amd64" ;;
  aarch64|arm64) ARCH="arm64" ;;
  *) echo "Unsupported architecture: $ARCH" && exit 1 ;;
esac

case "$OS" in
  linux|darwin) ;;
  *) echo "Unsupported OS: $OS" && exit 1 ;;
esac

echo "Fetching latest release tag for $REPO..."
if command -v gh >/dev/null 2>&1; then
  TAG=$(gh release view -R "$REPO" --json tagName -q .tagName 2>/dev/null || true)
fi

if [ -z "$TAG" ]; then
  TAG=$(curl -s "https://api.github.com/repos/$REPO/releases/latest" | grep '"tag_name":' | sed -E 's/.*"([^"]+)".*/\1/' || true)
fi

if [ -z "$TAG" ]; then
  echo "Error: Could not automatically detect latest release."
  echo "If $REPO is a private repository, please ensure you are authenticated via 'gh auth login' or provide TAG=v1.0.0."
  exit 1
fi

ARCHIVE="slasht_${TAG}_${OS}_${ARCH}.tar.gz"
echo "Downloading $ARCHIVE ($TAG)..."

mkdir -p "$INSTALL_DIR"
TMP_DIR=$(mktemp -d)
trap 'rm -rf "$TMP_DIR"' EXIT

if command -v gh >/dev/null 2>&1; then
  gh release download "$TAG" -R "$REPO" --pattern "$ARCHIVE" --dir "$TMP_DIR"
else
  curl -fsSL "https://github.com/$REPO/releases/download/$TAG/$ARCHIVE" -o "$TMP_DIR/$ARCHIVE"
fi

tar -xzf "$TMP_DIR/$ARCHIVE" -C "$TMP_DIR"
cp "$TMP_DIR/slasht_${TAG}_${OS}_${ARCH}/$BINARY" "$INSTALL_DIR/$BINARY"
chmod +x "$INSTALL_DIR/$BINARY"

echo "Successfully installed $BINARY ($TAG) to $INSTALL_DIR/$BINARY"
