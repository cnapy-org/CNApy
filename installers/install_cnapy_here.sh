#!/bin/sh
# Adapted from https://raw.githubusercontent.com/mamba-org/micromamba-releases/main/install.sh

set -eu

# Optional first argument: a git branch of https://github.com/cnapy-org/CNApy to install
# instead of the pinned PyPI release. Example: ./install_cnapy_here.sh cnapy2
BRANCH="${1:-}"

if [ "${BRANCH}" = "-h" ] || [ "${BRANCH}" = "--help" ]; then
  echo "Usage: $0 [branch]"
  echo "  branch   Optional. A branch of https://github.com/cnapy-org/CNApy to install"
  echo "           instead of the latest release from PyPI, e.g. \"cnapy2\"."
  exit 0
fi

if [ -n "${BRANCH}" ]; then
  if ! hash git >/dev/null 2>&1; then
    echo "ERROR: installing from a specific branch requires git to be installed and available on PATH." >&2
    exit 1
  fi
  echo "Checking that branch '${BRANCH}' exists in https://github.com/cnapy-org/CNApy.git ..."
  if ! git ls-remote --exit-code --heads https://github.com/cnapy-org/CNApy.git "${BRANCH}" >/dev/null 2>&1; then
    echo "ERROR: branch '${BRANCH}' was not found in https://github.com/cnapy-org/CNApy.git" >&2
    exit 1
  fi
  # sanitize for use as a folder name (branch names may contain "/")
  INSTALL_LABEL="$(echo "${BRANCH}" | tr '/' '-')"
else
  INSTALL_LABEL="1.2.8"
fi

# Folders
BIN_FOLDER="${BIN_FOLDER:-./cnapy-${INSTALL_LABEL}}"
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

install_with_retry() {
  description="$1"
  shift
  max_attempts=3
  attempt=1
  while [ "$attempt" -le "$max_attempts" ]; do
    if "$@"; then
      return 0
    fi
    if [ "$attempt" -lt "$max_attempts" ]; then
      echo "${description} failed on attempt ${attempt} of ${max_attempts}, retrying in 5 seconds. This is sometimes caused by antivirus/EDR software briefly locking newly created files..." >&2
      sleep 5
    fi
    attempt=$((attempt + 1))
  done
  echo "ERROR: ${description} failed after ${max_attempts} attempts." >&2
  exit 1
}

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

ENV_DIR="${BIN_FOLDER}/cnapy-environment"
ENV_PYTHON="${ENV_DIR}/bin/python"

"${BIN_FOLDER}/micromamba" create -y -p "${ENV_DIR}" python=3.10 pip openjdk -r "${BIN_FOLDER}" -c conda-forge

if [ ! -x "${ENV_PYTHON}" ]; then
  echo "ERROR: environment creation did not produce a Python interpreter at ${ENV_PYTHON}." >&2
  echo "This is usually caused by a network problem while downloading packages from conda-forge." >&2
  exit 1
fi

# Invoke pip/uv via the environment's own interpreter (absolute path) rather than by
# bare name, so this can never accidentally resolve to some other Python found earlier
# on PATH (e.g. an already-active conda base environment, a Homebrew Python, etc.)
install_with_retry "Installing uv" "${ENV_PYTHON}" -m pip install --no-cache-dir uv
if [ -n "${BRANCH}" ]; then
  install_with_retry "Installing cnapy" "${ENV_PYTHON}" -m uv --no-cache pip install --no-cache-dir "git+https://github.com/cnapy-org/CNApy.git@${BRANCH}"
else
  install_with_retry "Installing cnapy" "${ENV_PYTHON}" -m uv --no-cache pip install --no-cache-dir cnapy
fi

cat << 'EOF' > "${BIN_FOLDER}/run_cnapy.sh"
#!/bin/bash

# Always run relative to this script's own location, regardless of the caller's
# current working directory.
cd "$(dirname "$0")"

# Add CPLEX variable here, e.g.
# export PYTHONPATH=/path_to_cplex/cplex/python/3.10/x86-64_linux

export LD_LIBRARY_PATH="./cnapy-environment/lib/" # For Linux
export DYLD_LIBRARY_PATH="./cnapy-environment/lib/" # For MacOS
./micromamba run -p ./cnapy-environment cnapy
EOF

# Make the shell script executable
chmod +x "${BIN_FOLDER}/run_cnapy.sh"

echo CNApy was succesfully installed!
echo You can now run CNApy by executing run_cnapy.sh in the newly created cnapy-${INSTALL_LABEL} subfolder.
echo To deinstall CNApy later, simply delete the cnapy-${INSTALL_LABEL} subfolder.
