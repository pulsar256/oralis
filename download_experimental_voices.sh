#!/usr/bin/env bash
set -e

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TARGET_DIR="$REPO_ROOT/voices/experimental_voices"

mkdir -p "$TARGET_DIR"

FILES=(
  "experimental_voices_de.tar.gz|https://github.com/user-attachments/files/24035887/experimental_voices_de.tar.gz"
  "experimental_voices_fr.tar.gz|https://github.com/user-attachments/files/24035880/experimental_voices_fr.tar.gz"
  "experimental_voices_jp.tar.gz|https://github.com/user-attachments/files/24035882/experimental_voices_jp.tar.gz"
  "experimental_voices_kr.tar.gz|https://github.com/user-attachments/files/24035883/experimental_voices_kr.tar.gz"
  "experimental_voices_pl.tar.gz|https://github.com/user-attachments/files/24035885/experimental_voices_pl.tar.gz"
  "experimental_voices_pt.tar.gz|https://github.com/user-attachments/files/24035886/experimental_voices_pt.tar.gz"
  "experimental_voices_sp.tar.gz|https://github.com/user-attachments/files/24035884/experimental_voices_sp.tar.gz"
  "experimental_voices_en1.tar.gz|https://github.com/user-attachments/files/24189272/experimental_voices_en1.tar.gz"
  "experimental_voices_en2.tar.gz|https://github.com/user-attachments/files/24189273/experimental_voices_en2.tar.gz"
)

for entry in "${FILES[@]}"; do
  IFS="|" read -r FNAME URL <<< "$entry"
  echo "[INFO] Downloading $FNAME ..."
  wget -O "$FNAME" "$URL"
  echo "[INFO] Extracting $FNAME ..."
  tar -xzvf "$FNAME" -C "$TARGET_DIR"
  rm -f "$FNAME"
done

echo "[SUCCESS] Experimental voices installed to $TARGET_DIR"
