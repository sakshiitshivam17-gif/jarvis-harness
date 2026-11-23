#!/usr/bin/env bash
# Fetch the two vendored assets JARVIS needs: the Piper voice engine + voices,
# and the CUA computer-use driver. Everything lands under tools/ (git-ignored).
set -euo pipefail

cd "$(dirname "$0")/.."
ROOT="$PWD"
PIPER_VERSION="2023.11.14-2"
CUA_VERSION="${CUA_VERSION:-0.59.1}"
VOICES=("en_GB/alan/medium/en_GB-alan-medium" "hi/hi_IN/pratham/medium/hi_IN-pratham-medium")

need() { command -v "$1" >/dev/null 2>&1 || { echo "missing dependency: $1" >&2; exit 1; }; }
need curl
need tar

# ---------------------------------------------------------------- Piper voice
if [ ! -x tools/piper/piper/piper ]; then
  echo "==> downloading Piper $PIPER_VERSION"
  mkdir -p tools/piper
  curl -fsSL -o /tmp/piper.tar.gz \
    "https://github.com/rhasspy/piper/releases/download/${PIPER_VERSION}/piper_linux_x86_64.tar.gz"
  tar xzf /tmp/piper.tar.gz -C tools/piper
  rm -f /tmp/piper.tar.gz
else
  echo "==> Piper already present"
fi

mkdir -p tools/piper/voices
for voice in "${VOICES[@]}"; do
  name="$(basename "$voice")"
  [ -f "tools/piper/voices/$name.onnx" ] && { echo "==> voice $name already present"; continue; }
  echo "==> downloading voice $name"
  base="https://huggingface.co/rhasspy/piper-voices/resolve/main/$voice"
  curl -fsSL -o "tools/piper/voices/$name.onnx" "$base.onnx?download=true"
  curl -fsSL -o "tools/piper/voices/$name.onnx.json" "$base.onnx.json?download=true"
done

# ----------------------------------------------------------------- CUA driver
if [ ! -x tools/cua-driver/cua-driver ]; then
  echo "==> downloading CUA driver v$CUA_VERSION"
  mkdir -p tools/cua-driver
  curl -fsSL -o /tmp/cua-driver.tar.gz \
    "https://github.com/trycua/cua/releases/download/cua-driver-rs-v${CUA_VERSION}/cua-driver-rs-${CUA_VERSION}-linux-x86_64.tar.gz"
  tmp_dir="$(mktemp -d)"
  tar xzf /tmp/cua-driver.tar.gz -C "$tmp_dir"
  cp -r "$tmp_dir"/cua-driver-rs-*/[!.]* tools/cua-driver/
  chmod +x tools/cua-driver/cua-driver
  rm -rf "$tmp_dir" /tmp/cua-driver.tar.gz
else
  echo "==> CUA driver already present"
fi

echo
echo "Assets ready in $ROOT/tools"
echo "The driver starts on demand; no service to enable."
