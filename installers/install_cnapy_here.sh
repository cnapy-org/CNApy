#!/bin/sh
# Adapted from https://raw.githubusercontent.com/mamba-org/micromamba-releases/main/install.sh

set -eu

# CNApy version
CNAPY_VERSION="1.2.1.1"

# Folders
BIN_FOLDER="${BIN_FOLDER:-./cnapy-${CNAPY_VERSION}}"
CONDA_FORGE_YES="${CONDA_FORGE_YES:-yes}"

# Computing artifact location
case "$(uname)" in
  Linux)
    PLATFORM="linux" ;;
  Darwin)
    PLATFORM="osx" ;;
  *NT*)
    PLATFORM="win" ;;
esac

ARCH="$(uname -m)"
case "$ARCH" in
  aarch64|ppc64le|arm64)
      ;;  # pass
  *)
    ARCH="64" ;;
esac

case "$PLATFORM-$ARCH" in
  linux-aarch64|linux-ppc64le|linux-64|osx-arm64|osx-64|win-64)
      ;;  # pass
  *)
    echo "Failed to detect your operating system. This installer only supports linux-aarch64|linux-ppc64le|linux-64|osx-arm64|osx-64|win-64" >&2
    exit 1
    ;;
esac

RELEASE_URL="https://github.com/mamba-org/micromamba-releases/releases/latest/download/micromamba-${PLATFORM}-${ARCH}"

# Downloading artifact
mkdir -p "${BIN_FOLDER}"
if hash curl >/dev/null 2>&1; then
  curl "${RELEASE_URL}" -o "${BIN_FOLDER}/micromamba" -fsSL --compressed ${CURL_OPTS:-}
elif hash wget >/dev/null 2>&1; then
  wget ${WGET_OPTS:-} -qO "${BIN_FOLDER}/micromamba" "${RELEASE_URL}"
else
  echo "Neither curl nor wget was found. Please install one of them on your system." >&2
  exit 1
fi
chmod +x "${BIN_FOLDER}/micromamba"

./cnapy-${CNAPY_VERSION}/micromamba create -y -p ./cnapy-${CNAPY_VERSION}/cnapy-environment python=3.10 pip -r ./cnapy-${CNAPY_VERSION}/
./cnapy-${CNAPY_VERSION}/micromamba run -p ./cnapy-${CNAPY_VERSION}/cnapy-environment -r ./cnapy-${CNAPY_VERSION}/ pip install --no-cache-dir uv
./cnapy-${CNAPY_VERSION}/micromamba run -p ./cnapy-${CNAPY_VERSION}/cnapy-environment -r ./cnapy-${CNAPY_VERSION}/ uv --no-cache pip install --no-cache-dir cnapy

cat << 'EOF' > run_cnapy.sh
#!/bin/bash
./cnapy-${CNAPY_VERSION}/micromamba run -p ./cnapy-${CNAPY_VERSION}/cnapy-environment -r ./cnapy-${CNAPY_VERSION}/ cnapy
EOF

# Make the shell script executable
chmod +x run_cnapy.sh
